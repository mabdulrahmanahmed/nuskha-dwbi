-- A2 (Practical 9, contribution): each category's share of gross margin per fiscal year.
-- Grain: category x fiscal year. SQL feature: SUM() OVER (PARTITION BY ...). Synthetic data.
WITH c AS (
  SELECT fiscal_year, category, SUM(gross_margin_pkr) AS gross_margin_pkr
  FROM dw.vw_sales_enriched
  GROUP BY fiscal_year, category
)
SELECT fiscal_year,
       category,
       gross_margin_pkr,
       ROUND(100 * gross_margin_pkr / SUM(gross_margin_pkr) OVER (PARTITION BY fiscal_year), 2) AS share_of_margin_pct
FROM c
ORDER BY fiscal_year, share_of_margin_pct DESC;
