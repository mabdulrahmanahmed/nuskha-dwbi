# Final audit (unit 5.09)

Synthetic data (seed 472). Every requirement in the project brief, as captured in `docs/blueprint.md` (questions Q1–Q14, rubric criteria C1–C5, deliverables), is checked against the repository. Each file named here was checked to exist by `python -m src.audit` (`evidence/09_report/audit_check.csv`). Audit date: 22 Nov 2026, after the headless run and the demo-sequence run.

Status values: **MET** (done and evidenced by the automated build); **MET – human step** (prepared, with a short final action for a person in `START_HERE.md` part 4).

## Brief questions

| Q | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| Q1 | Business questions with user, measure, grain, decision | MET | `report/report.md` (section 1), `docs/blueprint.md` |
| Q2 | Sources: 4 departments on 3 engines, planning matrix | MET | `sql/01_source_ddl/`, `evidence/01_sources/stage1_row_counts.csv`, `evidence/01_sources/erd_summary.csv` |
| Q3 | Extraction, profiling, cleaning with before/after evidence | MET | `evidence/02_etl/extract_log_batch_1.csv`, `evidence/02_etl/profile_before_after.csv` |
| Q4 | Crosswalks, rejects, de-duplication | MET | `evidence/02_etl/crosswalk_match_methods.csv`, `evidence/02_etl/rejects_vs_ledger.csv`, `evidence/02_etl/duplicates_removed.csv` |
| Q5 | Reconciliation of rows and amounts per batch | MET | `evidence/02_etl/reconciliation_batch_1.csv`, `evidence/02_etl/reconciliation_batch_2.csv` |
| Q6 | Dimensional design: grains, measures, conformed dimensions, bus matrix | MET | `evidence/03_warehouse/star_schema.png`, `report/report.md` (section 4) |
| Q7 | Warehouse DDL, loading, batches, rerun, failure recovery, SCD 1 | MET | `sql/02_warehouse_ddl/02_dw_stars.sql`, `evidence/03_warehouse/rerun_checks.csv`, `evidence/03_warehouse/batch2_checks.csv`, `evidence/03_warehouse/failure_checks.csv`, `evidence/03_warehouse/scd1_checks.csv` |
| Q8 | Metadata repository, reverse engineering, lineage traces | MET | `evidence/04_metadata_lineage/metadata_checks.csv`, `evidence/04_metadata_lineage/reverse_engineering/sales_draft_ddl.sql`, `evidence/04_metadata_lineage/traces/trace_summary.csv` |
| Q9 | Validation suite and architecture analysis | MET | `evidence/05_validation/validation_results.csv` (11 checks, all PASS), `report/report.md` (section 9) |
| Q10 | 12 analytic SQL queries with chart and interpretation; saved views | MET | `sql/04_queries/`, `sql/03_views/`, `evidence/06_sql/readings.md`, `evidence/06_sql/view_checks.csv` |
| Q11 | Power BI: 3 pages, 10+ visuals, filters, 3 reconciled totals | MET – human step | `powerbi/nuskha.pbip`, `evidence/08_powerbi/report_schema_validation.csv`, `powerbi/reconciliation.csv`; open once in Power BI Desktop and save `.pbix` (START_HERE part 4, item 1) |
| Q12 | Forecast from SQL features vs baselines on a time-ordered holdout | MET | `evidence/07_ai/forecast_metrics.csv`, `evidence/07_ai/forecast_leakage_test.csv` |
| Q13 | Anomaly detection: threshold vs model on injected labels, 3 cases | MET | `evidence/07_ai/anomaly_metrics_injected.csv`, `evidence/07_ai/anomaly_case_traces.csv` |
| Q14 | Decision support: recommendations with evidence, trace, limitation | MET | `docs/recommendations.md` |

## Rubric (Score 2 items)

