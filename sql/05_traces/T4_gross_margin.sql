-- T4 Derived measure: gross_margin_pkr = net (Sales) - quantity x standard cost effective on the date (Inventory).
-- Parameter :source_key. Synthetic data.
-- step: fact row with its stored cost and margin
SELECT f.source_key, d.full_date, p.product_code, p.category, f.quantity_units, f.net_amount_pkr,
       f.cost_amount_pkr, f.gross_margin_pkr, round(f.cost_amount_pkr / f.quantity_units, 2) AS unit_cost_used,
       p.std_cost_per_unit AS current_std_cost
FROM dw.fact_sales f JOIN dw.dim_date d USING (date_key) JOIN dw.dim_product p USING (product_key)
WHERE f.source_key = :source_key;
-- step: cost history row effective on the receipt date (staged Inventory table)
SELECT h.item_id, h.effective_from, h.std_cost_per_unit FROM stg.item_cost_history h
WHERE h.item_id = (SELECT product_key FROM dw.fact_sales WHERE source_key = :source_key)
  AND h.effective_from <= (SELECT d.full_date FROM dw.fact_sales f JOIN dw.dim_date d USING (date_key)
                           WHERE f.source_key = :source_key)
ORDER BY h.effective_from DESC LIMIT 1;
