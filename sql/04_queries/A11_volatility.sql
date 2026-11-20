-- A11 (Practical 10, volatility): standard deviation and coefficient of variation of monthly
-- net sales per category. Grain: category. SQL feature: STDDEV_SAMP over a monthly CTE.
WITH m AS (
  SELECT category, month_start, SUM(net_amount_pkr) AS net_sales_pkr
  FROM dw.vw_sales_enriched
  GROUP BY category, month_start
)
SELECT category,
       COUNT(*)                                  AS months,
       ROUND(AVG(net_sales_pkr), 2)              AS mean_monthly_pkr,
       ROUND(STDDEV_SAMP(net_sales_pkr), 2)      AS stddev_monthly_pkr,
       ROUND(STDDEV_SAMP(net_sales_pkr) / NULLIF(AVG(net_sales_pkr), 0), 3) AS coefficient_of_variation
FROM m
GROUP BY category
ORDER BY coefficient_of_variation DESC;
