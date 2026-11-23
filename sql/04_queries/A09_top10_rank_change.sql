-- A9 (Practical 10, ranking change): top-10 products by net sales in FY2026 and their rank
-- in FY2025 (both complete fiscal years). Grain: product x fiscal year. SQL feature: RANK(), LAG().
WITH s AS (
  SELECT fiscal_year, product_code, generic_name || ' ' || strength AS product, category,
         SUM(net_amount_pkr) AS net_sales_pkr
  FROM dw.vw_sales_enriched
  WHERE fiscal_year IN ('FY2025', 'FY2026')
  GROUP BY fiscal_year, product_code, generic_name, strength, category
),
r AS (
  SELECT s.*, RANK() OVER (PARTITION BY fiscal_year ORDER BY net_sales_pkr DESC) AS sales_rank
  FROM s
),
c AS (
  SELECT r.*, LAG(sales_rank) OVER (PARTITION BY product_code ORDER BY fiscal_year) AS rank_last_year
  FROM r
)
SELECT fiscal_year, sales_rank, product_code, product, category, net_sales_pkr, rank_last_year,
       rank_last_year - sales_rank AS places_gained
FROM c
WHERE fiscal_year = 'FY2026' AND sales_rank <= 10
ORDER BY sales_rank;
