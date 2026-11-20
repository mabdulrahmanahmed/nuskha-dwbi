-- A8 (Practical 10, growth): month-on-month and year-on-year growth of company net sales.
-- Grain: month. SQL feature: LAG(1) and LAG(12).
WITH m AS (
  SELECT month_start, SUM(net_amount_pkr) AS net_sales_pkr
  FROM dw.vw_sales_enriched
  GROUP BY month_start
),
l AS (
  SELECT month_start, net_sales_pkr,
         LAG(net_sales_pkr, 1)  OVER (ORDER BY month_start) AS prev_month_pkr,
         LAG(net_sales_pkr, 12) OVER (ORDER BY month_start) AS same_month_last_year_pkr
  FROM m
)
SELECT month_start,
       net_sales_pkr,
       prev_month_pkr,
       same_month_last_year_pkr,
       ROUND(100 * (net_sales_pkr / NULLIF(prev_month_pkr, 0) - 1), 1)           AS mom_growth_pct,
       ROUND(100 * (net_sales_pkr / NULLIF(same_month_last_year_pkr, 0) - 1), 1) AS yoy_growth_pct
FROM l
ORDER BY month_start;
