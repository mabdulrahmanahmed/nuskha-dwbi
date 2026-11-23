"""Data profiling before and after cleaning (units 2.03 and 2.05).

profile_tables(tables) returns one row per table and column with:
  rows, nulls, distinct values, min and max (as text), the date/number formats seen,
  and for the columns the ETL standardizes (branch, category, unit, currency,
  panel text) the distinct spellings themselves.
Run on the raw snapshots (before) and on the staged tables (after); compare() puts
the two side by side, one pair of rows per table.
"""
from __future__ import annotations

import re

import pandas as pd

# Columns whose distinct spellings are listed in full (they are what cleaning fixes).
SPELLING_COLUMNS = {"branch_name", "branch_text", "branch_label", "category", "sell_unit", "currency",
                    "customer_type", "status", "panel_company_text", "panel_text", "region"}

FORMATS = [  # (label, regex) used to describe how values are written
    ("YYYY-MM-DD hh:mm:ss+tz", r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$"),
    ("YYYY-MM-DD hh:mm:ss", r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"),
    ("YYYY-MM-DD", r"^\d{4}-\d{2}-\d{2}$"),
    ("DD/MM/YYYY", r"^\d{2}/\d{2}/\d{4}$"),
    ("integer", r"^-?\d+$"),
    ("decimal(2)", r"^-?\d+\.\d{2}$"),
    ("decimal(3+)", r"^-?\d+\.\d{3,}$"),
    ("decimal(1)", r"^-?\d+\.\d$"),
]


def value_format(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "NULL"
    s = str(v)
    for label, rx in FORMATS:
        if re.match(rx, s):
            return label
    if s != s.strip():
        return "text with leading/trailing spaces"
    return "text"


def profile_tables(tables: dict, stage_label: str) -> pd.DataFrame:
    rows = []
    for (db, table), df in tables.items():
        for col in df.columns:
            s = df[col]
            non_null = s.dropna()
            as_text = non_null.astype(str)
            formats = as_text.map(value_format).value_counts()
            row = {"profile": stage_label, "database": db, "table": table, "column": col, "rows": len(df),
                   "nulls": int(s.isna().sum()), "distinct": int(as_text.nunique()),
                   "min": as_text.min() if len(as_text) else None,
                   "max": as_text.max() if len(as_text) else None,
                   "formats": "; ".join(f"{k}={v}" for k, v in formats.items()),
                   "spellings": None}
            if col in SPELLING_COLUMNS and as_text.nunique() <= 60:
                counts = as_text.value_counts()
                row["spellings"] = "; ".join(f"'{k}'={v}" for k, v in counts.items())
            # Real date range for date-like columns (text min/max is misleading for DD/MM/YYYY).
            if len(as_text) and formats.index[0] in ("DD/MM/YYYY",):
                d = pd.to_datetime(as_text, format="%d/%m/%Y", errors="coerce")
                row["min"], row["max"] = str(d.min().date()), str(d.max().date())
            rows.append(row)
    return pd.DataFrame(rows)


def table_summary(profile: pd.DataFrame) -> pd.DataFrame:
    """One row per table: rows, total nulls, number of columns with mixed formats or spellings."""
    g = profile.groupby(["profile", "database", "table"])
    return pd.DataFrame({
        "rows": g["rows"].first(),
        "columns": g["column"].count(),
        "null_cells": g["nulls"].sum(),
        "mixed_format_columns": g["formats"].apply(lambda f: int(sum(";" in x for x in f if x))),
        "columns_with_spelling_list": g["spellings"].apply(lambda s: int(s.notna().sum())),
    }).reset_index()


def compare(before: pd.DataFrame, after: pd.DataFrame, table_map: dict) -> pd.DataFrame:
    """Side by side: each raw table next to the staged table it becomes (a pair per table)."""
    b, a = table_summary(before), table_summary(after)
    rows = []
    for (db, table), stg_name in table_map.items():
        rb = b[(b.database == db) & (b.table == table)]
        ra = a[a.table == stg_name]
        for label, r in (("before (raw)", rb), ("after (staged)", ra)):
            if len(r):
                r = r.iloc[0]
                rows.append({"source_table": f"{db}.{table}", "profile": label, "table": r.table, "rows": r.rows,
                             "null_cells": r.null_cells, "mixed_format_columns": r.mixed_format_columns,
                             "columns_with_spelling_list": r.columns_with_spelling_list})
    return pd.DataFrame(rows)
