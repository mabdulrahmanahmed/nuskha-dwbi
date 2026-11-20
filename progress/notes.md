# Handover notes between units


## 1.02 Repo skeleton (DONE)
- Folders created per blueprint layout: `src/`, `src/gen/`, `sql/01..05_*`, `evidence/01_sources..09_report`, `powerbi/data`, `report/`, `tests/`.
- `src/common.py`: `ROOT`/path constants, `SEED=472`, `load_env()`/`setting()`/`get_engine(name)` (lazy, names: sales, finance, purchasing, inventory, dw), `money()` (half-up 2 dp), `start_batch()`/`finish_batch()`, `log_stage()` (CSV to `evidence/<area>/stage_log.csv`, plus `etl.batch_stage_log` when batch_id given and DW up), `write_evidence()`.
- 2.01 must create `etl.batch` with columns used by `start_batch`/`finish_batch`: batch_id (serial), watermark_from, watermark_to, started_at, finished_at, status, rows_loaded, amount_loaded, note; and `etl.batch_stage_log` with batch_id, stage, table_name, rows_in, rows_out, amount_in, amount_out, status, note, logged_at.
- `data/generated/` is git-ignored (rebuilt from seed). Venv at `.venv` (Windows: `.venv/Scripts/python`).

## 1.03 Source DDL (DONE)
- `sql/01_source_ddl/{sales_mysql,finance_mysql,purchasing_postgres,inventory_sqlite}.sql`: blueprint columns exactly, plus DROP IF EXISTS at the top and synthetic table comments (MySQL COMMENT=, PostgreSQL COMMENT ON, SQLite inline comments).
- `src/create_sources.py`: `create_inventory_file(path)` (no server needed), `create_department(dept)` via engines from `config/.env`; CLI `python -m src.create_sources [dept...] [--sqlite-file X.db]`.
- MySQL/PostgreSQL DDL is untested until 1.08 (no `nuskha` DB users yet). MySQL 9.3 is installed: it may enforce inline REFERENCES, so 1.08 must load Sales with `SET FOREIGN_KEY_CHECKS=0` (planted orphan lines R07).
