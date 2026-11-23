-- T3 A late receipt loaded in batch 2: sold before the batch-1 cut-off, saved at the till after it.
-- Parameter :receipt_no. Synthetic data.
-- step: fact rows (dated in their real month, loaded by batch 2)
SELECT f.receipt_no, f.line_no, f.date_key, f.net_amount_pkr, f.batch_id FROM dw.fact_sales f
WHERE f.receipt_no = :receipt_no ORDER BY f.line_no;
-- step: the two batches: the receipt date is inside batch 1's range, its updated_at inside batch 2's
SELECT batch_id, watermark_from, watermark_to, status, note FROM etl.batch WHERE batch_id IN (1, 2) ORDER BY batch_id;
-- step: staged header (receipt_ts vs updated_at)
SELECT receipt_no, branch_text, receipt_ts, updated_at, status FROM stg.receipt WHERE receipt_no = :receipt_no;
