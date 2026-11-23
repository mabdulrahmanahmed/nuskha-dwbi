# Nuskha DWBI — execution plan for Claude Code

Five phases, 49 work units of 10–15 minutes of Claude Code processing each, about 10.5 hours in total. Every unit ends with an acceptance check. A unit is DONE only when its check passes and its evidence is committed.

- Design source of truth: `docs/blueprint.md`. If this plan and the blueprint disagree, follow this plan and record why in `docs/DECISIONS.md`.
- Rules and the autonomy protocol: `CLAUDE.md`.
- Progress and time left: `python scripts/progress.py status <phase>`.
- Estimates are processing minutes for Claude Code, not human time. `progress.py` rescales the remaining estimate by how fast the finished units actually went.

Column "Needs" lists units that must be DONE first.

**Database-free start.** Units 1.02–1.07 and 1.09 need only Python: the generator writes to `data/generated/` (CSV per table, plus the SQLite Inventory file) and is tested on those files. The person installs MySQL and PostgreSQL in parallel; units 1.01 and 1.08 then create the databases and load the generated data. If Graphviz is not installed yet, 1.09 writes `.dot` files and renders them in 1.08.

**Human steps come last.** The only human step before the run is the setup that starts it (repository, environment, Claude Code sign-in). Every other human step (START_HERE.md, part 4) — the Google Colab run, Power BI Desktop, fixing any blocked unit, the contribution statement, viva preparation — happens after phase 5, followed by one automated closing step. No unit may pause for a person: a unit that cannot finish is marked BLOCKED and its dependents are SKIPPED, and both are handled at the end.

## Phase 1 — Foundation and source systems (9 units, ~115 min)

| ID | Unit | Builds | Acceptance check | Est | Needs |
| --- | --- | --- | --- | --- | --- |
| 1.01 | Environment (after databases are installed) | `scripts/setup_env.sh`, safe to rerun, in two modes: **local** (engines already installed by the person and `config/.env` present: no sudo; only connect with the `.env` users and create `sales_db`, `finance_db`, `purchasing_db`, `nuskha_dw` if missing) and **colab** (apt-install and start MySQL 8 and PostgreSQL, create the `nuskha` users and databases, write `config/.env`); pip-installs `requirements.txt` in both | `python scripts/check_env.py` prints OK for MySQL x2, PostgreSQL x2, SQLite | 15 | 1.07 |
| 1.02 | Repo skeleton | folders from the blueprint, `src/common.py` (engines from `config/.env`, batch ids, `log_stage()`, evidence writer), `README.md` stub, `.gitignore` | `python -c "import src.common"` succeeds without any database running; `config/.env` is git-ignored | 10 | — |
| 1.03 | Source DDL | `sql/01_source_ddl/` for Sales, Purchasing, Inventory (incl. `item_cost_history`), Finance exactly as in the blueprint; `src/create_sources.py` | DDL files written for all four departments; the Inventory DDL runs on SQLite now; the MySQL and PostgreSQL DDL runs in 1.08 | 10 | 1.02 |
| 1.04 | Generator: reference data | `src/generate_sources.py` reference part: 150 items in 8 categories with pack sizes and partial codes, 10 branches with 2–3 spelling variants, 25 suppliers (5 import), 1,200 loyalty members, 15 panel accounts, daily USD/PKR, shelf-price list, standard cost history with the Diabetes Care step-up from Mar 2026 | row counts match the blueprint generator table | 15 | 1.03 |
| 1.05 | Generator: stage 1 transactions | receipts and lines Nov 2023 – Aug 2026 with trend, dengue/flu/Ramadan seasons, customer mix, planted anomalies; purchase orders, GRNs and lines with ~15% USD | ~28k receipt lines, ~4.7k GRN lines; monthly totals chart saved to `evidence/01_sources/` shows trend and seasons | 15 | 1.04 |
| 1.06 | Generator: defects | planted defects R01–R07, D01 exact duplicates, U01 unresolved customers, legitimate repeats, at blueprint rates; `evidence/01_sources/defect_ledger.csv` lists every planted row and code | ledger counts per code within ±10% of target rates | 15 | 1.05 |
| 1.07 | Generator: stage 2 | `--stage 2`: Sep–Oct 2026 rows, corrected quantities and panel customers, late receipts (old date, new `updated_at`), cancellations, 3 receipts hard-deleted, cough-syrup category fix in Inventory | a diff of stage-1 vs stage-2 sources touches only the intended rows (saved as `stage2_diff.csv`) | 15 | 1.06 |
| 1.08 | Load and reproducibility | load generator output into the four sources; build twice from scratch | per-table checksums identical across the two builds (`evidence/01_sources/reproducibility.csv`) | 10 | 1.01, 1.07 |
| 1.09 | Source ERDs | one ERD per department generated from the DDL (graphviz) plus `evidence/01_sources/README.md` | four PNGs exist and open | 10 | 1.03 |

