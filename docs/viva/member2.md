> All data in this project is synthetic (fictional "Nuskha Pharmacies", one generator, seed 472). No real patients, brands or companies.

# Viva guide: Member 2, Warehouse (criterion C2) and the forecast
Draft owner: **Syed Basil Hussain (DT-045)** (the group confirms the assignment; see report section 10).

You own the warehouse DDL, loading the two star schemas, surrogate keys, batch 2, SCD Type 1 and failure recovery. Your AI share is the monthly sales forecast.

## 1. Your component in plain words

**What it does.** You turn Member 1's clean staged rows into two star schemas in PostgreSQL (`nuskha_dw`): `dw.fact_sales` (one row per till receipt line) and `dw.fact_purchase` (one row per goods-receipt line). They share the conformed dimensions Date, Product and Branch; Customer belongs to Sales only and Supplier to Purchasing only. You make loading safe: a rerun changes nothing, a second batch updates rows in place, a half-finished load rolls back completely.

**Why.** Analysts and the dashboard need one place where a sale has one product, one branch, one date and correct PKR measures, and where the numbers do not change just because a job was run twice or crashed halfway.

**Main pieces:**

- **DDL** (`sql/02_warehouse_ddl/01_schemas_and_control.sql`, `02_dw_stars.sql`, `03_meta_and_ai.sql`, run by `src/create_warehouse.py`): schemas `dw`, `stg`, `etl`, `meta`, `ai`; 23 tables. Every dimension has an Unknown member (key -1); `dim_customer` also has Walk-in (key 0). Facts have `UNIQUE (source_system, receipt_no, line_no)` / `(source_system, grn_no, line_no)`.
- **Row builders** (`src/load.py`) and **loader** (`src/load_db.py`): dimensions first, then facts, then `meta.lineage`, then the batch is closed in `etl.batch`. Each load is `INSERT ... ON CONFLICT DO UPDATE ... WHERE (columns) IS DISTINCT FROM (new values)`, so a row is rewritten only when a value really changed.
- **Surrogate keys:** stable integers. `product_key` = Inventory `item_id`, `supplier_key` = `supplier_id`; branch and customer keys are read back from the warehouse and never renumbered. Fact foreign keys are never NULL (an unresolved customer goes to -1).
- **Batch tests** (`src/batch_tests.py rerun | batch2 | scd1 | failure`) and checks (`src/dw_checks.py dims | facts`).
- **Forecast** (`src/forecast.py`, run by `src/ai_run.py`): ridge regression on features built in SQL (`sql/03_views/05_vw_forecast_features.sql`), compared with two naive baselines on a 3-month holdout.

**Evidence:** `evidence/03_warehouse/` (DDL test, load logs, rerun, batch 2, SCD1, failure) and `evidence/07_ai/forecast_*.csv`, `forecast.png`.

## 2. How it connects to the others

- **From Member 1:** staged, crosswalked, validated rows (`src.etl_db.run(batch)`), the canonical codes (`P-0<item_id>`, branch `store_code`, `L-<card>`, `PANEL-<account>`) and the counts of rejects and duplicates. Your fact row count must equal Member 1's "loaded" figure: 27,543 sales rows in batch 1. Member 1's batch-2 extract needs your `etl.batch` row 1 to be SUCCESS so it can read the watermark.
- **To Member 3:** you write `meta.lineage` in the same transaction as the facts (one row per fact row: source system, table, source key, batch). Their traces, the 100% lineage check and the grain / foreign-key / join-safety / rerun / SCD1 validation checks all test your tables. Your DDL also creates the `meta` and `ai` tables they fill.
- **To Member 4:** the stars are what the six saved views read. Views exclude `is_cancelled` rows, which you set. The "last batch id" shown on every Power BI page comes from your `etl.batch`.
- **Forecast link:** it reads Member 4's view `dw.vw_forecast_features` and writes to `ai.model_run` and `ai.forecast_result` (Member 4 exports these to Power BI's AI Insights page and uses the range in recommendation R1).

## 3. Numbers to know

