> All data in this project is synthetic (fictional "Nuskha Pharmacies", one generator, seed 472). No real patients, brands or companies.

# Viva guide: Member 3, Lineage and validation (criterion C3) and anomaly detection
Draft owner: **Umer Haroon Mallick (DT-039)** (the group confirms the assignment; see report section 10).

You own the metadata repository, reverse engineering, the six lineage traces, the validation suite and the architecture analysis. Your AI share is anomaly detection.

## 1. Your component in plain words

**What it does.** You make the warehouse explainable and provable. The metadata repository says where every warehouse column comes from and which rule changed it. Lineage links every fact row to the exact source row and batch. The traces walk six figures back to a source row with SQL at every step. The validation suite runs 11 checks, each saved with expected value, actual value and PASS/FAIL. The architecture analysis says, with numbers from our own logs, what works and what is weak. Anomaly detection finds region-category months that moved abnormally.

**Why.** An examiner, auditor or manager asks "where does this number come from, and how do you know it is right?" Your part answers both with evidence instead of trust.

**Main pieces:**

- **Metadata** (`src/metadata.py --load`, content in `config/column_map.csv` and `config/transform_rules.csv`): tables `meta.source_system`, `meta.source_object`, `meta.transform_rule`, `meta.column_map`, plus `meta.lineage` (written by Member 2's loader in the fact transaction). Exported to `evidence/04_metadata_lineage/meta_*.csv`.
- **Reverse engineering** (`src/reverse_engineer.py`): reads each engine's catalogue through SQLAlchemy, writes an ERD and draft DDL per engine. Declared foreign keys are **observed**; links guessed from matching column names are **inferred** (`evidence/04_metadata_lineage/reverse_engineering/`).
- **Traces** (`src/traces.py`, SQL in `sql/05_traces/T1..T6.sql`): results as Markdown in `evidence/04_metadata_lineage/traces/T*.md`.
- **Validation** (`src/validation.py`): `evidence/05_validation/validation_results.csv`, also written to `etl.validation_result`.
- **Architecture analysis:** section 9 of `report/report.md`, each point backed by a figure.
- **Anomaly detection** (`src/anomaly.py`, run by `src/ai_run.py`): reads `dw.vw_region_category_month`; robust z-score vs Isolation Forest; region-wide pattern rule; case review; outputs in `evidence/07_ai/anomaly_*.csv` and `ai.anomaly_result`.

## 2. How it connects to the others

- **From Member 1:** the raw snapshots and staging rows (steps 3 and 4 of trace T1), the transform rule ids (R-DATE-01, R-UNIT-01, R-FX-01, R-XW-PROD...), and the reconciliation figures that your checks 5 and 6 recompute. The source DDL in `sql/01_source_ddl/` is what your reverse-engineered ERDs are compared with.
- **From Member 2:** the stars and `meta.lineage` (one row per fact row), `etl.batch` (watermarks and status used in every trace), the rerun / failure / SCD1 evidence that checks 9 and 10 summarize. You test their grain, foreign keys, unknown members and join safety.
- **From Member 4:** the saved views. Trace T5 starts at the Power BI FY2026 card and goes through `vw_sales_enriched`; T6 starts at `vw_forecast_features`; anomaly detection reads `vw_region_category_month`.
- **To Member 4:** your anomaly flags and case traces feed the AI Insights page (scatter and flagged-case table with source keys) and recommendation R3. Validation check 11 confirms the AI tables Member 4 exports have no duplicates after a retried run.
- **To everyone:** a FAIL in your suite means someone upstream has a bug; the suite is the group's safety net.

## 3. Numbers to know

| # | Figure | Source file |
| --- | --- | --- |
| 1 | Metadata: 4 source systems, 34 source objects, 19 transform rules, 70 column mappings covering all 67 warehouse columns | `evidence/04_metadata_lineage/metadata_checks.csv` |
| 2 | `meta.lineage` 34,738 rows = 29,820 sales + 4,918 purchase rows; coverage 100% on both facts | `metadata_checks.csv`, `evidence/05_validation/headless_run/totals_comparison.csv` |
| 3 | Reverse engineering: Sales 3 observed links, Purchasing 6 observed, Inventory 3 inferred | `report/report.md` s.6, `reverse_engineering/inventory_links.csv` |
| 4 | 6 traces, all PASS, all end at a source row | `evidence/04_metadata_lineage/traces/trace_summary.csv` |
| 5 | T5: FY2026 card PKR 6,230,294.70 = 10,721 fact rows back to MySQL lines | `report/report.md` s.6, `traces/T5.md` |
| 6 | Validation: 11 checks, 27 result rows, all PASS | `evidence/05_validation/validation_results.csv` |
| 7 | Unknown customer: 1 row, 0.003% (limit 1%); 0 orphan keys; 36 of 36 months in both facts | `validation_results.csv` |
| 8 | Join safety: fact_sales 16,400,628.65 and fact_purchase 16,567,538.48 before = after joining every dimension | `validation_results.csv` |
| 9 | Anomaly on 25 injected cases: Isolation Forest 22 flags, 20 true, precision 0.909, recall 0.80; robust z 10 flags, 6 true, 0.60 / 0.24 | `evidence/07_ai/anomaly_metrics_injected.csv` |
| 10 | East / Analgesics / Sep 2026: PKR 37,584 vs expected 8,767 (4.29x trailing median), z = 10.5 | `evidence/07_ai/anomaly_flags_real.csv` |
| 11 | East Jun 2026: 5 of 8 categories down; Gulshan-e-Iqbal PKR 5,229 (5 receipts) vs 6-month average 67,065 | `anomaly_region_month_drops.csv`, `anomaly_case_traces.csv` |
| 12 | `ai.anomaly_result` 1,152 rows, unchanged after the retry | `evidence/07_ai/ai_retry_log.csv` |

## 4. 15 likely questions with answers

1. **What is the difference between metadata and lineage here?**
   Metadata describes structure: which source column feeds which staging and warehouse column, under which rule (`meta.column_map`, `meta.transform_rule`). Lineage is per row: `meta.lineage` says that fact row `sales_db|CLF-2026-000417|1` came from `sales_db.receipt_line` key `CLF-2026-000417|1` in batch 2. Metadata tells you how a column is made; lineage tells you where one number came from.

2. **How do you know the metadata is complete?**
   `src/metadata.py` checks it: every one of the 67 warehouse columns has at least one mapping, 0 mappings point to columns missing from the DDL, and 0 mappings name an unknown rule (`metadata_checks.csv`).

3. **Walk me through trace T1.**
   Six steps: the fact row with its dimension attributes; its `meta.lineage` row joined to `etl.batch` (batch 2, watermarks, SUCCESS); the staging row with normalized values; the raw snapshot CSV `evidence/02_etl/raw/batch_2/sales_db.receipt_line.csv`; the MySQL `sales_db.receipt_line` row; and its header in `sales_db.receipt` (branch text "CLIFTON"). Quantity 2, price 145.00, discount 14.50, net 275.50 are the same at every step.

4. **How does T5 connect the dashboard to the source?**
   It starts from the FY2026 net sales card (PKR 6,230,294.70, 10,721 lines in `vw_sales_enriched`), splits the fact rows by the batch that loaded them (10,694 in batch 1, 27 in batch 2), then bridges from MySQL: 10,902 source lines dated in FY2026, minus 18 lines of voided receipts, minus 164 rejected lines, plus 1 line of a receipt later hard-deleted at the till, equals 10,721 lines and the same PKR total. So the Power BI number, the SQL number and the source number are provably the same.

5. **What is "observed" vs "inferred" in reverse engineering?**
   Observed links are foreign keys declared in the catalogue (Sales MySQL 3, Purchasing PostgreSQL 6). Inventory in SQLite declares no foreign keys, so we infer links where a column name equals another table's primary key: `item_cost_history.item_id`, `stock_count.item_id`, `stock_count.store_code`. They are marked inferred and drawn dashed because nothing in the database enforces them.

6. **Why is "Unknown members below 1%" a check, and why not 0%?**
   Some rows legitimately cannot be resolved, like a panel customer typed as junk, and we load them rather than lose a valid sale. The check makes sure this stays rare and visible: 1 sales row (0.003%) on the Unknown customer, 0 on unknown product, branch or supplier.

7. **What is join safety and why check it?**
   If a dimension had a duplicate key, joining it to the fact would duplicate fact rows and inflate totals. We sum the fact alone, then again after joining every dimension: both stars give the same total (16,400,628.65 and 16,567,538.48), so every join is many-to-one.

8. **Why is the amount check "MySQL valid lines plus deleted receipts kept"?**
   Three receipts were deleted at the source in stage 2, but we keep their fact rows (deletion policy: log, do not auto-delete). So the warehouse holds 6 more rows than the current source. The check adds them back to compare like with like: 0 of 36 months differ.

9. **Your suite is all PASS. Does that prove the warehouse is correct?**
   It proves the properties we test: grain, keys, completeness, reconciliation, lineage, rerun, SCD1, AI duplicates. It cannot prove things we did not test, and the data is synthetic with planted defects, so it shows the methods find what was put there, not real-world mess. That limitation is stated in the report.

10. **Give two architecture strengths and two weaknesses, with numbers.**
    Strengths: reruns are safe (the unchanged rerun and the post-failure rerun both wrote 0 rows); every figure is traceable (100% lineage, 6 traces ending at a source row). Weaknesses: crosswalk upkeep (81 product codes matched by rule or description, not exactly, so each new code needs a rule); dependence on the FX table (USD lines without a rate are rejected as R06). Also a single PostgreSQL instance and batch latency.

11. **Why two anomaly methods?**
    The brief asks for a transparent threshold vs a model. The robust z-score of the ratio to the trailing 6-month median (flag above 3.5) is easy to explain. Isolation Forest (300 trees, contamination 2%, random_state 472) uses three features together: ratio to trailing median, year-on-year ratio and ratio to the category average. On 25 injected cases the forest found 20 with 2 false alerts; the z-score found 6 with 4 false alerts.

12. **How did you evaluate without real labels?**
    We copied the review period (Nov 2025-Oct 2026) and injected 25 spikes and drops with known labels, stored under a separate run id (`<run_id>-injected`) so they never mix with real results. Precision = true flags / all flags, recall = true flags / injected cases. With only 25 cases the figures carry wide uncertainty, which we say.

13. **The Gulshan-e-Iqbal stock-out was not flagged by either method. How did you find it?**
    One closed branch lowers every category of its region by about half, but no single cell crosses z 3.5. So we added a transparent region-wide rule: 5 or more of a region's 8 categories below z -1.5 in the same month. It flags exactly East, June 2026, and the case review traces it to Gulshan-e-Iqbal (PKR 5,229 vs a 6-month average of 67,065).

14. **Why pool the median and MAD over all 24 series?**
    Each series has only about 18 calibration points, so a per-series MAD is unstable. The ratio to the trailing median has no units, so pooling it across series is fair (`docs/DECISIONS.md`). The calibration values are stored in `ai.model_run` (median 1.0669, scaled MAD 0.306).

15. **How is a flag traced to the source?**
    `anomaly_case_traces.csv` lists the receipt lines behind each flagged cell with `source_system`, `source_key` and `batch_id`. For East Analgesics Sep 2026 the top line is `GUL-2026-000427|2` (Naproxen, batch 2), which leads straight to a MySQL `sales_db.receipt_line` row. The keying error traces to `CLF-2026-000185|3`: 80 strips, PKR 30,480.

## 5. Show me

1. **Metadata, reverse engineering and traces live** (after the earlier demo ranges):
   `.venv/Scripts/python -m src.pipeline --from metadata --to traces`
   Then open `evidence/04_metadata_lineage/traces/T5.md` and `T1.md`.
2. **Validation suite:** `.venv/Scripts/python -m src.validation`, then open `evidence/05_validation/validation_results.csv`.
3. **psql lineage lookup** (`psql postgresql://nuskha:nuskha@localhost:5432/nuskha_dw`):
   ```sql
   SELECT l.*, b.status FROM meta.lineage l JOIN etl.batch b USING (batch_id)
    WHERE l.source_key = 'CLF-2026-000417|1';
   SELECT warehouse_table, count(*) FROM meta.lineage GROUP BY 1;
   SELECT rule_id, description FROM meta.transform_rule ORDER BY 1;
   ```
4. **Anomaly evidence:** `evidence/07_ai/anomaly_metrics_injected.csv`, `anomaly_scatter.png`, `anomaly_case_traces.csv`; in psql `SELECT method, count(*) FILTER (WHERE is_flag) FROM ai.anomaly_result WHERE NOT is_injected_copy GROUP BY 1;`

## Key terms to say correctly

- **Metadata repository:** the `meta` schema describing sources, objects, rules and column mappings.
- **Lineage:** per-row link from a warehouse row to its source system, table, key and batch (`meta.lineage`).
- **Trace:** a worked walk from one warehouse figure back to a source row, with the SQL for each step.
- **Observed vs inferred link:** declared foreign key vs a link guessed from matching column names.
- **Join safety:** totals unchanged after joining dimensions, so no join multiplied rows.
- **Robust z-score:** (value - median) / scaled MAD; less affected by outliers than mean and standard deviation.
- **Isolation Forest:** a model that isolates unusual points with random splits; points isolated quickly score as anomalies.
- **Precision / recall:** share of flags that were real / share of real (injected) anomalies that were flagged.
