# Evidence index: rubric Score-2 items → files

Synthetic data (seed 472). Every path is relative to the project root and is checked to exist by `python -m src.audit` (result: `evidence/09_report/index_check.csv`).

## C1 Sources and ETL

| Score-2 item | Evidence |
| --- | --- |
| 4 departments on 3 engines | `sql/01_source_ddl/`, `evidence/01_sources/erd/sales_erd.png`, `evidence/01_sources/erd/purchasing_erd.png`, `evidence/01_sources/erd/inventory_erd.png`, `evidence/01_sources/erd/finance_erd.png`, `evidence/01_sources/stage1_row_counts.csv` |
| Reproducible sources | `evidence/01_sources/reproducibility.csv` |
| Cleaning with before/after evidence | `evidence/02_etl/profile_before.csv`, `evidence/02_etl/profile_after.csv`, `evidence/02_etl/profile_before_after.csv`, `config/transform_rules.csv` |
| Crosswalks | `evidence/02_etl/xw_product.csv`, `evidence/02_etl/xw_branch.csv`, `evidence/02_etl/xw_customer.csv`, `evidence/02_etl/crosswalk_match_methods.csv`, `evidence/02_etl/prejoin_checks.csv` |
| Rejects | `evidence/02_etl/rejects.csv`, `evidence/02_etl/rejects_vs_ledger.csv`, `evidence/02_etl/duplicates_removed.csv`, `evidence/09_report/reject_summary.csv` |
| Reconciled counts and amounts | `evidence/02_etl/reconciliation_batch_1.csv`, `evidence/02_etl/reconciliation_amounts_by_month_batch_1.csv`, `evidence/02_etl/reconciliation_batch_2.csv`, `evidence/05_validation/amount_reconciliation_sales_by_month.csv` |
| Unchanged rerun | `evidence/03_warehouse/rerun_checks.csv`, `evidence/03_warehouse/rerun_log.csv` |
| Batch 2 | `evidence/02_etl/extract_log_batch_2.csv`, `evidence/03_warehouse/batch2_checks.csv`, `evidence/03_warehouse/deletion_log_batch_2.csv` |
| Failure recovery | `evidence/03_warehouse/failure_checks.csv`, `evidence/03_warehouse/failure_log.csv` |

## C2 Warehouse

| Score-2 item | Evidence |
| --- | --- |
| Two stars from 3+ departments | `evidence/03_warehouse/star_schema.png`, `sql/02_warehouse_ddl/02_dw_stars.sql`, `report/report.md` (section 4 coverage matrix) |
| Grains passing uniqueness | `evidence/05_validation/validation_results.csv` (check 1), `evidence/03_warehouse/fact_checks_batch_1.csv` |
| Valid keys | `evidence/05_validation/validation_results.csv` (check 2) |
| Date + conformed dimensions | `evidence/03_warehouse/dimension_checks_batch_1.csv`, `sql/02_warehouse_ddl/02_dw_stars.sql` |
| Unknown members | `evidence/05_validation/validation_results.csv` (check 3) |
| SCD Type 1 | `evidence/03_warehouse/scd1_checks.csv`, `evidence/03_warehouse/scd1_evidence.csv`, `evidence/03_warehouse/dim_product_before_batch_2.csv` |
| Measures equal before/after joins | `evidence/05_validation/validation_results.csv` (check 7) |
| DDL runs on an empty database | `evidence/03_warehouse/ddl_empty_database_test.csv` |

## C3 Lineage and validation

| Score-2 item | Evidence |
| --- | --- |
| Metadata repository | `evidence/04_metadata_lineage/meta_source_system.csv`, `evidence/04_metadata_lineage/meta_source_object.csv`, `evidence/04_metadata_lineage/meta_column_map.csv`, `evidence/04_metadata_lineage/meta_transform_rule.csv`, `evidence/04_metadata_lineage/metadata_checks.csv` |
| ERD + DDL per engine (reverse engineering) | `evidence/04_metadata_lineage/reverse_engineering/sales_erd.png`, `evidence/04_metadata_lineage/reverse_engineering/sales_draft_ddl.sql`, `evidence/04_metadata_lineage/reverse_engineering/purchasing_erd.png`, `evidence/04_metadata_lineage/reverse_engineering/purchasing_draft_ddl.sql`, `evidence/04_metadata_lineage/reverse_engineering/inventory_erd.png`, `evidence/04_metadata_lineage/reverse_engineering/inventory_draft_ddl.sql` |
| 6 traces | `evidence/04_metadata_lineage/traces/T1.md` … `evidence/04_metadata_lineage/traces/T6.md`, `evidence/04_metadata_lineage/traces/trace_summary.csv`, `sql/05_traces/` |
| Expected/actual/pass for every check | `evidence/05_validation/validation_results.csv` |
| Evidence-based architecture analysis | `report/report.md` (section 9), `docs/DECISIONS.md` |
| Headless full run, twice, identical | `evidence/05_validation/headless_run/totals_comparison.csv`, `evidence/05_validation/headless_run/pipeline_executed.ipynb` |

## C4 SQL and BI

| Score-2 item | Evidence |
| --- | --- |
| 12 queries with chart and interpretation | `sql/04_queries/`, `evidence/06_sql/readings.md`, `evidence/06_sql/query_run_log.csv`, `evidence/06_sql/A12_diabetes_margin_bridge.png` |
| Saved views | `sql/03_views/`, `evidence/06_sql/view_checks.csv` |
| 3 pages, 10+ visuals, date/region/category filters | `powerbi/nuskha.pbip`, `powerbi/nuskha.Report/`, `evidence/08_powerbi/report_schema_validation.csv`, `powerbi/BUILD_GUIDE.md` |
| 3 reconciled totals | `powerbi/reconciliation.csv` |
| One diagnostic finding | `evidence/06_sql/A12_diabetes_margin_bridge.csv`, `evidence/06_sql/A10_price_vs_purchase_cost.csv` |

## C5 AI

| Score-2 item | Evidence |
| --- | --- |
| Both tasks from SQL views | `sql/03_views/`, `evidence/07_ai/forecast_leakage_test.csv`, `evidence/07_ai/anomaly_feature_check.csv` |
| Baseline vs model MAE/RMSE on 3-month holdout | `evidence/07_ai/forecast_metrics.csv`, `evidence/07_ai/forecast_results.csv`, `evidence/07_ai/forecast.png` |
| Threshold vs model precision/recall on injected labels | `evidence/07_ai/anomaly_metrics_injected.csv`, `evidence/07_ai/anomaly_injected_labels.csv` |
| 3 cases traced | `evidence/07_ai/anomaly_case_traces.csv`, `evidence/07_ai/anomaly_flags_real.csv` |
| Versioned outputs, safe retry | `evidence/07_ai/forecast_model_run.csv`, `evidence/07_ai/anomaly_model_run.csv`, `evidence/07_ai/ai_retry_log.csv` |
| A named decision | `docs/recommendations.md` |

## Deliverables

| Deliverable | File |
| --- | --- |
| Notebook, SQL, README | `pipeline.ipynb`, `sql/`, `README.md` |
| Technical report | `report/report.docx`, `report/report.pdf`, `evidence/09_report/report_pages.csv`, `evidence/09_report/report_numbers_check.csv` |
| Power BI | `powerbi/nuskha.pbip` (`.pbix` is saved by hand: `START_HERE.md` part 4) |
| Demo and viva | `docs/demo.md`, `docs/viva/member1.md`, `docs/viva/member2.md`, `docs/viva/member3.md`, `docs/viva/member4.md` |
