# Power BI data dictionary

Synthetic data (seed 472). Exported from the PostgreSQL warehouse. Money in PKR, 2 decimals; ratios are recomputed from sums in the measures.

## vw_sales_enriched.csv (29789 rows)

One row per receipt line with all dimension attributes; cancelled lines excluded.

| Column | Type |
| --- | --- |
| sales_line_id | int64 |
| receipt_no | object |
| line_no | int64 |
| full_date | datetime64[ns] |
| month_start | datetime64[ns] |
| month_name | object |
| quarter | int64 |
| year | int64 |
| fiscal_quarter | int64 |
| fiscal_year | object |
| is_ramadan | bool |
| product_code | object |
| generic_name | object |
| strength | object |
| category | object |
| selling_unit | object |
| branch_code | object |
| branch_name | object |
| area | object |
| region | object |
| customer_code | object |
| customer_type | object |
| customer_name | object |
| is_customer_unresolved | bool |
| quantity_units | float64 |
| gross_amount_pkr | float64 |
| discount_pkr | float64 |
| net_amount_pkr | float64 |
| cost_amount_pkr | float64 |
| gross_margin_pkr | float64 |
| source_system | object |
| source_key | object |
| batch_id | int64 |

## vw_sales_product_month.csv (5158 rows)

Sales summed to product x month.

| Column | Type |
| --- | --- |
| product_key | int64 |
| product_code | object |
| generic_name | object |
| category | object |
| month_start | datetime64[ns] |
| sales_lines | int64 |
| quantity_units | float64 |
| gross_amount_pkr | float64 |
| discount_pkr | float64 |
| net_amount_pkr | float64 |
| cost_amount_pkr | float64 |
| gross_margin_pkr | float64 |
| asp_pkr | float64 |
| std_unit_cost_pkr | float64 |
| margin_pct | float64 |

## vw_purchase_product_month.csv (3150 rows)

Purchases summed to product x month (PKR, units, original currency).

| Column | Type |
| --- | --- |
| product_key | int64 |
| product_code | object |
| generic_name | object |
| category | object |
| month_start | datetime64[ns] |
| purchase_lines | int64 |
| quantity_units | float64 |
| purchase_amount_pkr | float64 |
| amount_usd | float64 |
| amount_pkr_original | float64 |
| purchase_unit_cost_pkr | float64 |

## vw_margin_bridge.csv (5007 rows)

Month-on-month margin change per product split into volume, price and cost effects.

| Column | Type |
| --- | --- |
| product_key | int64 |
| product_code | object |
| generic_name | object |
| category | object |
| month_start | datetime64[ns] |
| prev_month | datetime64[ns] |
| qty | float64 |
| net_amount_pkr | float64 |
| cost_amount_pkr | float64 |
| gross_margin_pkr | float64 |
| asp_pkr | float64 |
| unit_cost_pkr | float64 |
| margin_change_pkr | float64 |
| volume_effect_pkr | float64 |
| price_effect_pkr | float64 |
| cost_effect_pkr | float64 |

## vw_forecast_features.csv (36 rows)

Company x month net sales with lag and rolling features.

| Column | Type |
| --- | --- |
| month_start | datetime64[ns] |
| net_sales_pkr | float64 |
| lag_1 | float64 |
| lag_12 | float64 |
| rolling_3_prior | float64 |
| month_of_year | float64 |
| ramadan_days | int64 |

## vw_region_category_month.csv (864 rows)

Region x category x month net sales with trailing statistics.

| Column | Type |
| --- | --- |
| region | object |
| category | object |
| month_start | datetime64[ns] |
| net_sales_pkr | float64 |
| sales_lines | int64 |
| trailing_median_6 | float64 |
| ratio_to_trailing | float64 |
| yoy_ratio | float64 |
| ratio_to_category | float64 |

## vw_purchase_enriched.csv (4911 rows)

One row per goods-receipt line with dimension attributes; cancelled GRNs excluded (for the purchases KPI).

| Column | Type |
| --- | --- |
| purchase_line_id | int64 |
| grn_no | object |
| line_no | int64 |
| full_date | datetime64[ns] |
| month_start | datetime64[ns] |
| fiscal_year | object |
| fiscal_quarter | int64 |
| product_code | object |
| generic_name | object |
| category | object |
| branch_name | object |
| region | object |
| supplier_name | object |
| origin | object |
| quantity_units | float64 |
| currency_code | object |
| fx_rate_used | float64 |
| amount_original | float64 |
| purchase_amount_pkr | float64 |
| batch_id | int64 |

## ai_forecast_result.csv (6 rows)

Holdout predictions and the Nov 2026 - Jan 2027 forecast.

| Column | Type |
| --- | --- |
| run_id | object |
| date_key | int64 |
| prediction | float64 |
| lower | float64 |
| upper | float64 |
| actual | float64 |
| is_holdout | bool |
| month_start | datetime64[ns] |
| method | object |

## ai_anomaly_result.csv (576 rows)

Anomaly scores and flags on the real review months.

| Column | Type |
| --- | --- |
| run_id | object |
| date_key | int64 |
| region | object |
| category | object |
| value | float64 |
| expected | float64 |
| score | float64 |
| method | object |
| is_flag | bool |
| is_injected_copy | bool |
| month_start | datetime64[ns] |

## dim_date.csv (1188 rows)

Conformed date dimension (fiscal year Jul-Jun).

| Column | Type |
| --- | --- |
| date_key | int64 |
| full_date | datetime64[ns] |
| month_start | datetime64[ns] |
| month_name | object |
| quarter | int64 |
| year | int64 |
| fiscal_quarter | int64 |
| fiscal_year | object |
| is_ramadan | bool |

## dim_product.csv (152 rows)

Conformed product dimension (current values, SCD Type 1).

| Column | Type |
| --- | --- |
| product_code | object |
| generic_name | object |
| strength | object |
| category | object |
| selling_unit | object |

## dim_branch.csv (11 rows)

Conformed branch dimension: branch -> area -> region.

| Column | Type |
| --- | --- |
| branch_code | object |
| branch_name | object |
| area | object |
| region | object |

## etl_last_batch.csv (1 rows)

Last batch id loaded (shown in every page footer).

| Column | Type |
| --- | --- |
| last_batch_id | int64 |
