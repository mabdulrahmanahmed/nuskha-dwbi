"""Metadata repository content (unit 3.08). Synthetic data.

Builds the rows of the meta tables from configuration files and the DDL:
  meta.source_system   the four departments (engine, database, owner, synthetic flag)
  meta.transform_rule  config/transform_rules.csv (rule id, plain-language rule, code reference)
  meta.column_map      config/column_map.csv (source column -> staging -> warehouse column, rule)
  meta.source_object / meta.lineage are filled per batch by the loader (row counts, fact keys).

coverage_check() proves that every warehouse column in sql/02_warehouse_ddl/02_dw_stars.sql has a
mapping and every mapping names a known rule.

  python -m src.metadata          # print the coverage check
"""
from __future__ import annotations

import pandas as pd

from src.common import CONFIG_DIR, SQL_DIR

SOURCE_SYSTEMS = pd.DataFrame([
    {"source_system": "sales_db", "engine": "MySQL", "database_name": "sales_db", "department": "Sales (till / POS)",
     "owner": "Sales operations", "is_synthetic": True},
    {"source_system": "finance_db", "engine": "MySQL", "database_name": "finance_db", "department": "Finance",
     "owner": "Finance controller", "is_synthetic": True},
    {"source_system": "purchasing_db", "engine": "PostgreSQL", "database_name": "purchasing_db",
     "department": "Purchasing", "owner": "Procurement head", "is_synthetic": True},
    {"source_system": "inventory", "engine": "SQLite", "database_name": "inventory.db", "department": "Inventory",
     "owner": "Inventory control", "is_synthetic": True},
])


def transform_rules() -> pd.DataFrame:
    return pd.read_csv(CONFIG_DIR / "transform_rules.csv", dtype=str)


def column_map() -> pd.DataFrame:
    return pd.read_csv(CONFIG_DIR / "column_map.csv", dtype=str, keep_default_na=False)


def coverage_check() -> pd.DataFrame:
    from src.erd import parse_ddl

    tables = parse_ddl((SQL_DIR / "02_warehouse_ddl" / "02_dw_stars.sql").read_text(encoding="utf-8"))
    needed = {(t, c.name) for t, tab in tables.items() for c in tab.columns}
    cmap = column_map()
    have = set(zip(cmap.warehouse_table, cmap.warehouse_column))
    unknown_rules = set(cmap.rule_id[cmap.rule_id != ""]) - set(transform_rules().rule_id)
    rows = [
        ("warehouse columns with at least one mapping", len(needed), len(needed & have), needed <= have),
        ("mappings to columns that do not exist in the DDL", 0, len(have - needed), not (have - needed)),
        ("mappings naming an unknown transform rule", 0, len(unknown_rules), not unknown_rules),
    ]
    out = pd.DataFrame(rows, columns=["check", "expected", "actual", "ok"])
    out["result"] = out.pop("ok").map({True: "PASS", False: "FAIL"})
    return out


if __name__ == "__main__":
    print(coverage_check().to_string(index=False))
