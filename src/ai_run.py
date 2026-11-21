"""Run both AI tasks and upsert their outputs into the ai schema (units 4.05-4.07). Synthetic data.

  python -m src.ai_run                 # PostgreSQL warehouse -> ai.* tables + evidence/07_ai/
  python -m src.ai_run --retry         # run twice and show that the ai row counts do not change
  python -m src.ai_run --duckdb        # pre-database preview on data/offline_dw.duckdb (a copy
                                       # with ai tables is used, so the retry rule is tested too)

Outputs never go into fact tables. Every write is an upsert on the tables' unique keys:
  ai.model_run (run_id), ai.forecast_result (run_id, date_key),
  ai.anomaly_result (run_id, date_key, region, category, method).
run_id is a hash of the configuration and the data batch, so a retried run rewrites the same
rows instead of adding new ones. The injected evaluation copy has its own run_id ('-injected').
"""
from __future__ import annotations

import shutil
import sys

import pandas as pd

from src import anomaly, forecast
from src.common import DATA_DIR, SQL_DIR, evidence_dir
from src.create_sources import split_statements

UPSERT = {
    "model_run": ("INSERT INTO ai.model_run (run_id, task, method, parameters, training_window, data_batch_id, metrics, "
                  "code_version) VALUES (:run_id, :task, :method, CAST(:parameters AS JSON), :training_window, "
                  ":data_batch_id, CAST(:metrics AS JSON), :code_version) ON CONFLICT (run_id) DO UPDATE SET "
                  "task = EXCLUDED.task, method = EXCLUDED.method, parameters = EXCLUDED.parameters, "
                  "training_window = EXCLUDED.training_window, metrics = EXCLUDED.metrics"),
    "forecast_result": ("INSERT INTO ai.forecast_result (run_id, date_key, prediction, lower, upper, actual, is_holdout) "
                        "VALUES (:run_id, :date_key, :prediction, :lower, :upper, :actual, :is_holdout) "
                        "ON CONFLICT (run_id, date_key) DO UPDATE SET prediction = EXCLUDED.prediction, "
                        "lower = EXCLUDED.lower, upper = EXCLUDED.upper, actual = EXCLUDED.actual, "
                        "is_holdout = EXCLUDED.is_holdout"),
    "anomaly_result": ("INSERT INTO ai.anomaly_result (run_id, date_key, region, category, value, expected, score, "
                       "method, is_flag, is_injected_copy) VALUES (:run_id, :date_key, :region, :category, :value, "
                       ":expected, :score, :method, :is_flag, :is_injected_copy) "
                       "ON CONFLICT (run_id, date_key, region, category, method) DO UPDATE SET value = EXCLUDED.value, "
                       "expected = EXCLUDED.expected, score = EXCLUDED.score, is_flag = EXCLUDED.is_flag, "
                       "is_injected_copy = EXCLUDED.is_injected_copy"),
}


def _records(df: pd.DataFrame, cols: list) -> list:
    out = df[cols].astype(object).where(df[cols].notna(), None)
    return [{k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()} for r in out.to_dict("records")]


def make_writer(execute):
    """execute(sql, list_of_param_dicts) -> None, for PostgreSQL (SQLAlchemy) or DuckDB."""
    def write(task: str, model_run: dict, results: pd.DataFrame) -> None:
        runs = [model_run]
        for rid in sorted(set(results.run_id) - {model_run["run_id"]}):          # e.g. '<id>-injected'
            runs.append({**model_run, "run_id": rid, "task": f"{task} (injected evaluation copy)"})
        execute(UPSERT["model_run"], runs)
        if task == "forecast":
            execute(UPSERT["forecast_result"], _records(results, ["run_id", "date_key", "prediction", "lower", "upper",
                                                                  "actual", "is_holdout"]))
        else:
            execute(UPSERT["anomaly_result"], _records(results, ["run_id", "date_key", "region", "category", "value",
                                                                 "expected", "score", "method", "is_flag",
                                                                 "is_injected_copy"]))
    return write


def counts(query) -> dict:
    return {t: int(query(f"SELECT COUNT(*) FROM ai.{t}")) for t in ("model_run", "forecast_result", "anomaly_result")}


def run_both(run_sql, out_dir, batch_id, writer):
    f = forecast.run(run_sql, out_dir, batch_id, writer)
    a = anomaly.run(run_sql, out_dir, batch_id, writer)
    return f, a


def duckdb_setup():
    """Copy of the offline DuckDB warehouse with the ai tables, so the upserts can be tested."""
    import duckdb

    path = DATA_DIR / "offline_dw_ai.duckdb"
    shutil.copyfile(DATA_DIR / "offline_dw.duckdb", path)
    con = duckdb.connect(str(path))
    ddl = (SQL_DIR / "02_warehouse_ddl" / "03_meta_and_ai.sql").read_text(encoding="utf-8")
    con.execute("CREATE SCHEMA IF NOT EXISTS ai")
    for stmt in split_statements(ddl):
        if "ai." in stmt and not stmt.upper().startswith("COMMENT"):
            # DuckDB has no JSONB (JSON instead) and cannot reference dw.dim_date across this copy's FKs.
            con.execute(stmt.replace("JSONB", "JSON").replace("REFERENCES dw.dim_date", "")
                        .replace("REFERENCES ai.model_run", "").replace("DEFAULT now()", "DEFAULT current_timestamp"))

    def execute(sql, rows):
        import re
        names = re.findall(r":(\w+)", sql.split("VALUES")[1].split("ON CONFLICT")[0])
        q = re.sub(r":(\w+)", "?", sql)
        con.executemany(q, [[r[n] for n in names] for r in rows])
    return con, execute


def main() -> None:
    retry = "--retry" in sys.argv
    if "--duckdb" in sys.argv:
        con, execute = duckdb_setup()
        run_sql = lambda sql: con.execute(sql).df()                       # noqa: E731
        query = lambda sql: con.execute(sql).fetchone()[0]                # noqa: E731
        out_dir, batch_id = evidence_dir("07_ai") / "preview_duckdb", 2
    else:
        from sqlalchemy import text

        from src.common import get_engine

        from src.queries import pg_types

        eng = get_engine("dw")
        run_sql = lambda sql: pg_types(pd.read_sql(text(sql), eng))       # noqa: E731  DATE/NUMERIC -> pandas

        def execute(sql, rows):
            with eng.begin() as c:
                c.execute(text(sql.replace("AS JSON)", "AS JSONB)")), rows)

        def query(sql):
            with eng.connect() as c:
                return c.execute(text(sql)).scalar()
        out_dir = evidence_dir("07_ai")
        batch_id = int(query("SELECT max(batch_id) FROM etl.batch WHERE status = 'SUCCESS'"))
    writer = make_writer(execute)
    f, a = run_both(run_sql, out_dir, batch_id, writer)
    first = counts(query)
    rows = [{"run": "first", **first}]
    if retry or "--duckdb" in sys.argv:
        run_both(run_sql, out_dir, batch_id, writer)
        second = counts(query)
        rows.append({"run": "retry", **second})
    log = pd.DataFrame(rows)
    if len(log) == 2:
        log["unchanged_after_retry"] = log.iloc[:, 1:].nunique().eq(1).all()
    log.to_csv(out_dir / "ai_retry_log.csv", index=False, lineterminator="\n")
    print(f["metrics"].to_string(index=False))
    print(a["metrics"].to_string(index=False))
    print(log.to_string(index=False))


if __name__ == "__main__":
    main()
