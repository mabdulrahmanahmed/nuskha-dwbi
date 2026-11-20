-- vw_sales_product_month: sales summed to product x month (cancelled excluded).
-- One side of the cross-star rule: each star is summed to product x month first, then compared.
-- Ratios (ASP, unit cost, margin %) are recomputed from the sums, never averaged. Synthetic data.
CREATE OR REPLACE VIEW dw.vw_sales_product_month AS
SELECT p.product_key,
       p.product_code,
       p.generic_name,
       p.category,
       d.month_start,
       COUNT(*)                     AS sales_lines,
       SUM(f.quantity_units)        AS quantity_units,
       SUM(f.gross_amount_pkr)      AS gross_amount_pkr,
       SUM(f.discount_pkr)          AS discount_pkr,
       SUM(f.net_amount_pkr)        AS net_amount_pkr,
       SUM(f.cost_amount_pkr)       AS cost_amount_pkr,
       SUM(f.gross_margin_pkr)      AS gross_margin_pkr,
       ROUND(SUM(f.net_amount_pkr) / NULLIF(SUM(f.quantity_units), 0), 2)            AS asp_pkr,
       ROUND(SUM(f.cost_amount_pkr) / NULLIF(SUM(f.quantity_units), 0), 2)           AS std_unit_cost_pkr,
       ROUND(100 * SUM(f.gross_margin_pkr) / NULLIF(SUM(f.net_amount_pkr), 0), 2)    AS margin_pct
FROM dw.fact_sales f
JOIN dw.dim_date d    ON d.date_key = f.date_key
JOIN dw.dim_product p ON p.product_key = f.product_key
WHERE NOT f.is_cancelled
GROUP BY p.product_key, p.product_code, p.generic_name, p.category, d.month_start;
