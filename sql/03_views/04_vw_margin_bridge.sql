-- vw_margin_bridge: month-on-month change in gross margin per product, split into
--   volume effect = (qty this month - qty last month) x unit margin last month
--   price effect  = qty this month x (ASP this month - ASP last month)
--   cost effect   = -(qty this month x (unit cost this month - unit cost last month))
-- The three effects add up exactly to the margin change. Summed over products, the volume
-- effect also carries the mix between products. Used by the Diagnostic page and query A12.
CREATE OR REPLACE VIEW dw.vw_margin_bridge AS
WITH m AS (
  SELECT product_key, product_code, generic_name, category, month_start,
         quantity_units AS qty,
         net_amount_pkr, cost_amount_pkr, gross_margin_pkr,
         net_amount_pkr  / NULLIF(quantity_units, 0) AS asp,
         cost_amount_pkr / NULLIF(quantity_units, 0) AS unit_cost
  FROM dw.vw_sales_product_month
),
w AS (
  SELECT m.*,
         LAG(month_start)      OVER (PARTITION BY product_key ORDER BY month_start) AS prev_month,
         LAG(qty)              OVER (PARTITION BY product_key ORDER BY month_start) AS prev_qty,
         LAG(asp)              OVER (PARTITION BY product_key ORDER BY month_start) AS prev_asp,
         LAG(unit_cost)        OVER (PARTITION BY product_key ORDER BY month_start) AS prev_unit_cost,
         LAG(gross_margin_pkr) OVER (PARTITION BY product_key ORDER BY month_start) AS prev_margin_pkr
  FROM m
)
SELECT product_key, product_code, generic_name, category, month_start, prev_month,
       qty, net_amount_pkr, cost_amount_pkr, gross_margin_pkr,
       ROUND(asp, 2)       AS asp_pkr,
       ROUND(unit_cost, 2) AS unit_cost_pkr,
       ROUND(gross_margin_pkr - prev_margin_pkr, 2)              AS margin_change_pkr,
       ROUND((qty - prev_qty) * (prev_asp - prev_unit_cost), 2)  AS volume_effect_pkr,
       ROUND(qty * (asp - prev_asp), 2)                          AS price_effect_pkr,
       ROUND(-qty * (unit_cost - prev_unit_cost), 2)             AS cost_effect_pkr
FROM w
WHERE prev_month IS NOT NULL;
