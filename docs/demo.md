# Demo run-sheet (about 12 minutes)

Synthetic data (seed 472). The demo rebuilds the whole warehouse live, from empty, in seven commands. Each command runs a range of the pipeline steps that `pipeline.ipynb` runs (`src/pipeline.py`). The same seven commands were run in sequence after the headless full run (unit 5.02) and gave the same totals (`evidence/05_validation/headless_run/demo_commands_log.csv`).

Run from the project folder in Git Bash (Windows); on Linux or Colab use `python` instead of `.venv/Scripts/python`.

**Before the demo (not timed):**
- `bash scripts/setup_env.sh` prints `OK` five times.
- Open `powerbi/nuskha.pbip` in Power BI Desktop.
- Open a psql window on the warehouse: `psql postgresql://nuskha:nuskha@localhost:5432/nuskha_dw`.
- Set the shorthand: `PY=.venv/Scripts/python`.

| # | Min | Say | Run | Show on screen |
| --- | --- | --- | --- | --- |
| 1 | 1 | Four departments on three engines, generated from seed 472; empty warehouse created | `$PY -m src.pipeline --mode FULL_REBUILD --to load_sources_stage_1` | `evidence/01_sources/stage1_row_counts.csv` (17 tables; 28,099 receipt lines), `reproducibility.csv` (17/17 identical) |
| 2 | 2 | Batch 1: watermark extract, profile, clean, crosswalk, reject, reconcile | `$PY -m src.pipeline --from extract_batch_1 --to etl_reconcile_1` | `evidence/02_etl/reconciliation_batch_1.csv` (28,238 = 27,543 + 556 + 139), `rejects_vs_ledger.csv`, `profile_before_after.csv`; psql: `SELECT reason_code, count(*) FROM etl.rejects GROUP BY 1 ORDER BY 2 DESC;` |
| 3 | 1 | Load the stars, then rerun unchanged: nothing changes | `$PY -m src.pipeline --from load_batch_1 --to rerun_test` | `evidence/03_warehouse/fact_checks_batch_1.csv`, `rerun_checks.csv` (0 rows written, totals unchanged) |
| 4 | 2 | Batch 2 (corrections, late rows, deletions), SCD Type 1, planned failure and recovery | `$PY -m src.pipeline --from batch_2 --to controlled_failure` | `batch2_checks.csv` (71 updated, 40 late, 3 deletions), `scd1_checks.csv`, `failure_checks.csv` (FAILED, rollback, rerun = clean); psql: `SELECT batch_id, status FROM etl.batch ORDER BY 1;` |
| 5 | 2 | Metadata, lineage; trace the FY2026 card to a till receipt line | `$PY -m src.pipeline --from metadata --to traces` | `evidence/04_metadata_lineage/traces/T5.md` (PKR 6,230,294.70 → 10,721 lines), then `T1.md` (one line to its MySQL row) |
| 6 | 2 | 12 queries, AI, validation, Power BI; one total checked live | `$PY -m src.pipeline --from queries --to powerbi_report` | Power BI: Management Overview, Diagnostic Analysis, AI Insights. psql: `SELECT sum(net_amount_pkr) FROM dw.vw_sales_enriched WHERE fiscal_year='FY2026';` returns 6,230,294.70, the same as the card. Also `evidence/05_validation/validation_results.csv` |
| 7 | 2 | AI: forecast vs baselines, next 3 months, one flag traced | (outputs of step 6) | `evidence/07_ai/forecast_metrics.csv`: ridge 70,806, last-month naive 56,347, seasonal naive 116,207. Say plainly that the model loses to last-month naive. Then `forecast.png`, `anomaly_metrics_injected.csv` (Isolation Forest 0.909 / 0.80) and `anomaly_case_traces.csv` (East Analgesics Sep 2026 → GUL-2026-000427 line 2) |

**Timing:** steps 1–6 take about 3 minutes of machine time in total. Talk over the slower ones: step 1 (generator and two source loads) and step 4 (batch 2).

**Closing line (30 s):** `docs/recommendations.md` gives three decisions, each with its evidence, trace and limitation.

**If something fails live:**
- Every range can be rerun on its own.
- You can also show that step's saved output in `evidence/05_validation/headless_run/pipeline_executed.ipynb`, the executed notebook from the headless run.
