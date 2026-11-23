-- A1 (Practical 9, comparison; task number provisional): net sales and gross margin by branch,
-- this fiscal quarter vs the previous quarter and vs the same quarter last year (BQ1).
-- This quarter = FY2027 Q1 (Jul-Sep 2026), the last complete quarter in the data.
-- Grain: branch x quarter. SQL feature: GROUP BY with FILTER and CASE. Synthetic data.
SELECT branch_name,
       region,
       SUM(net_amount_pkr)   FILTER (WHERE fiscal_year = 'FY2027' AND fiscal_quarter = 1) AS net_this_q,
       SUM(net_amount_pkr)   FILTER (WHERE fiscal_year = 'FY2026' AND fiscal_quarter = 4) AS net_prev_q,
       SUM(net_amount_pkr)   FILTER (WHERE fiscal_year = 'FY2026' AND fiscal_quarter = 1) AS net_same_q_last_year,
       SUM(gross_margin_pkr) FILTER (WHERE fiscal_year = 'FY2027' AND fiscal_quarter = 1) AS margin_this_q,
       SUM(gross_margin_pkr) FILTER (WHERE fiscal_year = 'FY2026' AND fiscal_quarter = 1) AS margin_same_q_last_year,
       ROUND(100 * (SUM(net_amount_pkr) FILTER (WHERE fiscal_year = 'FY2027' AND fiscal_quarter = 1)
                  / NULLIF(SUM(net_amount_pkr) FILTER (WHERE fiscal_year = 'FY2026' AND fiscal_quarter = 1), 0) - 1), 1)
                                                                                         AS net_growth_vs_ly_pct,
       CASE WHEN SUM(gross_margin_pkr) FILTER (WHERE fiscal_year = 'FY2027' AND fiscal_quarter = 1)
               > SUM(gross_margin_pkr) FILTER (WHERE fiscal_year = 'FY2026' AND fiscal_quarter = 1)
            THEN 'margin grew' ELSE 'margin fell' END                                    AS margin_vs_ly
FROM dw.vw_sales_enriched
GROUP BY branch_name, region
ORDER BY net_growth_vs_ly_pct DESC;
