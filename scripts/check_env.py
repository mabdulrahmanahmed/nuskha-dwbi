"""Check (and optionally create) the five databases the project uses.

  python scripts/check_env.py            # print OK / FAIL for each connection
  python scripts/check_env.py --create   # first create missing databases, then check

Connections come from config/.env:
  SALES_URL, FINANCE_URL  -> MySQL      (sales_db, finance_db)
  PURCHASING_URL, DW_URL  -> PostgreSQL (purchasing_db, nuskha_dw)
  INVENTORY_PATH          -> SQLite file (created on first use)

"Create" connects with the same .env user to the server itself (MySQL: no database;
PostgreSQL: the 'postgres' database) and runs CREATE DATABASE for any missing one.
It never creates users or changes server settings: that is the person's setup step.
Exit code 0 only when all five are OK.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # so `src` imports from scripts/

from sqlalchemy import create_engine, text                        # noqa: E402
from sqlalchemy.engine import make_url                            # noqa: E402

from src.common import ENV_KEYS, CONFIG_DIR, inventory_path, load_env, setting  # noqa: E402

SERVER_DBS = [("MySQL", "SALES_URL"), ("MySQL", "FINANCE_URL"),
              ("PostgreSQL", "PURCHASING_URL"), ("PostgreSQL", "DW_URL")]


def create_database(url_text: str) -> str:
    """CREATE DATABASE <name> on the server if it does not exist yet."""
    url = make_url(url_text)
    name = url.database
    if url.get_backend_name() == "mysql":
        # Connect to information_schema (always present): url.set(database=None) would keep the
        # old name, because SQLAlchemy treats None as "unchanged".
        server = create_engine(url.set(database="information_schema"))
        with server.begin() as con:
            con.execute(text(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4"))
        return f"{name}: present"
    server = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with server.connect() as con:
        exists = con.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}).first()
        if not exists:
            con.execute(text(f'CREATE DATABASE "{name}"'))
            return f"{name}: created"
    return f"{name}: present"


def check(create: bool) -> bool:
    found = load_env()
    if not (CONFIG_DIR / ".env").exists():
        print("FAIL config/.env is missing: copy config/.env.example to config/.env (see docs/BLOCKERS.md)")
        return False
    missing = [k for k in ENV_KEYS if k not in found]
    if missing:
        print(f"FAIL config/.env lacks: {', '.join(missing)}")
        return False
    all_ok = True
    for engine_name, key in SERVER_DBS:
        url_text = setting(key)
        label = f"{engine_name:<10} {make_url(url_text).database:<14}"
        try:
            if create:
                create_database(url_text)
            with create_engine(url_text).connect() as con:
                version = con.execute(text("SELECT version()")).scalar()
            print(f"OK   {label} ({str(version).split(',')[0][:40]})")
        except Exception as exc:                                    # show the first line of the error only
            all_ok = False
            print(f"FAIL {label} {str(exc).splitlines()[0][:160]}")
    try:
        path = inventory_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(path).execute("SELECT sqlite_version()").fetchone()
        print(f"OK   SQLite     {path.name}")
    except Exception as exc:
        all_ok = False
        print(f"FAIL SQLite     {exc}")
    return all_ok


if __name__ == "__main__":
    sys.exit(0 if check("--create" in sys.argv) else 1)
