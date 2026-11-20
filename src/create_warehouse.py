"""Create the warehouse objects in nuskha_dw (units 2.01 and 3.01). Synthetic data.

Runs the DDL files in sql/02_warehouse_ddl/ in name order:
  01_schemas_and_control.sql  schemas dw, stg, etl, meta, ai + etl control tables + crosswalks
  02_dw_stars.sql             dimensions and the two fact tables (blueprint columns)
  03_meta_and_ai.sql          metadata repository and AI output tables
Every statement uses IF NOT EXISTS, so running it again changes nothing.

  python -m src.create_warehouse            # all files
  python -m src.create_warehouse 01         # only files whose name starts with 01
  python -m src.create_warehouse --check    # list tables per schema afterwards
"""
from __future__ import annotations

import sys

from src.common import SQL_DIR, get_engine
from src.create_sources import split_statements

DDL_DIR = SQL_DIR / "02_warehouse_ddl"


def ddl_files(prefix: str = ""):
    return sorted(p for p in DDL_DIR.glob("*.sql") if p.name.startswith(prefix))


def create(prefix: str = "") -> int:
    from sqlalchemy import text

    n = 0
    with get_engine("dw").begin() as con:                    # all files in one transaction
        for path in ddl_files(prefix):
            for stmt in split_statements(path.read_text(encoding="utf-8")):
                con.execute(text(stmt))
                n += 1
            print(f"{path.name}: done")
    return n


def list_tables():
    from sqlalchemy import text

    with get_engine("dw").connect() as con:
        return con.execute(text(
            "SELECT table_schema, table_name FROM information_schema.tables "
            "WHERE table_schema IN ('dw','stg','etl','meta','ai') ORDER BY 1, 2")).fetchall()


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    print(f"{create(args[0] if args else '')} statements run")
    if "--check" in sys.argv:
        for schema, table in list_tables():
            print(f"  {schema}.{table}")
