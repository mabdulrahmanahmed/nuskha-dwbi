"""Metadata repository content (unit 3.08). Synthetic data.

Builds the rows of the meta tables from configuration files and the DDL:
  meta.source_system   the four departments (engine, database, owner, synthetic flag)
  meta.transform_rule  config/transform_rules.csv (rule id, plain-language rule, code reference)
  meta.column_map      config/column_map.csv (source column -> staging -> warehouse column, rule)
  meta.source_object / meta.lineage are filled per batch by the loader (row counts, fact keys).

coverage_check() proves that every warehouse column in sql/02_warehouse_ddl/02_dw_stars.sql has a
mapping and every mapping names a known rule.

  python -m src.metadata          # print the coverage check
  python -m src.metadata --load   # fill the meta tables in nuskha_dw and check lineage coverage
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


def load() -> pd.DataFrame:
    """Upsert the meta tables, then check mapping coverage and fact lineage (unit 3.08)."""
    import sys

    from sqlalchemy import text

    from src.common import evidence_dir, get_engine, write_evidence
    from src.gen.sources import KEYS

    with get_engine("dw").begin() as con:
        for r in SOURCE_SYSTEMS.to_dict("records"):
            con.execute(text("INSERT INTO meta.source_system VALUES (:source_system, :engine, :database_name, "
                             ":department, :owner, :is_synthetic) ON CONFLICT (source_system) DO UPDATE SET "
                             "engine = EXCLUDED.engine, database_name = EXCLUDED.database_name, "
                             "department = EXCLUDED.department, owner = EXCLUDED.owner"), r)
        for r in transform_rules().to_dict("records"):
            con.execute(text("INSERT INTO meta.transform_rule VALUES (:rule_id, :description, :code_reference) "
                             "ON CONFLICT (rule_id) DO UPDATE SET description = EXCLUDED.description, "
                             "code_reference = EXCLUDED.code_reference"), r)
        cm = column_map()
        cm["source_column"] = cm.source_column.replace("", "(generated)")   # surrogate keys have no source column
        for r in cm.replace("", None).to_dict("records"):
            con.execute(text(
                "INSERT INTO meta.column_map (source_system, source_object, source_column, staging_table, "
                "staging_column, warehouse_table, warehouse_column, rule_id) VALUES (:source_system, :source_object, "
                ":source_column, :staging_table, :staging_column, :warehouse_table, :warehouse_column, :rule_id) "
                "ON CONFLICT (source_system, source_object, source_column, warehouse_table, warehouse_column) "
                "DO UPDATE SET staging_table = EXCLUDED.staging_table, staging_column = EXCLUDED.staging_column, "
                "rule_id = EXCLUDED.rule_id"), r)
        # One row per source table per extract batch, with the row count read from the source.
        for log in sorted(evidence_dir("02_etl").glob("extract_log_batch_*.csv")):
            for r in pd.read_csv(log).itertuples():
                con.execute(text(
                    "INSERT INTO meta.source_object VALUES (:s, :o, :pk, :b, :n) ON CONFLICT "
                    "(source_system, object_name, batch_id) DO UPDATE SET row_count = EXCLUDED.row_count"),
                    {"s": r.database, "o": r.table, "pk": ", ".join(KEYS[r.table]), "b": int(r.batch_id),
                     "n": int(r.source_count)})
        q = lambda sql: con.execute(text(sql)).scalar()  # noqa: E731
        counts = {t: q(f"SELECT count(*) FROM meta.{t}")
                  for t in ("source_system", "source_object", "transform_rule", "column_map", "lineage")}
        lin = {t: q(f"SELECT round(100.0 * count(l.natural_key) / count(*), 2) FROM dw.{t} f LEFT JOIN meta.lineage l "
                    f"ON l.warehouse_table = 'dw.{t}' AND l.natural_key = f.source_system || '|' || f.source_key")
               for t in ("fact_sales", "fact_purchase")}
        bad_rule = q("SELECT count(*) FROM meta.column_map WHERE rule_id IS NOT NULL AND rule_id NOT IN "
                     "(SELECT rule_id FROM meta.transform_rule)")
    out = coverage_check()
    extra = [(f"meta.{t} rows", "> 0", n, n > 0) for t, n in counts.items()]
    extra += [(f"dw.{t}: % of rows with lineage", 100, float(v), float(v) == 100.0) for t, v in lin.items()]
    extra += [("meta.column_map rules all exist in meta.transform_rule", 0, bad_rule, bad_rule == 0)]
    more = pd.DataFrame(extra, columns=["check", "expected", "actual", "ok"])
    more["result"] = more.pop("ok").map({True: "PASS", False: "FAIL"})
    out = pd.concat([out, more], ignore_index=True)
    write_evidence("04_metadata_lineage", "metadata_checks.csv", out)
    with get_engine("dw").connect() as con:
        for t in ("source_system", "source_object", "transform_rule", "column_map"):
            write_evidence("04_metadata_lineage", f"meta_{t}.csv", pd.read_sql(text(f"SELECT * FROM meta.{t}"), con))
    print(out.to_string(index=False))
    if (out.result == "FAIL").any():
        sys.exit(1)
    return out


if __name__ == "__main__":
    import sys

    if "--load" in sys.argv:
        load()
    else:
        print(coverage_check().to_string(index=False))