| Criterion | Score-2 item | Status | Evidence |
| --- | --- | --- | --- |
| C1 | 4 departments on 3 engines | MET | `evidence/01_sources/stage1_row_counts.csv` |
| C1 | Cleaning with before/after evidence | MET | `evidence/02_etl/profile_before_after.csv` |
| C1 | Crosswalks | MET | `evidence/02_etl/xw_product.csv` |
| C1 | Rejects | MET | `evidence/02_etl/rejects.csv` |
| C1 | Reconciled counts and amounts | MET | `evidence/05_validation/amount_reconciliation_sales_by_month.csv` |
| C1 | Unchanged rerun | MET | `evidence/03_warehouse/rerun_checks.csv` |
| C1 | Batch 2 | MET | `evidence/03_warehouse/batch2_checks.csv` |
| C1 | Failure recovery | MET | `evidence/03_warehouse/failure_checks.csv` |
| C2 | Two stars from 3+ departments | MET | `evidence/03_warehouse/star_schema.png` |
| C2 | Grains pass uniqueness; valid keys; unknown members | MET | `evidence/05_validation/validation_results.csv` (checks 1–3) |
| C2 | Date + conformed dimensions | MET | `evidence/03_warehouse/dimension_checks_batch_1.csv` |
| C2 | SCD Type 1 | MET | `evidence/03_warehouse/scd1_evidence.csv` |
| C2 | Measures equal before/after joins | MET | `evidence/05_validation/validation_results.csv` (check 7) |
| C3 | Metadata repository | MET | `evidence/04_metadata_lineage/meta_column_map.csv` |
| C3 | ERD + DDL per engine | MET | `evidence/04_metadata_lineage/reverse_engineering/purchasing_erd.png`, `evidence/04_metadata_lineage/reverse_engineering/inventory_draft_ddl.sql` |
| C3 | 6 traces | MET | `evidence/04_metadata_lineage/traces/T1.md` … `evidence/04_metadata_lineage/traces/T6.md` |
| C3 | Expected/actual/pass for every check | MET | `evidence/05_validation/validation_results.csv` |
| C3 | Evidence-based architecture analysis | MET | `report/report.md` (section 9) |
| C4 | 12 queries with chart and interpretation | MET | `evidence/06_sql/query_run_log.csv` |
| C4 | Saved views | MET | `evidence/06_sql/view_checks.csv` |
| C4 | 3 pages, 10+ visuals, date/region/category filters | MET – human step | `powerbi/nuskha.Report/`, `powerbi/BUILD_GUIDE.md` |
| C4 | 3 reconciled totals | MET | `powerbi/reconciliation.csv` |
| C4 | One diagnostic finding | MET | `evidence/06_sql/A12_diabetes_margin_bridge.csv` |
| C5 | Both tasks from SQL views | MET | `sql/03_views/05_vw_forecast_features.sql`, `sql/03_views/06_vw_region_category_month.sql` |
| C5 | Baseline vs model MAE/RMSE on 3-month holdout | MET | `evidence/07_ai/forecast_metrics.csv` (model loses to last-month naive; reported honestly) |
| C5 | Threshold vs model precision/recall on injected labels | MET | `evidence/07_ai/anomaly_metrics_injected.csv` |
| C5 | 3 cases traced | MET | `evidence/07_ai/anomaly_case_traces.csv` |
| C5 | Versioned outputs; safe retry | MET | `evidence/07_ai/ai_retry_log.csv`, `evidence/05_validation/validation_results.csv` (check 11) |
| C5 | A named decision | MET | `docs/recommendations.md` |

## Deliverables

| Deliverable | Status | Evidence |
| --- | --- | --- |
| Notebook runs the whole pipeline from empty | MET | `pipeline.ipynb`, `evidence/05_validation/headless_run/totals_comparison.csv` (two runs, 11/11 identical) |
| Same notebook in Google Colab | MET – human step | START_HERE part 4, item 2 (saves evidence/colab_run.ipynb, created by a person) |
| SQL scripts | MET | `sql/` |
| README with run order, expected counts and totals | MET | `README.md` |
| Evidence folders | MET | `evidence/INDEX.md`, `evidence/09_report/index_check.csv` |
| Power BI file | MET – human step | `powerbi/nuskha.pbip` → save as `.pbix` (START_HERE part 4, item 1) |
| Technical report, 8–12 pages excluding appendices | MET | `report/report.pdf`, `evidence/09_report/report_pages.csv` (9 pages), `evidence/09_report/report_numbers_check.csv` |
| Member contribution statement | MET – human step | template in `report/report.md` section 10; names and hours filled by the group |
| Live demo run-sheet | MET | `docs/demo.md`, `evidence/05_validation/headless_run/demo_commands_log.csv` |
| Individual viva preparation | MET | `docs/viva/member1.md`, `docs/viva/member2.md`, `docs/viva/member3.md`, `docs/viva/member4.md` |
| All data synthetic, labelled | MET | `README.md`, `report/report.md`, `src/generate_sources.py` |

## Gaps found and fixed in this audit

- `progress/PROGRESS.md` had not been updated since 20 Nov. It is now rewritten after every unit by `scripts/progress.py report`.
- Validation check 11 (AI outputs after a retry) showed NOT RUN in the committed results. The headless run reran the suite: 11/11 PASS.
- `evidence/03_warehouse/load_log_batch_1.csv` shows the rerun (0 written) because the rerun test reuses batch id 1; the first load is evidenced by `evidence/03_warehouse/fact_checks_batch_1.csv` (`docs/DECISIONS.md`, 5.09).
- The demo used separate module commands that would have left the warehouse half-rebuilt. `src/pipeline.py` gained `--from/--to` ranges, and the demo now uses them (`docs/DECISIONS.md`, 5.07).

## Remaining human steps

All are in `START_HERE.md` part 4:
1. Open `powerbi/nuskha.pbip` and save it as `.pbix`.
2. Run the notebook in Colab.
3. Fill in the contribution statement.
4. Check the open items with the instructor.
5. Run `bash scripts/finalize.sh`.