## Phase 2 — Extraction, cleaning and matching (9 units, ~110 min)

| ID | Unit | Builds | Acceptance check | Est | Needs |
| --- | --- | --- | --- | --- | --- |
| 2.01 | Warehouse control tables | schemas `dw`, `stg`, `etl`, `meta`, `ai` in `nuskha_dw`; `etl.batch`, `etl.batch_stage_log`, `etl.rejects`, `etl.deletion_log`, `etl.validation_result` | tables exist; `log_stage()` writes a test row | 10 | 1.02 |
| 2.02 | Extract | `src/extract.py`: transaction tables by `updated_at` watermark (Inventory text dates parsed), master tables in full; raw CSV per table per batch under `evidence/02_etl/raw/batch_<n>/`; counts and amounts logged | logged row counts and amount totals equal source queries | 15 | 1.08, 2.01 |
| 2.03 | Profile before | `src/profile.py`: nulls, distinct branch and category spellings, unit mix, date formats, min/max dates per table | `profile_before.csv` covers every source table | 10 | 2.02 |
| 2.04 | Normalize | `src/normalize.py`: dates, trimmed and standardized text, units to selling units, REAL to NUMERIC, USD to PKR at the rate on or before the receipt date; `stg` tables | no text dates or float money remain in `stg` | 15 | 2.03 |
| 2.05 | Profile after | same profile on `stg`; side-by-side comparison | `profile_before_after.csv` has a pair per table | 10 | 2.04 |
| 2.06 | Crosswalks | `src/crosswalk.py`: `stg.xw_product`, `stg.xw_branch`, `stg.xw_customer` with match method; aliases in `config/branch_aliases.csv`, `config/panel_aliases.csv` | every source key maps to one canonical code or is flagged for rejection | 15 | 2.04 |
| 2.07 | Pre-join checks | key uniqueness, many-to-one crosswalks, row counts before and after each join, written to `etl.validation_result` | all checks PASS | 10 | 2.06 |
| 2.08 | Rejects and duplicates | `src/quality.py`: rejects with reason codes and raw JSON; de-dup on source key only | reject counts per code match `defect_ledger.csv` (differences explained in the CSV); legitimate repeats kept | 15 | 2.07 |
| 2.09 | Reconciliation batch 1 | `evidence/02_etl/reconciliation_batch_1.csv` | for every table: source = staged + rejected + duplicates; amounts equal per month | 10 | 2.08 |

## Phase 3 — Warehouse, batches, metadata and validation (11 units, ~145 min)

