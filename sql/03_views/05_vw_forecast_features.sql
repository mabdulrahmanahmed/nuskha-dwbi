-- vw_forecast_features: company x month net sales with lag and rolling features (BQ5).
-- As in docs/blueprint.md ("AI layer"), plus ramadan_days (days of Ramadan in the month)
-- for the Ramadan flag the model uses. rolling_3_prior uses only earlier months, so no
-- value leaks from the month being predicted. Synthetic data.
CREATE OR REPLACE VIEW dw.vw_forecast_features AS
WITH m AS (
  SELECT d.month_start, SUM(f.net_amount_pkr) AS net_sales_pkr
  FROM dw.fact_sales f JOIN dw.dim_date d USING (date_key)
  WHERE NOT f.is_cancelled
  GROUP BY d.month_start
),
r AS (
  SELECT month_start, SUM(CASE WHEN is_ramadan THEN 1 ELSE 0 END) AS ramadan_days
  FROM dw.dim_date
  GROUP BY month_start
)
SELECT m.month_start,
       m.net_sales_pkr,
       LAG(m.net_sales_pkr, 1)  OVER w AS lag_1,
       LAG(m.net_sales_pkr, 12) OVER w AS lag_12,
       AVG(m.net_sales_pkr) OVER (ORDER BY m.month_start ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) AS rolling_3_prior,
       EXTRACT(MONTH FROM m.month_start) AS month_of_year,
       r.ramadan_days
FROM m JOIN r ON r.month_start = m.month_start
WINDOW w AS (ORDER BY m.month_start);