| # | Figure | Source file |
| --- | --- | --- |
| 1 | DDL creates 23 tables; passes on an empty database and on a second run | `evidence/03_warehouse/ddl_empty_database_test.csv` |
| 2 | `dim_date`: 1,188 days (2023-11-01 to 2027-01-31), 89 Ramadan days, fiscal year July-June | `evidence/03_warehouse/dimension_checks_batch_1.csv` |
| 3 | Batch 1: 27,543 sales rows, net PKR 15,070,308.45 (= staged, to the paisa); 4,604 purchase rows | `evidence/03_warehouse/fact_checks_batch_1.csv` |
| 4 | Rerun of batch 1: 0 rows written, all totals and md5 fingerprints unchanged | `evidence/03_warehouse/rerun_checks.csv`, `rerun_log.csv` |
| 5 | Batch 2 load: fact_sales 2,369 sent, 2,277 inserted, 71 updated; fact_purchase 321 sent, 314 inserted, 7 updated; dim_product 1 inserted, 1 updated | `evidence/03_warehouse/load_log_batch_2.csv` |
| 6 | Batch 2: 40 late receipts into Jul-Aug 2026; 31 voided lines flagged; 21 re-saved lines untouched; 3 deleted receipts logged | `evidence/03_warehouse/batch2_checks.csv` |
| 7 | SCD1: Gastro -112,316.85, Cough and Cold +112,316.85, company total unchanged at 16,382,871.40 | `evidence/03_warehouse/scd1_evidence.csv` |
| 8 | Controlled failure: error after 1,184 of 2,369 rows; batch 3 FAILED, batch 4 SUCCESS; totals and md5 unchanged | `evidence/03_warehouse/failure_log.csv` |
| 9 | Final warehouse: 29,820 sales rows (net 16,400,628.65), 4,918 purchase rows (16,567,538.48); identical in two full rebuilds | `evidence/05_validation/headless_run/totals_comparison.csv` |
| 10 | Diabetes Care margin 25.56% (Sep 2025-Feb 2026) to 16.46% (Mar-Aug 2026) | `evidence/03_warehouse/fact_checks_batch_1.csv` |
| 11 | Forecast holdout MAE: ridge 70,806, last-month naive 56,347, seasonal naive 116,207; 21 usable training rows | `evidence/07_ai/forecast_metrics.csv` |
| 12 | Forecast: Nov 2026 616,975 (551,647-682,303), Dec 611,441, Jan 2027 630,303; alpha = 10 | `evidence/07_ai/forecast_results.csv`, `forecast_model_run.csv` |

## 4. 15 likely questions with answers

1. **Why two stars and not one big fact table?**
   Selling and buying are two processes with different grains: a till receipt line vs a goods-receipt line. Putting them in one table would force fake rows or NULL measures. They share Date, Product and Branch, so they can still be compared, but only after each is summed to product × month separately (otherwise the join multiplies rows).

2. **What is the grain of `fact_sales` and how do you enforce it?**
   One row per till receipt line, natural key (source_system, receipt_no, line_no). There is a `UNIQUE` constraint on it, the upsert uses it as the `ON CONFLICT` target, and validation check 1 shows 0 duplicate natural keys.

3. **Why surrogate keys, and why `product_key = item_id`?**
   Surrogate keys decouple the warehouse from source codes, which differ per system (till code, vendor code, item id). We picked stable integers: Inventory's `item_id` is already a clean integer master key, so using it keeps the key deterministic across rebuilds. Branch and customer keys are read back from the warehouse and never renumbered, so a fact never points to a different member after a reload.

4. **Why Unknown (-1) and Walk-in (0) members?**
   Fact foreign keys must never be NULL, or rows drop out of inner joins and totals change. A sale whose panel customer cannot be resolved goes to -1 and is counted: 1 row, 0.003%, against a 1% limit. Walk-in is a real, very common customer type, not an error, so it gets its own member.

5. **Explain your upsert. Why `IS DISTINCT FROM`?**
   `INSERT ... ON CONFLICT (natural key) DO UPDATE SET ... WHERE (old values) IS DISTINCT FROM (new values)`. Without the WHERE, every rerun would rewrite every row. With it, unchanged rows are skipped, which is why the batch-1 rerun wrote 0 rows. `IS DISTINCT FROM` also treats NULL = NULL as equal, unlike `<>`. `batch_id` and `updated_batch_id` are left out of the comparison.

6. **What did batch 2 do with a corrected quantity?**
   The receipt line already exists from batch 1, so the upsert updates it in place on its natural key: 71 stage-1 lines changed (quantity fixes, panel-name fixes and voids). 21 lines were re-saved at the source with only a new `updated_at` and no value change, so they were correctly left untouched.

7. **How do you handle late-arriving facts?**
   A fact loads into its real date, not the load date. The 40 late receipts dated July-August 2026 arrived in batch 2 and went into months 202607 and 202608 (`batch2_checks.csv`). Trace T3 follows one of them (CLF-2026-000308) back to MySQL.

8. **What about deletions and voids?**
   Sources should void, not delete. Voided lines keep their row with `is_cancelled = true` (31 lines) and every view excludes them; 7 cancelled GRN lines are flagged the same way. Three receipts disappeared from the source: a key comparison found exactly those 3, they were logged in `etl.deletion_log`, and their 6 fact rows were kept, not auto-deleted.

9. **What is a late-arriving dimension and where did it happen?**
   A fact whose product is new. Stage 2 adds P-0500 (Paracetamol 1000 mg). Because dimensions load before facts in the same batch, `dim_product` got the new row (1 inserted) before its 40 fact rows arrived, so none fell to Unknown.

