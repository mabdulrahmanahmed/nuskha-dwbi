-- A5 (Practical 9, comparison): local vs imported purchases in PKR by fiscal quarter, with
-- subtotals per quarter and a grand total. Grain: origin x quarter. SQL feature: GROUP BY ROLLUP.
-- Rows with origin NULL are the quarter subtotals; all three NULL is the grand total.
SELECT d.fiscal_year,
       d.fiscal_quarter,
       s.origin,
       SUM(f.purchase_amount_pkr) AS purchase_amount_pkr,
       COUNT(*)                   AS purchase_lines
FROM dw.fact_purchase f
JOIN dw.dim_date d     ON d.date_key = f.date_key
JOIN dw.dim_supplier s ON s.supplier_key = f.supplier_key
WHERE NOT f.is_cancelled
GROUP BY ROLLUP ((d.fiscal_year, d.fiscal_quarter), s.origin)
ORDER BY d.fiscal_year NULLS LAST, d.fiscal_quarter NULLS LAST, s.origin NULLS LAST;