| ID | Unit | Builds | Acceptance check | Est | Needs |
| --- | --- | --- | --- | --- | --- |
| 3.01 | Warehouse DDL | `sql/02_warehouse_ddl/` for `dw` stars, `meta` and `ai` tables as in the blueprint | creates cleanly on an empty database | 10 | 2.01 |
| 3.02 | Dimensions | `dim_date` (2023-11-01 to 2027-01-31, fiscal year, Ramadan flag), Unknown (−1) and Walk-in (0) members, dimension upserts in `src/load.py` | every dimension has its special members; business keys unique | 15 | 3.01, 2.09 |
| 3.03 | Facts | fact upserts on natural key, one transaction per fact, lineage columns, `cost_amount_pkr` from the cost effective on the receipt date | fact rows = valid staged rows; Diabetes Care margin falls from Mar 2026 | 15 | 3.02 |
| 3.04 | Rerun test | rerun batch 1 unchanged | 0 rows and 0 totals changed (`evidence/03_warehouse/rerun_log.csv`) | 10 | 3.03 |
| 3.05 | Batch 2 | stage-2 generator, extract by watermark, load; late arrivals; cancellations flagged; key comparison detects the 3 deleted receipts into `etl.deletion_log` | late rows in their real month; cancelled rows excluded from views; 3 deletions logged, none removed | 15 | 3.04 |
| 3.06 | SCD Type 1 | category totals before and after the cough-syrup fix | two category totals move; company total and past margins unchanged (`scd1_evidence.csv`) | 10 | 3.05 |
| 3.07 | Controlled failure | `FAIL_AT=0.5` raises an error halfway through a fact load; then rerun | rollback, FAILED in `etl.batch`, totals unchanged; rerun matches a clean run (`failure_log.csv`) | 10 | 3.05 |
| 3.08 | Metadata repository | fill `meta.source_system`, `source_object`, `column_map` (from `config/column_map.csv`), `transform_rule`, `lineage` | every warehouse column has a mapping; 100% of fact rows have lineage | 15 | 3.05 |
| 3.09 | Reverse engineering | `src/reverse_engineer.py` for Sales (MySQL), Purchasing (PostgreSQL), Inventory (SQLite): ERD + draft DDL, observed vs inferred links | three ERDs and three DDL files under `evidence/04_metadata_lineage/` | 15 | 1.08 |
| 3.10 | Six traces | `sql/05_traces/` for the six traces in the blueprint, with outputs | each trace ends at a source row | 15 | 3.08 |
| 3.11 | Validation suite | the 11 checks in the blueprint into `etl.validation_result` and `evidence/05_validation/validation_results.csv` | all PASS; any failure fixed in its unit and rerun | 15 | 3.07, 3.10 |

## Phase 4 — Analytics, AI and Power BI package (11 units, ~145 min)

| ID | Unit | Builds | Acceptance check | Est | Needs |
| --- | --- | --- | --- | --- | --- |
| 4.01 | Saved views | six views from the blueprint in `sql/03_views/` | each view's total equals the fact total under the same filter | 10 | 3.11 |
| 4.02 | Queries A1–A6 | `sql/04_queries/` with output CSV, chart PNG and a two-line reading each; Practical 9 | all six run on a fresh warehouse | 15 | 4.01 |
| 4.03 | Queries A7–A12 | same for A7–A12; Practical 10; A12 finds the Diabetes Care cost effect | all six run; A12 attributes the drop mostly to cost | 15 | 4.01 |
| 4.04 | Forecast features and baselines | `vw_forecast_features` (SQL window functions); seasonal-naive and last-month baselines | no feature uses the month it predicts (test in `src/forecast.py`) | 10 | 4.01 |
| 4.05 | Forecast model | ridge or gradient boosting; rolling-origin tuning inside training months; holdout Aug–Oct 2026 MAE and RMSE vs both baselines; Nov 2026 – Jan 2027 forecast; `ai.model_run`, `ai.forecast_result` with hashed run id | metrics table saved to `evidence/07_ai/`; forecast rows labelled | 15 | 4.04 |
| 4.06 | Anomaly detection | `vw_region_category_month`; robust z-score rule and Isolation Forest fitted on calibration months, applied to review months; `ai.anomaly_result` | both methods produce flags for the review period | 15 | 4.01 |
| 4.07 | Anomaly evaluation and retry | injected copy with ~25 labelled spikes and drops; precision, recall, false alerts for both methods; three real flags traced to receipt lines; rerun both AI tasks | metrics saved; AI row counts unchanged after retry | 15 | 4.05, 4.06 |
| 4.08 | Power BI data | export each view to `powerbi/data/*.csv` with a data dictionary; `powerbi/reconciliation.csv` with the three SQL totals | CSV totals equal SQL totals | 10 | 4.07 |
| 4.09 | Power BI model | `powerbi/nuskha.pbip` project: semantic model in TMDL reading the CSVs through a `DataFolder` parameter; measures Net Sales, Gross Margin, Margin %, ASP, Purchases | TMDL files parse as text without errors; every measure uses DIVIDE for ratios | 15 | 4.08 |
| 4.10 | Power BI report | report definition with three pages and 11 visuals as in the blueprint, slicers, footer text | report JSON validates against Microsoft's published schema if available; otherwise record the risk in `docs/BLOCKERS.md` | 15 | 4.09 |
| 4.11 | Power BI fallback guide | `powerbi/BUILD_GUIDE.md`: click-by-click build of the same report from the CSVs, about 45 minutes for a person | guide covers every page, visual, measure and the reconciliation | 10 | 4.08 |

