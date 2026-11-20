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

## 1.04 Generator: reference data (DONE)
- `src/gen/catalogue.py` holds the fixed lists (150 products, 10 branches with till spellings, word lists for fictional names, seasons, Ramadan dates). `src/gen/reference.py` builds the master data with `default_rng([472, 1])`.
- `python -m src.generate_sources --part reference` writes `data/generated/reference/*.csv` (item, branch, branch_name_variant, supplier, loyalty_member, panel_account, panel_name_variant, fx_rate, shelf_price, cost_history, unknown_pos_item, ramadan) and `evidence/01_sources/reference_counts.csv` (13 checks, all PASS).
- Canonical product code is `P-0<item_id>` (column `product_code`); canonical branch code is the Inventory `store_code`. Unknown till codes for R01: MISC-OPEN, DISC-0412-STR, SAMPLE-PCS.
- Venv uses system site-packages (slow network); SQLAlchemy/PyMySQL/graphviz/python-docx are pip-installed into it; jupyter/nbconvert are NOT installed yet (needed by 5.02).

## 1.05 Generator: stage 1 transactions (DONE)
- `src/gen/transactions.py` (rng [472,2]) builds full-history clean receipts/lines, POs/GRNs/lines and quarter-end stock counts, with seasons, trend, customer mix, East Analgesics Sep-2026 spike, BR-GUL Jun-2026 stock-out, keying error (qty 60) and 40 late receipts. `src/gen/sources.py` `materialize(ref, tx, stage)` gives exact source columns per engine format.
- `python -m src.generate_sources --stage 1` (about 50 s) writes `data/generated/stage1/<db>/<table>.csv` and `stage1/inventory.db`, plus `evidence/01_sources/stage1_row_counts.csv`, `stage1_monthly_totals.{csv,png}` and `planted_patterns.csv`.
- Stage 1: 12,789 receipts, 27,821 receipt lines, 1,734 GRNs, 4,797 GRN lines (16% USD), 1,035 FX days. Check: `python -m src.check_generated volumes` gives `stage1_volume_checks.csv` (all PASS).
- Date formats: MySQL 'YYYY-MM-DD HH:MM:SS'; PostgreSQL TIMESTAMPTZ '...+05:00'; Inventory 'DD/MM/YYYY'. CSV empty cell = NULL.

## 1.06 Generator: defects (DONE)
- `src/gen/defects.py` (rng [472,3,stage]) plants R01–R07, D01, U01 and LEGIT_REPEAT in each stage window; ledger rows are keyed `receipt_no|line_no` or `grn_no|line_no`.
- Stage-1 outputs: `evidence/01_sources/defect_ledger.csv` (1,320 rows), `defect_ledger_summary.csv`, and `data/generated/stage1/double_export.csv` (the D01 keys the extract must emit twice).
- Check: `python -m src.check_generated defects` writes `defect_rate_checks.csv`: 30/30 PASS. It checks rates within ±10% AND that the ledger equals the defective rows found independently in the data.
- Stage-1 counts are now 12,767 receipts and 28,099 receipt lines (27,821 + 278 legit repeats); 22 headers were removed for R07. GRN lines 4,801 (4,797 + 4 R06).
- The R06 GRNs are GRN-2023-90001/90002 (PO-2023-90001/90002). Unknown vendor items ZZZ-0001/0002 are in `vendor_item`.
