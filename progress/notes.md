# Handover notes between units


## 1.02 Repo skeleton (DONE)
- Folders created per blueprint layout: `src/`, `src/gen/`, `sql/01..05_*`, `evidence/01_sources..09_report`, `powerbi/data`, `report/`, `tests/`.
- `src/common.py`: `ROOT`/path constants, `SEED=472`, `load_env()`/`setting()`/`get_engine(name)` (lazy, names: sales, finance, purchasing, inventory, dw), `money()` (half-up 2 dp), `start_batch()`/`finish_batch()`, `log_stage()` (CSV to `evidence/<area>/stage_log.csv`, plus `etl.batch_stage_log` when batch_id given and DW up), `write_evidence()`.
- 2.01 must create `etl.batch` with columns used by `start_batch`/`finish_batch`: batch_id (serial), watermark_from, watermark_to, started_at, finished_at, status, rows_loaded, amount_loaded, note; and `etl.batch_stage_log` with batch_id, stage, table_name, rows_in, rows_out, amount_in, amount_out, status, note, logged_at.
- `data/generated/` is git-ignored (rebuilt from seed). Venv at `.venv` (Windows: `.venv/Scripts/python`).
