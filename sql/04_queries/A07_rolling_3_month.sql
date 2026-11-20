-- A7 (Practical 10, rolling average): company net sales with a 3-month rolling average.
-- Grain: month. SQL feature: AVG() OVER (ROWS BETWEEN 2 PRECEDING AND CURRENT ROW).
WITH m AS (
  SELECT month_start, SUM(net_amount_pkr) AS net_sales_pkr
  FROM dw.vw_sales_enriched
  GROUP BY month_start
)
SELECT month_start,
       net_sales_pkr,
       ROUND(AVG(net_sales_pkr) OVER (ORDER BY month_start ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2)
         AS rolling_3m_avg_pkr
FROM m
ORDER BY month_start;
