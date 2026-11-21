# Nuskha Pharmacies: Data Warehouse and BI project (CT-472)

> **All data in this repository is synthetic.** It is produced by one seeded generator
> (seed 472). There is no patient data, no real brand and no real company anywhere.

Nuskha Pharmacies is a fictional 10-branch pharmacy chain in Karachi. Four departmental
source systems (Sales and Finance on MySQL, Purchasing on PostgreSQL, Inventory on SQLite)
feed a PostgreSQL warehouse with two stars (sales and purchases), which in turn feeds
saved SQL views, a Power BI report and two AI tasks (a monthly forecast and anomaly detection).

- Design: [`docs/blueprint.md`](docs/blueprint.md)
- Work plan and acceptance checks: [`docs/PLAN.md`](docs/PLAN.md)
- Decisions and deviations: [`docs/DECISIONS.md`](docs/DECISIONS.md)
- **Start here:** [`START_HERE.md`](START_HERE.md) · evidence map: [`evidence/INDEX.md`](evidence/INDEX.md) · report: [`report/report.pdf`](report/report.pdf)

## Folder layout

| Folder | Holds |
| --- | --- |
| `src/` | Python pipeline code (`common.py` is shared by every step) |
| `src/gen/` | Parts of the synthetic data generator |
| `sql/01_source_ddl/` | DDL of the four source systems |
| `sql/02_warehouse_ddl/` | Warehouse DDL (`dw`, `stg`, `etl`, `meta`, `ai` schemas) |
| `sql/03_views/`, `sql/04_queries/`, `sql/05_traces/` | Saved views, analytic queries A1–A12, lineage traces |
| `config/` | `.env` (git-ignored, connection strings) and mapping/alias CSVs |
| `data/generated/` | Generator output: CSV per source table and the Inventory SQLite file |
| `evidence/` | Logs and outputs of every step, one folder per area |
| `powerbi/` | CSV exports, Power BI project and build guide |
| `report/` | Technical report (`report.md` source, `report.docx`, `report.pdf`) |
| `docs/` | Blueprint, plan, decisions, recommendations, demo run-sheet, viva guides, audit |

## Setup

1. MySQL 8+ and PostgreSQL 14+ running locally (or on Colab: `bash scripts/setup_env.sh colab` installs them).
2. `cp config/.env.example config/.env` and adjust the connection strings if needed.
3. Python 3.11+: `pip install -r requirements.txt` (here: `.venv/Scripts/python`).
4. `bash scripts/setup_env.sh` must print `OK` five times (two MySQL databases, two PostgreSQL databases, SQLite).

## Run order

The whole pipeline is one command, or one notebook (`pipeline.ipynb`, which calls the same steps):

```bash
python -m src.pipeline --mode FULL_REBUILD   # empty warehouse -> everything (about 3 minutes)
python -m src.pipeline --mode CONTINUE       # keep what exists; reruns change nothing
python -m src.pipeline --list                # the 29 steps and their modules
python -m src.headless_run                   # executes pipeline.ipynb twice and compares totals
python -m src.report_build --check           # report.docx / report.pdf + number check
python -m src.audit                          # every file in evidence/INDEX.md and docs/AUDIT.md exists
```

Expected results after each step (from the headless run of 22 Nov 2026; every run gives the same numbers):

| # | Step(s) | Module | Expected after the step |
| --- | --- | --- | --- |
| 1 | generate_stage_1, generate_stage_2 | `src.generate_sources` | Stage 1: 12,767 receipts / 28,099 lines, 1,717 GRNs / 4,683 lines. Stage 2: 13,833 receipts / 30,417 lines, 5,002 GRN lines |
| 2 | create_warehouse | `src.create_warehouse` | Schemas `dw`, `stg`, `etl`, `meta`, `ai` exist and are empty |
| 3 | load_sources_stage_1 | `src.load_sources --stage 1 --twice` | 17/17 source tables with identical checksums across two builds |
| 4 | extract_batch_1 | `src.extract` | Raw snapshot batch 1: receipt_line 28,238 rows (28,099 + 139 double-exported), grn_line 4,706 |
| 5 | etl_*_1 (7 steps) | `src.etl_db` | Batch 1: 635 rejects (all equal the defect ledger); receipt_line 28,238 = 27,543 valid + 556 rejected + 139 duplicates; grn_line 4,706 = 4,604 + 79 + 23 |
| 6 | load_batch_1, check_dims, check_facts | `src.load_db`, `src.dw_checks` | fact_sales 27,543 rows, fact_purchase 4,604; Diabetes Care margin 25.56% -> 16.46% |
| 7 | rerun_test | `src.batch_tests rerun` | 0 rows written, totals unchanged |
| 8 | batch_2 | `src.batch_tests batch2` | 2,428 receipt lines extracted (2,369 loaded, 47 rejected, 12 duplicates); 71 lines updated; 40 late receipts; 3 deletions logged; new product P-0500 |
| 9 | scd1 | `src.batch_tests scd1` | Gastro and Cough and Cold move by 112,316.85 PKR; company total unchanged |
| 10 | controlled_failure | `src.batch_tests failure` | Batch 3 FAILED after 1,184 of 2,369 rows and rolled back; batch 4 SUCCESS, 0 rows written |
| 11 | metadata, reverse_engineer | `src.metadata --load`, `src.reverse_engineer` | 4 systems, 34 objects, 19 rules, 70 column maps; lineage 100% |
| 12 | views, traces | `src.views`, `src.traces` | 6 views, 10/10 view checks; 6 traces each ending at a source row |
| 13 | queries | `src.queries` | 12 result CSVs, charts and readings in `evidence/06_sql/` |
| 14 | ai | `src.ai_run --retry` | forecast_result 6 rows, anomaly_result 1,152 rows, unchanged after retry |
| 15 | validation | `src.validation` | 11 checks, all PASS (`evidence/05_validation/validation_results.csv`) |
| 16 | powerbi_export, powerbi_model, powerbi_report | `src.powerbi_*` | 3 totals PASS; 32/32 report files pass the PBIR schemas |

**Final warehouse totals** (`evidence/05_validation/headless_run/totals_comparison.csv`):

| Measure | Value |
| --- | --- |
| fact_sales rows | 29,820 |
| fact_sales net PKR | 16,400,628.65 |
| fact_sales gross margin PKR | 4,101,635.58 |
| fact_purchase rows | 4,918 |
| fact_purchase PKR | 16,567,538.48 |
| etl.rejects rows | 687 |
| etl.deletion_log rows | 3 |
| meta.lineage rows | 34,738 |
| FY2026 net sales PKR (view) | 6,230,294.70 |
| ai.forecast_result rows | 6 |
| ai.anomaly_result rows | 1,152 |

## Synthetic data

Every table, CSV and chart is synthetic, generated from seed 472 by `src/generate_sources.py`. Product names are generic medicine names; customers are walk-ins, loyalty card numbers and fictional panel companies.
