-- A3 (Practical 9, trend): monthly net sales by category through the flu, dengue and
-- Ramadan seasons (BQ2). Grain: category x month. SQL feature: GROUP BY on the date hierarchy.
SELECT month_start,
       year,
       fiscal_year,
       category,
       SUM(net_amount_pkr) AS net_sales_pkr,
       COUNT(*)            AS sales_lines
FROM dw.vw_sales_enriched
GROUP BY month_start, year, fiscal_year, category
ORDER BY month_start, category;
