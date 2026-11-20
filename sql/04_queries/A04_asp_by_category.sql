-- A4 (Practical 9, average selling price): ASP per selling unit by category and month.
-- ASP is recomputed from sums (SUM(net) / SUM(quantity)), never averaged. Grain: category x month.
SELECT month_start,
       category,
       SUM(quantity_units) AS quantity_units,
       SUM(net_amount_pkr) AS net_sales_pkr,
       ROUND(SUM(net_amount_pkr) / NULLIF(SUM(quantity_units), 0), 2) AS asp_pkr
FROM dw.vw_sales_enriched
GROUP BY month_start, category
ORDER BY category, month_start;
