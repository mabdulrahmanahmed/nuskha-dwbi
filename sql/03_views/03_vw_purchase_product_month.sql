-- vw_purchase_product_month: purchases summed to product x month (cancelled GRNs excluded).
-- The other side of the cross-star rule. Purchase unit cost = PKR amount / selling units,
-- recomputed from sums. Original-currency amounts are kept per currency (not additive across them).
CREATE OR REPLACE VIEW dw.vw_purchase_product_month AS
SELECT p.product_key,
       p.product_code,
       p.generic_name,
       p.category,
       d.month_start,
       COUNT(*)                                                             AS purchase_lines,
       SUM(f.quantity_units)                                                AS quantity_units,
       SUM(f.purchase_amount_pkr)                                           AS purchase_amount_pkr,
       SUM(CASE WHEN f.currency_code = 'USD' THEN f.amount_original ELSE 0 END) AS amount_usd,
       SUM(CASE WHEN f.currency_code = 'PKR' THEN f.amount_original ELSE 0 END) AS amount_pkr_original,
       ROUND(SUM(f.purchase_amount_pkr) / NULLIF(SUM(f.quantity_units), 0), 2) AS purchase_unit_cost_pkr
FROM dw.fact_purchase f
JOIN dw.dim_date d    ON d.date_key = f.date_key
JOIN dw.dim_product p ON p.product_key = f.product_key
WHERE NOT f.is_cancelled
GROUP BY p.product_key, p.product_code, p.generic_name, p.category, d.month_start;
