> All data in this project is synthetic (fictional "Nuskha Pharmacies", one generator, seed 472). No real patients, brands or companies.

# Viva guide: Member 4, SQL and BI (criterion C4), AI output tables and recommendations
Draft owner: **Sufyan (DT-038)** (the group confirms the assignment; see report section 10).

You own the six saved views, the 12 analytic queries, the Power BI report, the reconciliation of dashboard totals with SQL, the AI output tables as the report uses them, and the three recommendations.

## 1. Your component in plain words

**What it does.** You turn the warehouse into answers. Six saved SQL views give everyone (Power BI, the 12 queries and both AI models) the same definitions. Twelve queries answer the business questions, each with a result CSV, a chart and a two-line reading. The Power BI report shows them on three pages with date, region and category slicers. Three dashboard totals are checked against warehouse SQL. The AI results are exported to the report, and three recommendations turn the evidence into decisions.

**Why.** Managers do not read fact tables. They need a few correct, consistent numbers and a clear "so what". One set of views means the FY2026 total is the same on the card, in SQL and in the AI input.

**Main pieces:**

- **Views** (`sql/03_views/01..06`, created and checked by `src/views.py`): `vw_sales_enriched` (receipt line with all dimension attributes, cancelled excluded), `vw_sales_product_month`, `vw_purchase_product_month`, `vw_margin_bridge` (price, cost and volume effects), `vw_forecast_features`, `vw_region_category_month`.
- **Queries** (`sql/04_queries/A01..A12.sql`, run by `src/queries.py`): results, charts and `readings.md` in `evidence/06_sql/`.
- **Power BI** (`powerbi/`): `src/powerbi_export.py` writes CSV exports of the views to `powerbi/data/` plus `DATA_DICTIONARY.md` and `reconciliation.csv`; `src/powerbi_model.py` writes the semantic model in TMDL (`powerbi/nuskha.SemanticModel`); `src/powerbi_report.py --validate` writes the report pages in PBIR (`powerbi/nuskha.Report`) and validates them against Microsoft's published schemas. Open `powerbi/nuskha.pbip`; `powerbi/BUILD_GUIDE.md` lists the hand steps.
- **AI output tables:** `ai.model_run`, `ai.forecast_result`, `ai.anomaly_result` (DDL `sql/02_warehouse_ddl/03_meta_and_ai.sql`, filled by `src/ai_run.py`), exported as `powerbi/data/ai_forecast_result.csv` and `ai_anomaly_result.csv`.
- **Recommendations:** `docs/recommendations.md` (R1 purchase budget, R2 Diabetes Care supplier, R3 East Analgesics spike).

## 2. How it connects to the others

- **From Member 2:** the two star schemas. Every view reads `dw.fact_sales` / `dw.fact_purchase` and the dimensions, and filters `WHERE NOT is_cancelled` (the flag Member 2 sets for voids). The "last batch id" on each page comes from `etl.batch` (`powerbi/data/etl_last_batch.csv`).
- **From Member 1, indirectly:** clean PKR amounts and one product/branch identity. A3's seasons, A12's cost rise and the anomaly cases exist because Member 1's generator planted them and the ETL kept them intact.
- **To Member 2 and Member 3 (AI):** `vw_forecast_features` is the forecast's only input (Member 2); `vw_region_category_month` is anomaly detection's only input (Member 3). Their results come back to you through the `ai` tables for the AI Insights page.
- **To Member 3 (validation):** trace T5 starts at your FY2026 card and goes through `vw_sales_enriched`; trace T6 starts at `vw_forecast_features`. Validation check 11 confirms your AI tables have no duplicates after a retry.
- **Reconciliation loop:** your three totals are recomputed in warehouse SQL, so a mistake anywhere upstream would show up as a mismatch on your page.

## 3. Numbers to know

