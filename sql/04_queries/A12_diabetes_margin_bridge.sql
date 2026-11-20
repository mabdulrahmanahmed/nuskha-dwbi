-- A12 (Practical 10, diagnostic): why did Diabetes Care margin fall in 2026 - price, cost or
-- volume? (BQ4). Month-on-month margin bridge from vw_margin_bridge summed over the category's
-- products, beside each month's margin %, ASP and unit cost, with running totals of the effects.
-- Grain: category x month (built from product x month). SQL feature: CTEs + window functions.
WITH b AS (
  SELECT month_start,
         SUM(margin_change_pkr)  AS margin_change_pkr,
         SUM(volume_effect_pkr)  AS volume_effect_pkr,
         SUM(price_effect_pkr)   AS price_effect_pkr,
         SUM(cost_effect_pkr)    AS cost_effect_pkr
  FROM dw.vw_margin_bridge
  WHERE category = 'Diabetes Care'
  GROUP BY month_start
),
m AS (
  SELECT month_start,
         SUM(net_amount_pkr) AS net_amount_pkr, SUM(gross_margin_pkr) AS gross_margin_pkr,
         SUM(quantity_units) AS quantity_units, SUM(cost_amount_pkr) AS cost_amount_pkr
  FROM dw.vw_sales_product_month
  WHERE category = 'Diabetes Care'
  GROUP BY month_start
)
SELECT m.month_start,
       m.net_amount_pkr,
       m.gross_margin_pkr,
       ROUND(100 * m.gross_margin_pkr / NULLIF(m.net_amount_pkr, 0), 2) AS margin_pct,
       ROUND(m.net_amount_pkr / NULLIF(m.quantity_units, 0), 2)          AS asp_pkr,
       ROUND(m.cost_amount_pkr / NULLIF(m.quantity_units, 0), 2)         AS unit_cost_pkr,
       b.margin_change_pkr, b.volume_effect_pkr, b.price_effect_pkr, b.cost_effect_pkr,
       SUM(b.cost_effect_pkr)   OVER (ORDER BY m.month_start) AS cumulative_cost_effect_pkr,
       SUM(b.price_effect_pkr)  OVER (ORDER BY m.month_start) AS cumulative_price_effect_pkr,
       SUM(b.volume_effect_pkr) OVER (ORDER BY m.month_start) AS cumulative_volume_effect_pkr
FROM m
LEFT JOIN b ON b.month_start = m.month_start
ORDER BY m.month_start;
