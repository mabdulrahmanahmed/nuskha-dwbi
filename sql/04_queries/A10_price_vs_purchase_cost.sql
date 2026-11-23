-- A10 (Practical 10, relationship): selling price vs purchase unit cost per product and month.
-- Cross-star rule: each star is summed to product x month in its own view first, then the two
-- are joined; joining the fact tables directly would multiply rows.
-- Grain: product x month. SQL feature: two summed CTEs, then a join. Synthetic data.
WITH s AS (
  SELECT product_key, product_code, generic_name, category, month_start, quantity_units, net_amount_pkr
  FROM dw.vw_sales_product_month
),
p AS (
  SELECT product_key, month_start, quantity_units AS purchased_units, purchase_amount_pkr
  FROM dw.vw_purchase_product_month
)
SELECT s.product_code, s.generic_name, s.category, s.month_start,
       s.quantity_units, s.net_amount_pkr, p.purchased_units, p.purchase_amount_pkr,
       ROUND(s.net_amount_pkr / NULLIF(s.quantity_units, 0), 2)          AS asp_pkr,
       ROUND(p.purchase_amount_pkr / NULLIF(p.purchased_units, 0), 2)    AS purchase_unit_cost_pkr,
       ROUND(100 * (1 - (p.purchase_amount_pkr / NULLIF(p.purchased_units, 0))
                        / NULLIF(s.net_amount_pkr / NULLIF(s.quantity_units, 0), 0)), 1) AS price_cost_gap_pct
FROM s
JOIN p ON p.product_key = s.product_key AND p.month_start = s.month_start
ORDER BY s.category, s.product_code, s.month_start;
