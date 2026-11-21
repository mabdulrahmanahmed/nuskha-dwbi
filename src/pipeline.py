"""The whole pipeline as an ordered list of steps (used by pipeline.ipynb and the demo). Synthetic data.

Every step runs one of the repo's command-line modules in a subprocess, so the notebook holds no
logic of its own. Modes:
  FULL_REBUILD  drop the warehouse schemas and the batch evidence, regenerate the sources from
                seed 472 and run every step from an empty warehouse
  CONTINUE      keep what exists; steps that would start a NEW batch (extracts, the controlled
                failure) are skipped when their batch already exists; every other step is an
                idempotent upsert or a check, so running it again changes nothing

  python -m src.pipeline --mode FULL_REBUILD     # everything, from an empty warehouse
  python -m src.pipeline --mode CONTINUE
  python -m src.pipeline --list                  # show the steps
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time

import pandas as pd

from src.common import EVIDENCE_DIR, ROOT, get_engine

CUT1 = "2026-08-31 23:59:59"
# (step name, what it does, module arguments, skip-in-CONTINUE condition name or None)
STEPS = [
    ("generate_stage_1", "Generator: reference data + stage-1 sources (Nov 2023 - Aug 2026)",
     ["src.generate_sources", "--stage", "1"], "full_only"),
    ("generate_stage_2", "Generator: stage-2 sources (Sep - Oct 2026, corrections, deletions)",
     ["src.generate_sources", "--stage", "2"], "full_only"),
    ("create_warehouse", "Warehouse DDL: schemas dw, stg, etl, meta, ai", ["src.create_warehouse"], None),
    ("load_sources_stage_1", "Load stage 1 into MySQL, PostgreSQL, SQLite (twice, checksums compared)",
     ["src.load_sources", "--stage", "1", "--twice"], "batch_1"),
    ("extract_batch_1", "Extract batch 1 by watermark into a raw snapshot",
     ["src.extract", "--to", CUT1, "--double-export", "data/generated/stage1/double_export.csv"], "batch_1"),
    *[(f"etl_{s}_1", f"ETL batch 1: {s.replace('-', ' ')}", ["src.etl_db", s, "--batch", "1"], None)
      for s in ("profile-before", "stage", "profile-after", "crosswalk", "prejoin", "quality", "reconcile")],
    ("load_batch_1", "Load batch 1 into the stars (dimensions, facts, lineage)", ["src.load_db", "--batch", "1"],
     "batch_2"),
    ("check_dims", "Dimension checks", ["src.dw_checks", "dims", "--batch", "1"], "batch_2"),
    ("check_facts", "Fact checks (rows, amounts, Diabetes Care margin)", ["src.dw_checks", "facts", "--batch", "1"],
     "batch_2"),
    ("rerun_test", "Rerun batch 1 unchanged: 0 rows change", ["src.batch_tests", "rerun"], "batch_2"),
    ("batch_2", "Stage-2 sources, extract batch 2, ETL, load, deletion check", ["src.batch_tests", "batch2"], None),
    ("scd1", "SCD Type 1 category totals before / after", ["src.batch_tests", "scd1"], None),
    ("controlled_failure", "FAIL_AT=0.5 rollback and clean rerun", ["src.batch_tests", "failure"], "failure_done"),
    ("metadata", "Metadata repository and lineage coverage", ["src.metadata", "--load"], None),
    ("reverse_engineer", "Reverse engineering: MySQL, PostgreSQL, SQLite", ["src.reverse_engineer"], None),
    ("views", "Saved views and their total checks", ["src.views"], None),
    ("traces", "Six traces to a source row", ["src.traces"], None),
    ("queries", "Analytic queries A1-A12 with charts and readings", ["src.queries"], None),
    ("ai", "Forecast and anomaly detection, run twice (retry)", ["src.ai_run", "--retry"], None),
    ("validation", "Validation suite (11 checks)", ["src.validation"], None),
    ("powerbi_export", "Power BI CSVs and reconciliation", ["src.powerbi_export"], None),
    ("powerbi_model", "Power BI semantic model (TMDL)", ["src.powerbi_model"], None),
    ("powerbi_report", "Power BI report (PBIR), schema-validated", ["src.powerbi_report", "--validate"], None),
]


def _scalar(sql: str):
    from sqlalchemy import text

    try:
        with get_engine("dw").connect() as con:
            return con.execute(text(sql)).scalar()
    except Exception:
        return None


def already_done(condition: str | None, mode: str) -> bool:
    if condition is None or mode == "FULL_REBUILD":
        return False
    if condition == "full_only":
        return True
    if condition == "batch_1":
        return bool(_scalar("SELECT count(*) FROM etl.batch WHERE batch_id = 1"))
    if condition == "batch_2":
        return bool(_scalar("SELECT count(*) FROM etl.batch WHERE batch_id = 2"))
    if condition == "failure_done":
        return bool(_scalar("SELECT count(*) FROM etl.batch WHERE status = 'FAILED'"))
    raise ValueError(condition)


def reset() -> None:
    """FULL_REBUILD: empty warehouse, no batch evidence left from earlier runs (raw snapshots included)."""
    from sqlalchemy import text

    with get_engine("dw").begin() as con:
        con.execute(text("DROP SCHEMA IF EXISTS ai, meta, dw, stg, etl CASCADE"))
    for p in [EVIDENCE_DIR / "02_etl" / "raw", ROOT / "data" / "snapshots"]:
        shutil.rmtree(p, ignore_errors=True)
    for p in EVIDENCE_DIR.glob("*/stage_log.csv"):
        p.unlink()
    print("warehouse schemas dropped; raw snapshots, snapshots and stage logs removed")


def run_step(name: str, mode: str = "CONTINUE", quiet: bool = True) -> dict:
    step = next(s for s in STEPS if s[0] == name)
    _, what, args, cond = step
    if already_done(cond, mode):
        print(f"[skip] {name}: {what} (already done)")
        return {"step": name, "status": "SKIPPED", "seconds": 0}
    t0 = time.time()
    res = subprocess.run([sys.executable, "-m", *args], cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    secs = round(time.time() - t0, 1)
    out = (res.stdout + res.stderr).strip().splitlines()
    status = "OK" if res.returncode == 0 else "FAILED"
    print(f"[{status}] {name}: {what} ({secs} s)")
    for line in (out[-12:] if quiet else out):
        print("    " + line)
    if res.returncode != 0:
        raise RuntimeError(f"step {name} failed (exit {res.returncode})")
    return {"step": name, "status": status, "seconds": secs}


def totals() -> pd.DataFrame:
    """Final warehouse totals (compared between runs in 5.02 and with the Colab run)."""
    from sqlalchemy import text

    sql = {
        "fact_sales rows": "SELECT count(*) FROM dw.fact_sales",
        "fact_sales net PKR": "SELECT sum(net_amount_pkr) FROM dw.fact_sales",
        "fact_sales gross margin PKR": "SELECT sum(gross_margin_pkr) FROM dw.fact_sales",
        "fact_purchase rows": "SELECT count(*) FROM dw.fact_purchase",
        "fact_purchase PKR": "SELECT sum(purchase_amount_pkr) FROM dw.fact_purchase",
        "etl.rejects rows": "SELECT count(*) FROM etl.rejects",
        "etl.deletion_log rows": "SELECT count(*) FROM etl.deletion_log",
        "meta.lineage rows": "SELECT count(*) FROM meta.lineage",
        "FY2026 net sales PKR (view)": "SELECT sum(net_amount_pkr) FROM dw.vw_sales_enriched WHERE fiscal_year = 'FY2026'",
        "ai.forecast_result rows": "SELECT count(*) FROM ai.forecast_result",
        "ai.anomaly_result rows": "SELECT count(*) FROM ai.anomaly_result",
    }
    with get_engine("dw").connect() as con:
        rows = [{"measure": k, "value": str(con.execute(text(s)).scalar())} for k, s in sql.items()]
    return pd.DataFrame(rows)


def run_all(mode: str) -> pd.DataFrame:
    if mode == "FULL_REBUILD":
        reset()
    log = [run_step(name, mode) for name, *_ in STEPS]
    return pd.DataFrame(log)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=["FULL_REBUILD", "CONTINUE"], default="CONTINUE")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list:
        for name, what, args, _ in STEPS:
            print(f"{name:24s} python -m {' '.join(args)}")
    else:
        print(run_all(a.mode).to_string(index=False))
        print(totals().to_string(index=False))
