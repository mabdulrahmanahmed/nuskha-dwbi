-- T6 AI input series: one month of vw_forecast_features -> the fact rows of that month.
-- Parameter :month_start e.g. '2026-03-01'. Synthetic data.
-- step: the feature row the model reads
SELECT * FROM dw.vw_forecast_features WHERE month_start = CAST(:month_start AS DATE);
-- step: the fact rows behind it
SELECT count(*) AS lines, sum(f.net_amount_pkr) AS net_sales_pkr, min(f.source_key) AS first_source_key
FROM dw.fact_sales f JOIN dw.dim_date d USING (date_key)
WHERE d.month_start = CAST(:month_start AS DATE) AND NOT f.is_cancelled;
