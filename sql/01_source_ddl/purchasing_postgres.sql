-- Purchasing department: PostgreSQL database purchasing_db.
-- SYNTHETIC DATA ONLY: every row is produced by src/generate_sources.py (seed 472).
-- Columns exactly as in docs/blueprint.md; only DROP statements and table comments added.
DROP TABLE IF EXISTS grn_line;
DROP TABLE IF EXISTS goods_receipt;
DROP TABLE IF EXISTS purchase_order;
DROP TABLE IF EXISTS vendor_item;
DROP TABLE IF EXISTS branch;
DROP TABLE IF EXISTS supplier;

CREATE TABLE supplier (
  supplier_id    SERIAL PRIMARY KEY,
  supplier_name  TEXT NOT NULL,
  country        TEXT NOT NULL,
  is_import      BOOLEAN NOT NULL
);
CREATE TABLE branch (
  branch_id      SMALLINT PRIMARY KEY,
  branch_label   TEXT NOT NULL                -- 'Gulshan-e-Iqbal Br.'
);
CREATE TABLE vendor_item (
  vendor_item_code TEXT PRIMARY KEY,          -- 'DST-1187'
  supplier_id      INT NOT NULL REFERENCES supplier,
  description      TEXT,
  strips_per_box   INT NOT NULL
);
CREATE TABLE purchase_order (
  po_no        TEXT PRIMARY KEY,
  supplier_id  INT NOT NULL REFERENCES supplier,
  branch_id    SMALLINT NOT NULL REFERENCES branch,
  ordered_at   TIMESTAMPTZ NOT NULL,
  currency     CHAR(3) NOT NULL CHECK (currency IN ('PKR','USD')),
  updated_at   TIMESTAMPTZ NOT NULL
);
CREATE TABLE goods_receipt (
  grn_no       TEXT PRIMARY KEY,
  po_no        TEXT NOT NULL REFERENCES purchase_order,
  received_at  TIMESTAMPTZ NOT NULL,
  status       TEXT NOT NULL DEFAULT 'POSTED',  -- POSTED | CANCELLED
  updated_at   TIMESTAMPTZ NOT NULL
);
CREATE TABLE grn_line (
  grn_no            TEXT NOT NULL REFERENCES goods_receipt,
  line_no           SMALLINT NOT NULL,
  vendor_item_code  TEXT NOT NULL REFERENCES vendor_item,
  boxes_received    NUMERIC(8,2) NOT NULL,
  cost_per_box      NUMERIC(12,2) NOT NULL,   -- in PO currency
  updated_at        TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (grn_no, line_no)
);

COMMENT ON TABLE supplier       IS 'Synthetic data (seed 472): fictional suppliers';
COMMENT ON TABLE branch         IS 'Synthetic data (seed 472): branches as Purchasing labels them';
COMMENT ON TABLE vendor_item    IS 'Synthetic data (seed 472): supplier item codes and box sizes';
COMMENT ON TABLE purchase_order IS 'Synthetic data (seed 472): purchase orders in PKR or USD';
COMMENT ON TABLE goods_receipt  IS 'Synthetic data (seed 472): goods received notes (GRN)';
COMMENT ON TABLE grn_line       IS 'Synthetic data (seed 472): GRN lines in boxes';
