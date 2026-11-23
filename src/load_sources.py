"""Load the generated source data into the four source systems (unit 1.08). Synthetic data.

  python -m src.load_sources --stage 1            # (re)create and fill all four sources
  python -m src.load_sources --stage 1 --twice    # build twice from scratch, compare checksums
                                                  # -> evidence/01_sources/reproducibility.csv

For each MySQL / PostgreSQL database the DDL is run again (it starts with DROP TABLE IF EXISTS),
then every CSV in data/generated/stage<N>/<database>/ is inserted as text and the engine
converts the types. Sales is loaded with FOREIGN_KEY_CHECKS=0 because the planted R07 orphan
lines have no header (the legacy till lost them). Inventory is the generated SQLite file,
copied to INVENTORY_PATH.

checksum_table() reads a table back in primary-key order and hashes it, so two builds can be
compared table by table: identical hashes mean identical data.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
from decimal import Decimal

import pandas as pd

from src.common import GENERATED_DIR, get_engine, inventory_path, write_evidence
from src.create_sources import DEPARTMENTS, create_department
from src.gen.sources import COLUMNS, KEYS
from src.raw import read_csv_text

DB_OF_DEPT = {"sales": "sales_db", "finance": "finance_db", "purchasing": "purchasing_db", "inventory": "inventory"}
# Parents before children, so foreign keys are satisfied where the engine checks them.
LOAD_ORDER = {
    "sales_db": ["loyalty_member", "pos_item", "receipt", "receipt_line"],
    "finance_db": ["panel_account", "fx_rate", "panel_invoice"],
    "purchasing_db": ["supplier", "branch", "vendor_item", "purchase_order", "goods_receipt", "grn_line"],
}


def load_server_department(dept: str, stage: int, chunk: int = 2000) -> dict:
    from sqlalchemy import text

    db = DB_OF_DEPT[dept]
    create_department(dept)                                      # drop + create the tables
    engine = get_engine(DEPARTMENTS[dept][1])
    counts = {}
    with engine.begin() as con:
        if engine.dialect.name == "mysql":
            con.execute(text("SET FOREIGN_KEY_CHECKS = 0"))       # R07 orphan lines exist on purpose
        for table in LOAD_ORDER[db]:
            df = read_csv_text(GENERATED_DIR / f"stage{stage}" / db / f"{table}.csv")
            cols = COLUMNS[(db, table)]
            sql = text(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})")
            records = df[cols].to_dict("records")
            for i in range(0, len(records), chunk):
                con.execute(sql, records[i:i + chunk])
            counts[table] = len(records)
        if engine.dialect.name == "mysql":
            con.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        if db == "purchasing_db":                                  # SERIAL kept in step with loaded ids
            con.execute(text("SELECT setval(pg_get_serial_sequence('supplier', 'supplier_id'), "
                             "(SELECT max(supplier_id) FROM supplier))"))
    return counts


def load_inventory(stage: int) -> dict:
    target = inventory_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(GENERATED_DIR / f"stage{stage}" / "inventory.db", target)
    return {t: None for (db, t) in COLUMNS if db == "inventory"}


def load_stage(stage: int, departments=None) -> None:
    for dept in departments or DB_OF_DEPT:
        if dept == "inventory":
            load_inventory(stage)
        else:
            load_server_department(dept, stage)
        print(f"{dept}: loaded stage {stage}")


def _canonical(v) -> str:
    """One text form per value, whatever the engine returned (Decimal, datetime, bool...)."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    if isinstance(v, Decimal):
        return format(v.normalize(), "f")
    if isinstance(v, float):
        return format(Decimal(str(v)).normalize(), "f")
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


def checksum_table(db: str, table: str) -> tuple[int, str]:
    """(row count, md5 of all rows in primary-key order) for one source table."""
    from sqlalchemy import text

    engine = get_engine({"sales_db": "sales", "finance_db": "finance", "purchasing_db": "purchasing",
                         "inventory": "inventory"}[db])
    order = ", ".join(KEYS[table])
    with engine.connect() as con:
        rows = con.execute(text(f"SELECT {', '.join(COLUMNS[(db, table)])} FROM {table} ORDER BY {order}")).fetchall()
    h = hashlib.md5()
    for row in rows:
        h.update(("\x1f".join(_canonical(v) for v in row) + "\n").encode("utf-8"))
    return len(rows), h.hexdigest()


def checksums(departments=None) -> pd.DataFrame:
    dbs = {DB_OF_DEPT[d] for d in (departments or DB_OF_DEPT)}
    out = []
    for (db, table) in COLUMNS:
        if db in dbs:
            n, digest = checksum_table(db, table)
            out.append({"database": db, "table": table, "rows": n, "md5": digest})
    return pd.DataFrame(out)


def build_twice(stage: int, departments=None) -> pd.DataFrame:
    """Build from scratch twice and compare per-table checksums (unit 1.08 acceptance)."""
    load_stage(stage, departments)
    first = checksums(departments)
    load_stage(stage, departments)
    second = checksums(departments)
    out = first.merge(second, on=["database", "table"], suffixes=("_build1", "_build2"))
    out["identical"] = (out.rows_build1 == out.rows_build2) & (out.md5_build1 == out.md5_build2)
    out["result"] = out.identical.map({True: "PASS", False: "FAIL"})
    write_evidence("01_sources", "reproducibility.csv", out.drop(columns="identical"))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", type=int, choices=[1, 2], default=1)
    parser.add_argument("--twice", action="store_true", help="build twice and compare checksums")
    parser.add_argument("departments", nargs="*", help="default: all four")
    args = parser.parse_args()
    if args.twice:
        out = build_twice(args.stage, args.departments or None)
        print(out.to_string(index=False))
        if (out.result != "PASS").any():
            raise SystemExit("reproducibility check FAILED")
    else:
        load_stage(args.stage, args.departments or None)


if __name__ == "__main__":
    main()
