-- A6 (Practical 9, contribution over time): fiscal-year-to-date running net sales.
-- Grain: month. SQL feature: SUM() OVER (PARTITION BY fiscal_year ORDER BY month).
WITH m AS (
  SELECT fiscal_year, month_start, SUM(net_amount_pkr) AS net_sales_pkr
  FROM dw.vw_sales_enriched
  GROUP BY fiscal_year, month_start
)
SELECT fiscal_year,
       month_start,
       net_sales_pkr,
       SUM(net_sales_pkr) OVER (PARTITION BY fiscal_year ORDER BY month_start
                                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS ytd_net_sales_pkr
FROM m
ORDER BY month_start;
