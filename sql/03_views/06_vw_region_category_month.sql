-- vw_region_category_month: region x category x month net sales on a complete grid
-- (3 regions x 8 categories x every month; a month with no sales is 0), with the trailing
-- statistics the anomaly detection uses (BQ6):
--   trailing_median_6   median of the 6 previous months (correlated subquery, because
--                       PostgreSQL cannot use percentile_cont as a window function)
--   ratio_to_trailing   value / trailing median
--   yoy_ratio           value / same month last year
--   ratio_to_category   value / average of the 3 regions for the category that month
-- Synthetic data.
CREATE OR REPLACE VIEW dw.vw_region_category_month AS
WITH months AS (
  SELECT DISTINCT d.month_start FROM dw.fact_sales f JOIN dw.dim_date d USING (date_key)
),
grid AS (
  SELECT r.region, c.category, m.month_start
  FROM (SELECT DISTINCT region FROM dw.dim_branch WHERE branch_key > 0) r
  CROSS JOIN (SELECT DISTINCT category FROM dw.dim_product WHERE product_key > 0) c
  CROSS JOIN months m
),
sales AS (
  SELECT b.region, p.category, d.month_start, SUM(f.net_amount_pkr) AS net_sales_pkr, COUNT(*) AS sales_lines
  FROM dw.fact_sales f
  JOIN dw.dim_date d    ON d.date_key = f.date_key
  JOIN dw.dim_branch b  ON b.branch_key = f.branch_key
  JOIN dw.dim_product p ON p.product_key = f.product_key
  WHERE NOT f.is_cancelled
  GROUP BY b.region, p.category, d.month_start
),
base AS (
  SELECT g.region, g.category, g.month_start,
         COALESCE(s.net_sales_pkr, 0) AS net_sales_pkr,
         COALESCE(s.sales_lines, 0)   AS sales_lines
  FROM grid g
  LEFT JOIN sales s ON s.region = g.region AND s.category = g.category AND s.month_start = g.month_start
),
stats AS (
  SELECT b.*,
         (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY p.net_sales_pkr)
            FROM base p
           WHERE p.region = b.region AND p.category = b.category
             AND p.month_start <  b.month_start
             AND p.month_start >= b.month_start - INTERVAL '6 months') AS trailing_median_6,
         LAG(b.net_sales_pkr, 12) OVER (PARTITION BY b.region, b.category ORDER BY b.month_start) AS same_month_last_year,
         AVG(b.net_sales_pkr)     OVER (PARTITION BY b.category, b.month_start)                    AS category_region_avg
  FROM base b
)
SELECT region, category, month_start, net_sales_pkr, sales_lines,
       ROUND(CAST(trailing_median_6 AS NUMERIC), 2)                                         AS trailing_median_6,
       ROUND(CAST(net_sales_pkr / NULLIF(trailing_median_6, 0) AS NUMERIC), 4)              AS ratio_to_trailing,
       ROUND(CAST(net_sales_pkr / NULLIF(same_month_last_year, 0) AS NUMERIC), 4)           AS yoy_ratio,
       ROUND(CAST(net_sales_pkr / NULLIF(category_region_avg, 0) AS NUMERIC), 4)            AS ratio_to_category
FROM stats;
