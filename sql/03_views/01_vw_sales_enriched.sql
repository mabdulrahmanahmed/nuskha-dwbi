-- vw_sales_enriched: one row per receipt line with every dimension attribute; cancelled lines excluded.
-- Used by Power BI and queries A1-A4. Synthetic data (seed 472).
CREATE OR REPLACE VIEW dw.vw_sales_enriched AS
SELECT f.sales_line_id,
       f.receipt_no,
       f.line_no,
       d.full_date,
       d.month_start,
       d.month_name,
       d.quarter,
       d.year,
       d.fiscal_quarter,
       d.fiscal_year,
       d.is_ramadan,
       p.product_code,
       p.generic_name,
       p.strength,
       p.category,
       p.selling_unit,
       b.branch_code,
       b.branch_name,
       b.area,
       b.region,
       c.customer_code,
       c.customer_type,
       c.customer_name,
       f.is_customer_unresolved,
       f.quantity_units,
       f.gross_amount_pkr,
       f.discount_pkr,
       f.net_amount_pkr,
       f.cost_amount_pkr,
       f.gross_margin_pkr,
       f.source_system,
       f.source_key,
       f.batch_id
FROM dw.fact_sales f
JOIN dw.dim_date d     ON d.date_key = f.date_key
JOIN dw.dim_product p  ON p.product_key = f.product_key
JOIN dw.dim_branch b   ON b.branch_key = f.branch_key
JOIN dw.dim_customer c ON c.customer_key = f.customer_key
WHERE NOT f.is_cancelled;
