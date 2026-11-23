"""Raw snapshots: the unchanged copy of every source table, one CSV per table per batch.

Layout: evidence/02_etl/raw/batch_<n>/<database>.<table>.csv   (never edited after writing)

Every later step reads raw data through read_raw(), which returns
{(database, table): DataFrame} with every value as text (None for NULL), exactly as the
source returned it. Keeping everything as text means the cleaning step (normalize.py)
is the only place where types are decided, and it can log what failed to parse.

raw_from_generated() builds the same structure straight from the generator output
(data/generated/stage<N>/). It is used only by the pre-database dry run
(src/offline_dry_run.py); the real pipeline reads the snapshots written by src/extract.py.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.common import EVIDENCE_DIR, GENERATED_DIR
from src.gen.sources import COLUMNS, KEYS

RAW_DIR = EVIDENCE_DIR / "02_etl" / "raw"

# Transaction tables are extracted by updated_at watermark; the rest in full every batch.
TRANSACTION_TABLES = {("sales_db", "receipt"), ("sales_db", "receipt_line"), ("purchasing_db", "purchase_order"),
                      ("purchasing_db", "goods_receipt"), ("purchasing_db", "grn_line")}
SOURCE_SYSTEM = {"sales_db": "sales_db", "purchasing_db": "purchasing_db", "finance_db": "finance_db",
                 "inventory": "inventory"}


def batch_dir(batch_id: int) -> Path:
    return RAW_DIR / f"batch_{batch_id}"


def read_csv_text(path: Path) -> pd.DataFrame:
    """Read a CSV keeping every value as text; empty cells become None (SQL NULL)."""
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8")
    return df.astype(object).where(df.notna(), None)


def write_raw(raw: dict, batch_id: int) -> Path:
    folder = batch_dir(batch_id)
    folder.mkdir(parents=True, exist_ok=True)
    for (db, table), df in raw.items():
        df.to_csv(folder / f"{db}.{table}.csv", index=False, lineterminator="\n", encoding="utf-8")
    return folder


def read_raw(batch_id: int | None = None, folder: Path | None = None) -> dict:
    folder = folder or batch_dir(batch_id)
    raw = {}
    for (db, table) in COLUMNS:
        path = folder / f"{db}.{table}.csv"
        if path.exists():
            raw[(db, table)] = read_csv_text(path)
    return raw


def source_key(df: pd.DataFrame, table: str) -> pd.Series:
    """The source key as one text value, e.g. 'GUL-2026-000123|2' for a receipt line."""
    return df[KEYS[table]].astype(str).agg("|".join, axis=1)


def raw_from_generated(stage: int, since=None, until=None) -> dict:
    """Stand-in for an extract, used before the databases exist.

    Transaction tables keep rows with since < updated_at <= until (the watermark rule);
    master tables are taken in full. The till's double export (double_export.csv) is
    reproduced by appending those rows a second time, as the real extract will.
    """
    folder = GENERATED_DIR / f"stage{stage}"
    raw = {}
    for (db, table) in COLUMNS:
        df = read_csv_text(folder / db / f"{table}.csv")
        if (db, table) in TRANSACTION_TABLES:
            ts = pd.to_datetime(df["updated_at"].str[:19])
            keep = pd.Series(True, index=df.index)
            if since is not None:
                keep &= ts > pd.Timestamp(since)
            if until is not None:
                keep &= ts <= pd.Timestamp(until)
            df = df[keep]
        raw[(db, table)] = df.reset_index(drop=True)
    dup = read_csv_text(folder / "double_export.csv")
    for db, table, key_cols in (("sales_db", "receipt_line", ["receipt_no", "line_no"]),
                                ("purchasing_db", "grn_line", ["grn_no", "line_no"])):
        keys = dup[dup.source_table == table][["receipt_no", "line_no"]]
        keys.columns = key_cols
        df = raw[(db, table)]
        extra = df.merge(keys, on=key_cols, how="inner")
        raw[(db, table)] = pd.concat([df, extra], ignore_index=True)
    return raw
