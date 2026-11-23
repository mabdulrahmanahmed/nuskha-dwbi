-- T5 Dashboard total: the FY2026 net sales card -> view -> fact rows -> batches (then source rows).
-- Synthetic data.
-- step: the card (what Power BI shows)
SELECT fiscal_year, sum(net_amount_pkr) AS net_sales_pkr, count(*) AS lines
FROM dw.vw_sales_enriched WHERE fiscal_year = 'FY2026' GROUP BY fiscal_year;
-- step: the same total from the fact rows, split by the batch that loaded them
SELECT f.batch_id, count(*) AS lines, sum(f.net_amount_pkr) AS net_sales_pkr
FROM dw.fact_sales f JOIN dw.dim_date d USING (date_key)
WHERE d.fiscal_year = 'FY2026' AND NOT f.is_cancelled GROUP BY f.batch_id ORDER BY f.batch_id;
