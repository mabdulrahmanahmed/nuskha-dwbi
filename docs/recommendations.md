# Recommendations (decision support, Q14)

Synthetic data (seed 472). Each recommendation gives the decision, the evidence it rests on, the trace from that evidence back to source rows, and its limitation. Every figure below can be found in the evidence file named next to it.

## R1. Set the Nov 2026 – Jan 2027 purchase budget from the forecast range, weighted towards Cough and Cold

**Decision (Procurement Head, Finance):** budget company-wide sales cover of about **PKR 1.86 million** for Nov 2026 – Jan 2027 (sum of the three monthly forecasts), plan cash for the upper end of the range (**PKR 2.05 million**), and give Cough and Cold a larger share of the December–February stock than its average share.

**Evidence:**
- Forecast (BQ5), `evidence/07_ai/forecast_results.csv`: Nov 2026 PKR 616,975 (range 551,647 – 682,303), Dec 2026 PKR 611,441 (546,113 – 676,769), Jan 2027 PKR 630,303 (564,975 – 695,631). Three-month total 1,858,719; range 1,662,735 – 2,054,703.
- Holdout scores, `evidence/07_ai/forecast_metrics.csv`: ridge MAE PKR 70,806, last-month naive PKR 56,347, seasonal naive PKR 116,207 (Aug–Oct 2026).
- Seasonality, `evidence/06_sql/A03_monthly_category_trend.csv` and `readings.md` (A3): Cough and Cold sells 1.52x its other-month average in December–February.
- Power BI page *AI Insights* (forecast vs holdout plus next 3 months) and *Management Overview* (3-month rolling average).

**Trace:** forecast input `dw.vw_forecast_features` → `dw.fact_sales` rows per month → batches 1 and 2 → MySQL `sales_db.receipt_line` (trace T6, `evidence/04_metadata_lineage/traces/T6.md`). The model run is versioned in `ai.model_run` (`evidence/07_ai/forecast_model_run.csv`).

**Limitation:** the ridge model did **not** beat the last-month naive baseline on the three holdout months, and only 21 training rows are usable once lag-12 is taken. The forecast is therefore used for its range, not as a point target; the budget should be revised monthly against the last-month figure as each new batch is loaded.

## R2. Renegotiate or switch the Diabetes Care supplier

**Decision (Finance Controller, Category Manager):** open supplier negotiations for Diabetes Care products, and get a quote from an alternative distributor, before the next price review. Do not cut prices or run promotions to recover the margin.

**Evidence:**
- Margin bridge (BQ4), `evidence/06_sql/A12_diabetes_margin_bridge.csv` and `readings.md` (A12): margin fell from 26.8% (Feb 2026) to 17.2% (Mar 2026); the cost effect was PKR -8,294 against PKR -70 from price and PKR +3,782 from volume.
- Price vs cost, `evidence/06_sql/A10_price_vs_purchase_cost.csv` (A10): purchase cost took 73.8% of the selling price in Sep 2025 – Feb 2026 and 83.2% in Mar – Oct 2026.
- Weight of the category, `evidence/06_sql/A09_top10_rank_change.csv` (A9): 4 of the top 10 products are Diabetes Care.
- Power BI page *Diagnostic Analysis* (margin % by category, ASP vs unit cost, margin bridge).

**Trace:** `dw.vw_margin_bridge` → `dw.vw_sales_product_month` and `dw.vw_purchase_product_month` (each star summed to product × month first) → `dw.fact_sales` / `dw.fact_purchase` → Inventory standard cost and PostgreSQL `purchasing_db.grn_line` converted at the Finance `fx_rate` of the day (traces T2 and T4).

**Limitation:** the bridge separates price, cost and volume at category level; it does not show *why* the supplier raised its cost (e.g. exchange rate on imported lines vs a list-price change). Gross margin uses standard cost from Inventory, so a supplier that already lowered its price will only show once standard cost is updated.

## R3. Investigate the East Analgesics spike (Sep 2026) with Pharmacy Operations before the next dengue season

**Decision (Internal Audit, Pharmacy Ops):** review September 2026 Analgesics sales at the three East branches (Gulshan-e-Iqbal, Gulistan-e-Jauhar, Malir) to establish whether the jump is an outbreak (then raise seasonal safety stock for the August–October season) or a keying or stock problem. Also review the East region's June 2026 drop, where five of eight categories fell together.

**Evidence:**
- Flags on real data, `evidence/07_ai/anomaly_flags_real.csv`: East / Analgesics / Sep 2026, net sales PKR 37,584 against an expected PKR 8,767 (4.3x the trailing median); flagged by both the robust z-score (z = 10.5) and Isolation Forest.
- Method quality on injected labels, `evidence/07_ai/anomaly_metrics_injected.csv`: Isolation Forest precision 0.909, recall 0.80; robust z precision 0.60, recall 0.24.
- Region-wide drop, `evidence/07_ai/anomaly_region_month_drops.csv` and `anomaly_case_traces.csv`: East, Jun 2026; Gulshan-e-Iqbal sold PKR 5,229 that month against a 6-month average of PKR 67,065.
- Power BI page *AI Insights* (anomaly scatter, flagged-case table with source links).

**Trace:** `evidence/07_ai/anomaly_case_traces.csv` lists the receipt lines behind each flag, with `source_system`, `source_key` (e.g. `GUL-2026-000427|2`) and `batch_id`, so each flag leads straight to a MySQL `sales_db.receipt_line` row.

**Limitation:** a flag says a month is unusual, not why. The data is synthetic and the September spike was planted, so on real data the review must check stock movements and staff records too. The injected test set has about 25 cases, so the precision and recall figures carry wide uncertainty.
