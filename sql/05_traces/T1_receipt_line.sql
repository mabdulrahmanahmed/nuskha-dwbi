-- T1 A normal till receipt line: fact row -> lineage -> staging row (then raw CSV and MySQL, see src/traces.py).
-- Parameter :source_key e.g. 'GUL-2026-000123|2'. Synthetic data.
-- step: fact row with its dimension attributes
SELECT f.sales_line_id, f.receipt_no, f.line_no, d.full_date, p.product_code, p.generic_name, b.branch_code,
       c.customer_code, f.quantity_units, f.net_amount_pkr, f.batch_id, f.source_system, f.source_key
FROM dw.fact_sales f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_product p USING (product_key)
JOIN dw.dim_branch b USING (branch_key) JOIN dw.dim_customer c USING (customer_key)
WHERE f.source_key = :source_key;
-- step: lineage row and its batch
SELECT l.*, b.watermark_from, b.watermark_to, b.status FROM meta.lineage l JOIN etl.batch b USING (batch_id)
WHERE l.warehouse_table = 'dw.fact_sales' AND l.source_key = :source_key;
-- step: staging row (normalized values and the raw record as extracted)
SELECT receipt_no, line_no, item_code, qty, unit_price_pkr, discount_pkr, net_amount_pkr, raw_json
FROM stg.receipt_line WHERE receipt_no || '|' || line_no = :source_key;
