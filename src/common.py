"""Shared helpers for every pipeline step of the Nuskha DWBI project.

All data handled by this project is SYNTHETIC (generated with seed 472); no real
patients, brands or companies appear anywhere.

What lives here:
  * project paths (pathlib only, so the code runs on Windows, Linux and Colab)
  * connection settings read from config/.env, and SQLAlchemy engines built from them
  * batch helpers for etl.batch (used once the warehouse exists, unit 2.01 onwards)
  * log_stage(): one log line per pipeline step, to a CSV under evidence/<area>/
    and, when the warehouse is reachable, to etl.batch_stage_log
  * write_evidence(): save a table (DataFrame or list of dicts) as CSV evidence
  * money(): round a value to 2 decimals the way accountants expect (half up)

Importing this module never connects to a database: engines are created lazily.
"""
from __future__ import annotations

import csv
import os
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent          # project folder
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
GENERATED_DIR = DATA_DIR / "generated"                  # generator output (CSV + SQLite)
EVIDENCE_DIR = ROOT / "evidence"
SQL_DIR = ROOT / "sql"

SEED = 472                                              # the one seed used everywhere

# The keys config/.env must define (see config/.env.example).
ENV_KEYS = ("SALES_URL", "FINANCE_URL", "PURCHASING_URL", "INVENTORY_PATH", "DW_URL")


# ---------------------------------------------------------------------------
# Settings from config/.env
# ---------------------------------------------------------------------------
def load_env(path: Path | None = None) -> dict:
    """Read KEY=VALUE lines from config/.env into os.environ (existing values win).

    A tiny parser is used instead of python-dotenv so there is one less dependency.
    Returns the settings found. A missing file is not an error: steps that need a
    database will fail later with a clear message.
    """
    path = path or (CONFIG_DIR / ".env")
    found = {}
    if path.exists():
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            found[key.strip()] = value.strip().strip('"').strip("'")
    for key, value in found.items():
        os.environ.setdefault(key, value)
    return found


def setting(key: str) -> str:
    """Return one setting (from the environment or config/.env), or raise a clear error."""
    load_env()
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"{key} is not set: copy config/.env.example to config/.env and fill it in")
    return value


def inventory_path() -> Path:
    """Path of the Inventory SQLite file; relative paths are taken from the project folder."""
    p = Path(setting("INVENTORY_PATH"))
    return p if p.is_absolute() else ROOT / p


_ENGINES: dict = {}


def get_engine(name: str):
    """SQLAlchemy engine for 'sales', 'finance', 'purchasing', 'inventory' or 'dw'.

    Engines are cached, and creating one does not open a connection yet.
    """
    from sqlalchemy import create_engine  # imported here so `import src.common` stays light

    name = name.lower()
    if name not in _ENGINES:
        if name == "inventory":
            url = "sqlite:///" + inventory_path().as_posix()
        else:
            url = setting(f"{name.upper()}_URL")
        _ENGINES[name] = create_engine(url, pool_pre_ping=True)
    return _ENGINES[name]


def dw_available() -> bool:
    """True when the warehouse database answers and has the etl schema (unit 2.01 onwards)."""
    try:
        from sqlalchemy import text

        with get_engine("dw").connect() as con:
            return bool(con.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'etl' AND table_name = 'batch_stage_log'")).first())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------
def money(value) -> Decimal | None:
    """Round to 2 decimals, half up (12.345 -> 12.35). None stays None."""
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Batches (etl.batch is created in unit 2.01)
# ---------------------------------------------------------------------------
def start_batch(watermark_from, watermark_to, note: str = "") -> int:
    """Insert a RUNNING row into etl.batch and return its batch_id."""
    from sqlalchemy import text

    with get_engine("dw").begin() as con:
        return con.execute(text(
            "INSERT INTO etl.batch (watermark_from, watermark_to, started_at, status, note) "
            "VALUES (:f, :t, now(), 'RUNNING', :n) RETURNING batch_id"),
            {"f": watermark_from, "t": watermark_to, "n": note}).scalar_one()


def finish_batch(batch_id: int, status: str = "SUCCESS", rows_loaded=None, amount_loaded=None) -> None:
    """Close a batch with SUCCESS or FAILED and its totals."""
    from sqlalchemy import text

    with get_engine("dw").begin() as con:
        con.execute(text(
            "UPDATE etl.batch SET status = :s, finished_at = now(), "
            "rows_loaded = :r, amount_loaded = :a WHERE batch_id = :b"),
            {"s": status, "r": rows_loaded, "a": amount_loaded, "b": batch_id})


# ---------------------------------------------------------------------------
# Logging and evidence
# ---------------------------------------------------------------------------
STAGE_LOG_FIELDS = ["logged_at", "batch_id", "stage", "table_name", "rows_in", "rows_out",
                    "amount_in", "amount_out", "status", "note"]


def evidence_dir(area: str) -> Path:
    """evidence/<area>/, created if needed (area e.g. '01_sources', '02_etl')."""
    d = EVIDENCE_DIR / area
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_stage(stage: str, table_name: str, rows_in=None, rows_out=None, amount_in=None,
              amount_out=None, status: str = "OK", batch_id=None, area: str = "02_etl",
              note: str = "") -> dict:
    """Record one pipeline step.

    Always appends a line to evidence/<area>/stage_log.csv. When the warehouse is
    up (etl.batch_stage_log exists), the same row is inserted there too.
    """
    row = {
        "logged_at": datetime.now().isoformat(timespec="seconds"),
        "batch_id": batch_id, "stage": stage, "table_name": table_name,
        "rows_in": rows_in, "rows_out": rows_out,
        "amount_in": money(amount_in), "amount_out": money(amount_out),
        "status": status, "note": note,
    }
    path = evidence_dir(area) / "stage_log.csv"
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=STAGE_LOG_FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)

    if batch_id is not None and dw_available():
        from sqlalchemy import text

        with get_engine("dw").begin() as con:
            con.execute(text(
                "INSERT INTO etl.batch_stage_log (batch_id, stage, table_name, rows_in, rows_out, "
                "amount_in, amount_out, status, note, logged_at) VALUES (:batch_id, :stage, "
                ":table_name, :rows_in, :rows_out, :amount_in, :amount_out, :status, :note, now())"),
                {k: v for k, v in row.items() if k != "logged_at"})
    return row


def write_evidence(area: str, filename: str, data) -> Path:
    """Save a DataFrame or a list of dicts as evidence/<area>/<filename> (UTF-8, LF)."""
    path = evidence_dir(area) / filename
    if hasattr(data, "to_csv"):                       # pandas DataFrame
        data.to_csv(path, index=False, lineterminator="\n", encoding="utf-8")
    else:
        rows = list(data)
        fields = list(rows[0].keys()) if rows else []
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    return path
