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

## Pre-database build (no unit marked DONE; acceptance checks need the databases)
- Pure-pandas ETL written and verified offline: `src/raw.py` (raw snapshot format `evidence/02_etl/raw/batch_<n>/<db>.<table>.csv`, all text; `raw_from_generated()` stand-in), `src/profile.py` (2.03/2.05), `src/normalize.py` (2.04 rules R-DATE/TEXT/CAT/UNIT/MONEY/FX; `convert_purchase_lines()` runs after joins), `src/crosswalk.py` (2.06; config/branch_aliases.csv, config/panel_aliases.csv, config/product_manual_matches.csv), `src/quality.py` (2.07/2.08: dedupe on source key, join log, single reason code by precedence, `accumulate()` keeps headers across batches), `src/load.py` (3.02/3.03 dimension and fact row builders; DB upserts still to add), config/ramadan_dates.csv.
- `python -m src.offline_dry_run` runs batch 1 and batch 2 on the generated sources: 71/71 PASS in `evidence/02_etl/offline_dry_run/dry_run_checks.csv`. Rejects, D01, U01 and LEGIT match both ledgers key for key; rows and amounts reconcile; the Diabetes Care margin falls 25.6% -> 16.5%; 3 deletions, 40 late receipts, SCD1 (only Gastro and Cough and Cold move) and P-0500 all check out.
- Lesson: header tables (receipt, goods_receipt, purchase_order) must be cumulative in stg; a September GRN can belong to an August PO extracted in batch 1.
- When the DB units run: write these frames to `stg.*` and `etl.rejects`, and add upserts in load.py. Surrogate keys: product_key = item_id, supplier_key = supplier_id, branch/customer keys kept stable via the existing key map.
- Also pre-built (untested against servers): `src/load_sources.py` (1.08: drop/create + insert CSV text, Sales with FOREIGN_KEY_CHECKS=0, PG supplier sequence reset, `--twice` writes reproducibility.csv; Inventory path tested: identical checksums), `src/extract.py` (2.02: watermark from etl.batch, PG session TZ Asia/Karachi, values -> source text, D01 re-emit, COUNT/SUM cross-check; Inventory extract text identical to the generated CSVs), `src/create_warehouse.py` + `sql/02_warehouse_ddl/01..03` (2.01 control + crosswalks, 3.01 stars as blueprint, meta, ai), `src/reverse_engineer.py` (3.09; Inventory done: 3 inferred links in evidence/04_metadata_lineage/reverse_engineering/), star diagram `evidence/03_warehouse/star_schema.png` (`python -m src.erd`).
- Analytics and AI, pre-built and checked on DuckDB (`python -m src.offline_warehouse` builds data/offline_dw.duckdb from the dry run; then `--duckdb` flags): `sql/03_views/01..06` (4.01; 9/9 view-total checks), `sql/04_queries/A01..A12` + `src/queries.py` (4.02/4.03; CSV, chart and generated two-line reading each; preview in evidence/06_sql/preview_duckdb/), `src/forecast.py` (4.04/4.05; leakage test PASS, ridge vs seasonal/last-month naive on Aug-Oct holdout, Nov-Jan forecast), `src/anomaly.py` (4.06/4.07; robust z + Isolation Forest; injected evaluation; region-wide drop rule; 3 cases traced), `src/ai_run.py` (upserts into ai.*; the retry keeps row counts unchanged), `src/charts.py` (one chart style).
- 3.08 content: config/column_map.csv (70 mappings; all 67 DW columns covered) and config/transform_rules.csv (19 rules); `python -m src.metadata` checks coverage.
- Power BI (4.08/4.09/4.11 drafts from the DuckDB preview): `src/powerbi_export.py` writes powerbi/data/*.csv, DATA_DICTIONARY.md and reconciliation.csv (3 totals PASS); `src/powerbi_model.py` writes the PBIP semantic model in TMDL (10 tables, 6 relationships, 11 measures, DataFolder parameter; text checks PASS); powerbi/BUILD_GUIDE.md. The report pages (nuskha.Report, 4.10) are NOT written yet, so nuskha.pbip refers to a missing report folder until 4.10.
- When PostgreSQL exists, rerun every one of these without `--duckdb` so that the official evidence comes from the warehouse.

## 1.01 Environment (DONE, 2026-11-22)
- DB access fixed with `scripts/reset_db_access.ps1` (run by the person as Administrator): nuskha/nuskha on MySQL and PostgreSQL; admin logins now root/root and postgres/postgres (local only). `check_env.py` prints OK x5.

## 1.08 Load and reproducibility (DONE)
- `python -m src.load_sources --stage 1 --twice` loads stage-1 CSVs into sales_db, finance_db, purchasing_db and INVENTORY_PATH; `evidence/01_sources/reproducibility.csv`: 17/17 tables identical md5 across two builds.
- Sources now hold stage 1. 3.05 must reload with `--stage 2` before the batch-2 extract.

## Phase 2 (2.01-2.09, DONE 2026-11-22)
- 2.01: `python -m src.create_warehouse 01` (schemas + etl control + crosswalk tables). Test batch truncated so batch 1 = batch_id 1.
- 2.02: `python -m src.extract --to "2026-08-31 23:59:59" --double-export data/generated/stage1/double_export.csv` -> evidence/02_etl/raw/batch_1 (17/17 counts and amounts match). Fixed a NaN-vs-None bug in the amount check. The DB snapshot equals raw_from_generated(1) table for table.
- 2.03-2.09: new `src/etl_db.py` with steps profile-before, stage, profile-after, crosswalk, prejoin, quality, reconcile (`--batch N`). Staging is rebuilt from the immutable raw snapshots (header tables cumulative over batches); `run(batch)` gives stg, xw, valid/rejects/duplicates. stg.* written with NUMERIC money; checks go to etl.validation_result (rerun replaces same check name).
- Batch 1: 635 rejects in etl.rejects, all codes equal the ledger key for key; receipt_line 28,238 = 27,543 valid + 556 rejected + 139 dup; grn_line 4,706 = 4,604 + 79 + 23.
- etl.batch row 1 is still RUNNING: 3.03 must finish_batch(1, 'SUCCESS', ...) after the fact load so batch 2 can use its watermark.

## 3.01-3.07 (DONE 2026-11-22)
- 3.01: full DDL via `python -m src.create_warehouse`; empty-database test (scratch DB nuskha_ddl_test, run twice) in evidence/03_warehouse/ddl_empty_database_test.csv.
- 3.02/3.03: `src/load_db.py` (`--batch N`; temp table + INSERT..ON CONFLICT DO UPDATE WHERE IS DISTINCT FROM; batch_id/updated_batch_id excluded from the comparison; meta.lineage written with the facts; FAIL_AT env; `--new-batch note`). Checks in `src/dw_checks.py dims|facts`. Batch 1: 27,543 sales / 4,604 purchase rows; Diabetes Care margin 25.56% -> 16.46%.
- 3.04-3.07: `src/batch_tests.py rerun|batch2|scd1|failure`. batch2 snapshots dim_product (evidence) and fact_sales (data/snapshots/, git-ignored) before loading, reloads sources with `load_sources --stage 2`, extracts batch 2, runs all etl_db steps, loads, logs 3 deletions.
- Stage-2 facts: 71 lines updated (20 qty + 31 void + 20 panel-receipt lines); 21 re-saved-only lines untouched; 7 CANCELLED GRN lines (not 9 as the old note said); P-0368 Dextromethorphan Syrup Gastro -> Cough and Cold (+/-112,316.85).
- etl.batch now: 1 SUCCESS, 2 SUCCESS, 3 FAILED (controlled failure), 4 SUCCESS (rerun). Sources hold stage 2.

## 3.08-3.11 (DONE)
- 3.08 `python -m src.metadata --load`: meta tables filled (4 systems, 34 source objects, 19 rules, 70 column maps); lineage 100% on both facts.
- 3.09 `python -m src.reverse_engineer`: sales 3 observed links, purchasing 6 observed, inventory 3 inferred.
- 3.10 `python -m src.traces` + sql/05_traces/T1..T6.sql -> evidence/04_metadata_lineage/traces/T*.md (all end at a source row; T5 bridges MySQL lines to the FY2026 card exactly: 10,721 lines, PKR 6,230,294.70).
- Views created early by `python -m src.views` (10/10 checks) — 4.01 can just rerun it.
- 3.11 `python -m src.validation`: 26 PASS, check 11 NOT RUN until the AI units; rerun in 5.09.

## Phase 4 (DONE 2026-11-22)
- 4.01 `python -m src.views` (10/10). 4.02/4.03 `python -m src.queries` -> evidence/06_sql (12/12; A12: cost effect -8,294 vs price -70).
- 4.04-4.07 `python -m src.ai_run --retry` -> evidence/07_ai; ridge MAE 70,806 vs last-month 56,347 vs seasonal 116,207; IF precision 0.909 recall 0.80, robust z 0.60/0.24; 3 planted cases traced; retry unchanged (3/6/1152 rows).
- 4.08 `python -m src.powerbi_export` (3 totals PASS: 6,230,294.70 / 745,398.10 / 599,167.14). 4.09 `python -m src.powerbi_model`. 4.10 `python -m src.powerbi_report --validate` (32/32 schema PASS). 4.11 guide coverage 27/27.
- START_HERE.md does not exist in the repo yet; create it in phase 5 (part 4 = human checklist: open pbip, Colab run, contribution statement).

## 5.02 Headless full run (DONE 2026-11-22)
- `python -m src.headless_run`: nbconvert executes pipeline.ipynb twice with NUSKHA_MODE=FULL_REBUILD (empty warehouse, regenerated sources). Run 1 158.7 s, run 2 166.8 s, 0 cell errors.
- evidence/05_validation/headless_run/totals_comparison.csv: 11/11 identical (fact_sales 29,820 rows / 16,400,628.65 net / 4,101,635.58 margin; fact_purchase 4,918 / 16,567,538.48; rejects 687; deletions 3; lineage 34,738; FY2026 6,230,294.70; forecast 6, anomaly 1,152 rows).
- Warehouse now holds the run-2 state (batches 1 SUCCESS, 2 SUCCESS, 3 FAILED, 4 SUCCESS); validation check 11 now runs (PASS).
- pipeline.py has `--from/--to` ranges (used by docs/demo.md).

## 5.03 Recommendations (DONE)
- docs/recommendations.md: R1 forecast-range budget (Cough and Cold weighting), R2 Diabetes Care supplier (A12 bridge), R3 East Analgesics spike + East Jun drop; each with evidence files, trace, limitation.
