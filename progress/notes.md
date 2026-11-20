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

## 1.07 Generator: stage 2 (DONE)
- `src/gen/stage2.py` (rng [472,4]): 20 qty fixes, 8 panel-name fixes (all stage-1 U01 receipts), 15 VOIDED receipts, 3 hard-deleted receipts (6 lines), 3 CANCELLED GRNs (9 lines), cough syrup (Dextromethorphan Syrup) Gastro -> 'Cough and Cold' (last_updated 15/09/2026), new item 500 'Paracetamol 1000 mg' PAR-1000-STR on 40 Sep-Oct lines. Edits re-save the header and all its lines (new updated_at).
- `python -m src.generate_sources --stage 2` writes `data/generated/stage2/...`, `evidence/01_sources/defect_ledger_stage2.csv`, `stage2_intended_changes.csv`, `stage2_monthly_totals.{csv,png}`; `stage2/double_export.csv` holds only the stage-2 D01 keys.
- Check: `python -m src.check_generated stage2` writes `stage2_diff.csv` (every differing row, with intended=yes), `stage2_diff_summary.csv` and `stage2_checks.csv` (24/24 PASS).
- Stage 2 totals: 13,833 receipts, 30,417 lines, 1,871 POs, 5,143 GRN lines, 1,096 FX days. Stage 1 output is byte-identical after adding part 4, and both stages reproduce byte-identically on rerun.
- The 3.05 deletion check should find exactly the 3 receipts listed as 'deleted' in `stage2_intended_changes.csv`.

## 1.09 Source ERDs (DONE)
- `src/erd.py`: `parse_ddl()` reads CREATE TABLE statements (columns, types, PK, inline/table-level FKs); writes `evidence/01_sources/erd/<dept>_erd.{dot,png}` and `erd_summary.csv`. Inventory's implied links (item_id, store_code) are dashed "not declared". 3.09 can reuse `parse_ddl`/`draw_matplotlib`/`to_dot`.
- Rendered with matplotlib because Graphviz `dot` is not installed; rerun `python -m src.erd` after installing Graphviz to get Graphviz renders.
- `evidence/01_sources/README.md` indexes every evidence file of this area.

## 1.01 Environment (BLOCKED)
- Written: `scripts/setup_env.sh` (auto, local and colab modes; local only pip-installs the missing packages, then runs `check_env.py --create`), `scripts/check_env.py` (OK/FAIL per DB; `--create` makes missing databases with the .env user), and `scripts/local_db_users_{mysql,postgres}.sql` (one-time person step).
- Blocked: user `nuskha` does not exist on MySQL or PostgreSQL, and `config/.env` is missing. Exact fix in docs/BLOCKERS.md. 1.08 is SKIPPED until then (it needs 1.01).
- jupyter/nbconvert are being pip-installed in the background (slow network); `setup_env.sh` installs them if still missing.
- For 1.08 later: load `data/generated/stage1/` CSVs (Sales with SET FOREIGN_KEY_CHECKS=0 because of R07 orphans), copy `stage1/inventory.db` to INVENTORY_PATH, build twice and compare checksums.
