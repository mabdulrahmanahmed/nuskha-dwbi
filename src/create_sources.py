"""Create (or re-create) the tables of the four synthetic source systems.

The DDL lives in sql/01_source_ddl/, one file per department:
  sales_mysql.sql        -> MySQL       sales_db       (SALES_URL)
  finance_mysql.sql      -> MySQL       finance_db     (FINANCE_URL)
  purchasing_postgres.sql-> PostgreSQL  purchasing_db  (PURCHASING_URL)
  inventory_sqlite.sql   -> SQLite      inventory.db   (INVENTORY_PATH)

Each file starts with DROP TABLE IF EXISTS, so running it again gives empty, fresh tables.

Usage:
  python -m src.create_sources                      # all four, using config/.env
  python -m src.create_sources inventory            # one department
  python -m src.create_sources --sqlite-file X.db   # Inventory DDL into a given SQLite file
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from src.common import SQL_DIR, get_engine, inventory_path

DDL_DIR = SQL_DIR / "01_source_ddl"

# department -> (DDL file, engine name in src.common.get_engine)
DEPARTMENTS = {
    "sales": ("sales_mysql.sql", "sales"),
    "finance": ("finance_mysql.sql", "finance"),
    "purchasing": ("purchasing_postgres.sql", "purchasing"),
    "inventory": ("inventory_sqlite.sql", "inventory"),
}


def split_statements(sql_text: str) -> list[str]:
    """Split a DDL file into statements on ';' at the end of a line.

    Comment-only lines are dropped; comments after code on a line are kept
    (MySQL, PostgreSQL and SQLite all accept '-- ' comments inside a statement).
    """
    statements, current = [], []
    for line in sql_text.splitlines():
        if line.strip().startswith("--") and not current:
            continue                                   # comment before a statement
        current.append(line)
        if line.rstrip().endswith(";"):
            stmt = "\n".join(current).strip().rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            current = []
    tail = "\n".join(current).strip()
    if tail and not all(l.strip().startswith("--") or not l.strip() for l in current):
        statements.append(tail)
    return statements


def ddl_text(department: str) -> str:
    return (DDL_DIR / DEPARTMENTS[department][0]).read_text(encoding="utf-8")


def create_inventory_file(path: Path) -> Path:
    """Run the Inventory DDL in a SQLite file (created if missing). No server needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.executescript(ddl_text("inventory"))
        con.commit()
    finally:
        con.close()
    return path


def create_department(department: str) -> int:
    """Run one department's DDL against its configured database; returns statements run."""
    if department == "inventory":
        create_inventory_file(inventory_path())
        return len(split_statements(ddl_text("inventory")))
    from sqlalchemy import text

    statements = split_statements(ddl_text(department))
    engine = get_engine(DEPARTMENTS[department][1])
    with engine.begin() as con:
        for stmt in statements:
            con.execute(text(stmt))
    return len(statements)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("departments", nargs="*",
                        help="any of sales, finance, purchasing, inventory (default: all four)")
    parser.add_argument("--sqlite-file", type=Path, help="create the Inventory tables in this SQLite file")
    args = parser.parse_args()
    unknown = set(args.departments) - set(DEPARTMENTS)
    if unknown:
        parser.error(f"unknown department(s): {', '.join(sorted(unknown))}")
    if args.sqlite_file:
        print(f"inventory: tables created in {create_inventory_file(args.sqlite_file)}")
        return
    for dept in args.departments or list(DEPARTMENTS):
        print(f"{dept}: {create_department(dept)} statements run")


if __name__ == "__main__":
    main()
