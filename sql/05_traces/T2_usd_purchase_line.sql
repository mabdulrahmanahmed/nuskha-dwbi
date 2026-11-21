-- T2 A USD purchase line: fact row -> FX rate used -> staging (then PostgreSQL grn_line and Finance fx_rate).
-- Parameter :source_key e.g. 'GRN-2026-00462|1'. Synthetic data.
-- step: fact row
SELECT f.grn_no, f.line_no, d.full_date, p.product_code, s.supplier_code, s.origin, f.quantity_units,
       f.currency_code, f.amount_original, f.fx_rate_used, f.purchase_amount_pkr,
       round(f.amount_original * f.fx_rate_used, 2) AS recomputed_pkr, f.batch_id
FROM dw.fact_purchase f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_product p USING (product_key)
JOIN dw.dim_supplier s USING (supplier_key) WHERE f.source_key = :source_key;
-- step: FX rate on or before the receipt date (staged Finance table)
SELECT r.rate_date, r.usd_pkr FROM stg.fx_rate r
WHERE r.rate_date <= (SELECT d.full_date FROM dw.fact_purchase f JOIN dw.dim_date d USING (date_key)
                      WHERE f.source_key = :source_key)
ORDER BY r.rate_date DESC LIMIT 1;
-- step: staged GRN line
SELECT grn_no, line_no, vendor_item_code, boxes_received, cost_per_box, amount_original, raw_json
FROM stg.grn_line WHERE grn_no || '|' || line_no = :source_key;