| # | Figure | Source file |
| --- | --- | --- |
| 1 | 6 views, 10/10 view checks; `vw_sales_enriched` net 16,382,871.40 = fact_sales net (not cancelled) | `evidence/06_sql/view_checks.csv` |
| 2 | 12/12 queries PASS (A10 has 3,049 rows, A03 288) | `evidence/06_sql/query_run_log.csv` |
| 3 | Reconciled totals: FY2026 net sales 6,230,294.70; Gulshan-e-Iqbal calendar 2025 745,398.10; Oct 2026 purchases 599,167.14 | `powerbi/reconciliation.csv` |
| 4 | Semantic model: 10 tables, 6 relationships, 11 DAX measures; 3 pages, 11 visuals | `report/report.md` s.7, `powerbi/model_checks.csv` |
| 5 | Report files pass Microsoft's PBIR schemas: 32/32 | `evidence/08_powerbi/report_schema_validation.csv` |
| 6 | A12: Diabetes Care margin 26.8% (Feb 2026) to 17.2% (Mar 2026); cost effect -8,294, price -70, volume +3,782 PKR | `evidence/06_sql/readings.md`, `A12_diabetes_margin_bridge.csv` |
| 7 | A10: Diabetes Care purchase cost 73.8% of selling price (Sep 2025-Feb 2026) vs 83.2% (Mar-Oct 2026) | `evidence/06_sql/readings.md` |
| 8 | A6: FY2025 PKR 4,957,885, FY2026 PKR 6,230,295 (+25.7%) | `evidence/06_sql/readings.md` |
| 9 | A3: Cough and Cold 1.52x its other-month average in Dec-Feb; Analgesics 1.66x, Gastro 1.46x in Aug-Oct | `evidence/06_sql/readings.md` |
| 10 | A5: imports 17.1% of purchases (PKR 2,824,860 of 16,546,049) | `evidence/06_sql/readings.md` |
| 11 | AI tables after retry: 3 model runs, 6 forecast rows, 1,152 anomaly rows (unchanged) | `evidence/07_ai/ai_retry_log.csv` |
| 12 | R1 budget: Nov 2026-Jan 2027 forecast total PKR 1,858,719, range 1,662,735-2,054,703 | `docs/recommendations.md` |

## 4. 15 likely questions with answers

1. **Why saved views instead of writing SQL in each query or in Power BI?**
   One definition, used everywhere. Cancelled lines are excluded once, in the view, so Power BI, the 12 queries and the AI all get the same FY2026 total (6,230,294.70). If a rule changes, we change one view and every consumer follows. `view_checks.csv` proves each view's total equals the fact total.

2. **Why must Sales and Purchasing be summed separately before comparing (A10, A12)?**
   Joining two fact tables directly on product and month would match every sales line with every purchase line of that product-month and multiply amounts. So `vw_sales_product_month` and `vw_purchase_product_month` each sum to product × month first, then the two summaries are joined one-to-one.