## Phase 5 — Notebook, report and handover (9 units, ~120 min)

| ID | Unit | Builds | Acceptance check | Est | Needs |
| --- | --- | --- | --- | --- | --- |
| 5.01 | Colab notebook | `pipeline.ipynb`: setup cell (same as `setup_env.sh`), mode flag FULL_REBUILD or CONTINUE, then every pipeline step in order with short markdown explanations | notebook JSON valid; every cell calls repo code, no logic copied in | 15 | 4.08 |
| 5.02 | Headless full run | execute `pipeline.ipynb` with `jupyter nbconvert --execute` from an empty warehouse, twice | both runs finish; warehouse totals identical; executed copy saved | 15 | 5.01 |
| 5.03 | Recommendations | three recommendations, each with decision, evidence, trace and limitation, in `docs/recommendations.md` | each cites a query, view or AI output that exists | 10 | 4.07 |
| 5.04 | Report part 1 | `report/report.md` sections 1–5 from the report outline in the blueprint, using real numbers from evidence files | every number in the text appears in an evidence file | 15 | 5.02 |
| 5.05 | Report part 2 | sections 6–9 and appendices; contribution statement as a template for the group to fill; build `report/report.docx` and PDF | 8–12 pages excluding appendices | 15 | 5.04 |
| 5.06 | README and evidence index | README with run order and expected counts and totals; `evidence/INDEX.md` mapping every rubric Score-2 item to its file | every rubric item has a file that exists | 10 | 5.05 |
| 5.07 | Demo script | `docs/demo.md`: the 12-minute run-sheet with exact commands and the screen to show at each step | every command in it ran in 5.02 | 10 | 5.02 |
| 5.08 | Viva guides | `docs/viva/member1.md` … `member4.md`: their component in plain words, how it connects to the others, 15 likely questions with answers | one guide per rubric criterion owner | 15 | 5.06 |
| 5.09 | Final audit | check every requirement in the brief and rubric against the repo; fix gaps; tag `v1.0` | `docs/AUDIT.md` shows every item as met, with its file | 15 | 5.08 |

## Closing step — after the end-of-run human steps (~10 min)

Run by `bash scripts/finalize.sh`, once the human steps in `START_HERE.md` part 4 are done. Not tracked as a phase.

1. If `evidence/colab_run.ipynb` exists, confirm its final cell shows the same warehouse totals as the headless run in 5.02, and record the comparison in `evidence/colab_check.csv`. If it does not exist, add it to `docs/AUDIT.md` as missing.
2. If `powerbi/nuskha.pdf` exists, add its pages to report section 7 and the appendix; if `powerbi/nuskha.pbix` exists, list it in `evidence/INDEX.md`.
3. If the human steps fixed any BLOCKED units (`docs/BLOCKERS.md` marked resolved), run `python3 scripts/progress.py retry` and tell the person in the output to run `bash scripts/run_all.sh` once more, then this closing step again.
4. Rebuild `report/report.docx` and the PDF, rerun the final audit from unit 5.09, update `docs/AUDIT.md`, commit, and tag `v1.1`.