10. **Explain your SCD Type 1 demo. Why Type 1 and not Type 2?**
    Dextromethorphan Syrup (P-0368) was filed under Gastro by mistake and corrected to Cough and Cold. That is a correction, not a real change over time, so history is not wanted: Type 1 overwrites the category in place. Only those two category totals moved (±112,316.85) and the company total stayed at 16,382,871.40. If the business wanted "category as it was at the time", we would need Type 2 with effective dates and a new surrogate key per version.

11. **Show how failure recovery works.**
    `FAIL_AT=0.5` makes the fact load raise an error after half the rows (1,184 of 2,369), inside one transaction. PostgreSQL rolls the whole transaction back, the batch is marked FAILED (batch 3), and the row counts, totals and md5 fingerprints are identical to before. The rerun (batch 4) succeeded, matched the clean run and wrote 0 rows because the data was already there.

12. **Why do batches 3 and 4 exist if there are only two loads?**
    The controlled failure and its rerun reload the batch-2 snapshot under their own `etl.batch` rows. That keeps batches 1 and 2 as the two real loads while still showing FAILED → rollback → SUCCESS (`docs/DECISIONS.md`, 3.07).

13. **Which measures are additive, and how is margin computed?**
    Quantity, gross, discount, net, cost and gross margin in PKR are all additive. `cost_amount_pkr` = quantity × Inventory standard cost on the receipt date, and `gross_margin_pkr` = net − cost; the fact check confirms this on every row. Ratios such as ASP and margin % are never stored; they are recomputed from sums. `amount_original` on purchases is additive only within one currency.

14. **Did your forecast beat the baselines? Be honest.**
    No, not both. On the Aug-Oct 2026 holdout the ridge model's MAE was PKR 70,806: better than seasonal naive (116,207) but worse than last-month naive (56,347). With lag-12 only 21 training rows are usable, which is too few for a model to learn much beyond "next month is like last month". We report it as it is, and recommendation R1 uses the forecast range for budgeting, not the point value, revised monthly.

15. **How do you know the forecast has no leakage?**
    Features are built in SQL with window functions: `lag_1`, `lag_12` and `rolling_3_prior` (average of the 3 previous months, excluding the current one). `forecast_leakage_test.csv` checks all three: PASS. The split is by time only (train Nov 2023-Jul 2026, holdout Aug-Oct 2026), alpha was tuned with rolling-origin validation inside training months (alpha 10, RMSE 51,037), and the holdout is forecast recursively three months ahead, like the real Nov-Jan forecast.

## 5. Show me

1. **Batch 2, SCD1 and the failure live** (run after the earlier ranges of `docs/demo.md`):
   `.venv/Scripts/python -m src.pipeline --from batch_2 --to controlled_failure`
   Then open `evidence/03_warehouse/batch2_checks.csv`, `scd1_checks.csv`, `failure_checks.csv`.
2. **psql** (`psql postgresql://nuskha:nuskha@localhost:5432/nuskha_dw`):
   ```sql
   SELECT batch_id, watermark_from, watermark_to, status, note FROM etl.batch ORDER BY 1;
   SELECT count(*), sum(net_amount_pkr) FROM dw.fact_sales;
   SELECT product_key, product_code, generic_name, category FROM dw.dim_product
    WHERE product_key IN (-1, 368, 500);
   SELECT * FROM etl.deletion_log;
   ```
3. **Rerun safety:** in the demo, step 3 (`.venv/Scripts/python -m src.pipeline --from load_batch_1 --to rerun_test`) loads batch 1 and reruns it; then open `evidence/03_warehouse/rerun_log.csv` (every measure and md5 `changed = False`).
4. **Forecast:** `evidence/07_ai/forecast_metrics.csv` and `forecast.png`; `SELECT * FROM ai.forecast_result ORDER BY date_key;`

## Key terms to say correctly

- **Grain:** what one fact row means; here one receipt line or one goods-receipt line.
- **Conformed dimension:** one dimension shared by both stars with the same keys and meaning (Date, Product, Branch).
- **Natural key vs surrogate key:** the source's identifier (source_system, receipt_no, line_no) vs the warehouse's own integer key (`product_key`, `branch_key`...).
- **Upsert:** insert a new row, or update the existing one on the same key, only when a value differs.
- **SCD Type 1:** overwrite the attribute, no history kept; Type 2 would add a new row with effective dates.
- **Late-arriving fact / dimension:** a fact dated in an earlier month loaded now (40 receipts); a new product arriving with its facts (P-0500).
- **Controlled failure:** `FAIL_AT=0.5` makes the fact load fail halfway inside one transaction, to prove the rollback.
- **Naive baselines:** last-month naive = "next month equals this month"; seasonal naive = "equals the same month last year".