3. **Explain the margin bridge.**
   For each product and month vs the previous month: volume effect = change in quantity × last month's unit margin; price effect = this month's quantity × change in ASP; cost effect = -(this month's quantity × change in unit cost). Algebraically these add up exactly to the margin change. Summed over Diabetes Care products for March 2026, cost was -8,294 against -70 for price, so the fall is a cost problem.

4. **The bridge check shows 62,447.16 vs 62,447.39 and still PASS. Why?**
   Each effect is rounded to 2 decimals per product row in the view, and the sum of many rounded values drifts by a few paisa from the rounded margin change. The check allows a tolerance of PKR 1 for this one check (rounding of three terms per row) and 0.005 for every other total (`src/offline_warehouse.py`, `tol`); the unrounded formula adds up exactly.

5. **Why is ASP never stored, and why `DIVIDE` in DAX?**
   Ratios are non-additive: averaging per-row ASPs gives the wrong answer. ASP is always sum(net) / sum(quantity) at whatever level you filter. In DAX, `ASP = DIVIDE([Net Sales], [Units Sold])`, and `DIVIDE` returns blank instead of an error when the denominator is 0 (`model_checks.csv`: no `/` in ratio measures).

6. **Which window functions did you use, and where?**
   `SUM() OVER (ORDER BY ...)` for the year-to-date running total (A6), `AVG() OVER (ROWS 2 PRECEDING)` for the 3-month rolling average (A7), `LAG(1)` and `LAG(12)` for month-on-month and year-on-year growth (A8), `RANK()` with `LAG()` for top-10 rank change (A9), `SUM() OVER ()` for share of total (A2), and `LAG` per product in the margin bridge (A12).

7. **What is the diagnostic finding, and how do you know it is not correlation?**
   Diabetes Care margin fell from 26.8% to 17.2% between February and March 2026. The bridge separates the causes arithmetically, and A10 shows cost went from 73.8% to 83.2% of the selling price while ASP stayed flat. That is a decomposition of the margin itself, not a correlation between two series. We still say what it cannot show: why the supplier's cost rose.

8. **How did you reconcile Power BI with the warehouse?**
   Three totals under the same filters: FY2026 net sales, Gulshan-e-Iqbal net sales in calendar 2025, and October 2026 purchases. `powerbi_export.py` computes each from warehouse SQL and from the exported CSVs: all three match to the paisa (`reconciliation.csv`). The `power_bi_total` column is filled when the report is opened in Power BI Desktop, which the automated build could not run.

9. **Why does Power BI read CSV exports and not the live database?**
   Power BI Desktop could not reach the database from the automated build, and we did not want a hosted service needing accounts (`docs/DECISIONS.md`). The CSVs are exports of the same views from the same batch, so the totals are identical, and the last batch id is shown on every page so a reader knows how fresh the data is.

10. **What is on the three pages?**
    Management Overview: KPI cards, monthly net sales with 3-month rolling average, branch vs last year, category contribution. Diagnostic Analysis: margin % by category, Diabetes Care ASP vs unit cost, the margin bridge, top-10 rank change. AI Insights: forecast vs holdout plus next 3 months, anomaly scatter, flagged-case table with source keys. Each page has date, region and category slicers (AI page: region and category) and shows units and the last batch.

11. **How do the AI tables avoid duplicates when a run is retried?**
    The run id is a hash of the configuration and the data batch, so a retry gets the same run id. `ai.forecast_result` is unique on (run_id, date_key) and `ai.anomaly_result` on (run_id, date_key, region, category, method), and writes are upserts. After the retry the counts were still 3 / 6 / 1,152.

12. **Why are AI results in their own tables and not columns on the fact?**
    A prediction is not a fact about a sale; it belongs to one model run with its parameters and metrics. Keeping them in `ai.*`, linked by `date_key` and region/category values, keeps the facts clean and lets several model versions sit side by side.

13. **Recommendation R1 uses a forecast that loses to last-month naive. Is that defensible?**
    Yes, if said plainly. The ridge MAE (70,806) is worse than last-month naive (56,347), so R1 uses the forecast's range (1.66-2.05 million PKR for three months) for cash planning, not the point value, and says to revise it monthly against the last-month figure. The seasonal weighting towards Cough and Cold comes from A3, not from the model.

14. **What are the other two recommendations and their limits?**
    R2: renegotiate or switch the Diabetes Care supplier, based on A12 and A10, with 4 of the top 10 products being Diabetes Care (A9). Limit: the bridge does not say why cost rose, and margin uses Inventory standard cost. R3: investigate East Analgesics Sep 2026 (PKR 37,584 vs expected 8,767) with Pharmacy Ops. Limit: a flag says a month is unusual, not why, and the evaluation used only 25 injected cases.

15. **Is the query output trustworthy if someone filters by region in Power BI?**
    The relationships are single-direction from dimensions to facts (Date on `full_date`, Product on `product_code`, Branch on `branch_name`), so a region slicer filters both Sales and Purchases through Branch without joining the two facts. Measures are sums and `DIVIDE` ratios, so they stay correct at any filter level. The Gulshan-e-Iqbal 2025 reconciliation is exactly such a filtered total.

## 5. Show me

1. **Queries, AI, validation and Power BI live** (after the earlier demo ranges):
   `.venv/Scripts/python -m src.pipeline --from queries --to powerbi_report`
   Then open `evidence/06_sql/readings.md` and `A12_diabetes_margin_bridge.png`.
2. **The card checked in psql** (`psql postgresql://nuskha:nuskha@localhost:5432/nuskha_dw`):
   ```sql
   SELECT sum(net_amount_pkr) FROM dw.vw_sales_enriched WHERE fiscal_year = 'FY2026';  -- 6,230,294.70
   SELECT month_start, sum(cost_effect_pkr), sum(price_effect_pkr), sum(volume_effect_pkr)
     FROM dw.vw_margin_bridge WHERE category = 'Diabetes Care' AND month_start = '2026-03-01' GROUP BY 1;
   SELECT run_id, task, method FROM ai.model_run;
   ```
3. **Power BI:** open `powerbi/nuskha.pbip` and show the three pages; compare the FY2026 card with `powerbi/reconciliation.csv`.
4. **One query file:** open `sql/04_queries/A08_growth_mom_yoy.sql` (LAG 1 and LAG 12) next to `A08_growth_mom_yoy.csv`.

## Key terms to say correctly

- **Saved view:** a stored SELECT; it holds no data of its own and always reflects the current warehouse.
- **Additive vs non-additive measure:** amounts and quantities can be summed; ASP, unit cost and margin % must be recomputed from sums.
- **Window function:** a calculation over related rows (`OVER (...)`) that keeps every row, e.g. running totals, LAG, RANK.
- **ROLLUP:** GROUP BY extension that adds subtotal and grand-total rows (A5).
- **Margin bridge:** splitting a margin change into volume, price and cost effects that add up to it.
- **Semantic model (TMDL) / report (PBIR):** the Power BI tables, relationships and measures / the pages and visuals, both stored as text files.
- **Reconciled total:** a dashboard figure recomputed in warehouse SQL under the same filters and shown to match.
- **Run id:** hash of model configuration and data batch; identifies one versioned AI run.
