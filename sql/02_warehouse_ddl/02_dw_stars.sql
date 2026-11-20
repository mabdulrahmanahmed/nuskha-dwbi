-- Nuskha warehouse: the two stars (unit 3.01). Columns exactly as in docs/blueprint.md
-- ("Warehouse DDL (Q7)"); only IF NOT EXISTS and comments are added.
-- SYNTHETIC DATA ONLY (seed 472). Money is NUMERIC(14,2); keys are stable integers.

CREATE TABLE IF NOT EXISTS dw.dim_date (
  date_key       INT PRIMARY KEY,              -- 20260315
  full_date      DATE NOT NULL UNIQUE,
  month_start    DATE NOT NULL,
  month_name     TEXT NOT NULL,
  quarter        SMALLINT NOT NULL,
  year           SMALLINT NOT NULL,
  fiscal_quarter SMALLINT NOT NULL,            -- Jul-Sep = 1
  fiscal_year    TEXT NOT NULL,                -- 'FY2026' = Jul 2025-Jun 2026
  is_ramadan     BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS dw.dim_product (
  product_key        INT PRIMARY KEY,          -- -1 = Unknown
  product_code       TEXT NOT NULL UNIQUE,     -- canonical 'P-0312'
  generic_name       TEXT NOT NULL,
  strength           TEXT NOT NULL,
  category           TEXT NOT NULL,
  selling_unit       TEXT NOT NULL,            -- STRIP | BOTTLE | PIECE
  tablets_per_unit   INT,
  std_cost_per_unit  NUMERIC(14,2) NOT NULL,
  updated_batch_id   INT NOT NULL
);
CREATE TABLE IF NOT EXISTS dw.dim_branch (
  branch_key     INT PRIMARY KEY,              -- -1 = Unknown
  branch_code    TEXT NOT NULL UNIQUE,         -- 'BR-GUL'
  branch_name    TEXT NOT NULL,
  area           TEXT NOT NULL,
  region         TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dw.dim_customer (
  customer_key   INT PRIMARY KEY,              -- 0 = Walk-in, -1 = Unknown
  customer_code  TEXT NOT NULL UNIQUE,         -- 'L-1043', 'PANEL-40021'
  customer_type  TEXT NOT NULL,                -- WALKIN | LOYALTY | PANEL
  customer_name  TEXT NOT NULL,
  panel_terms_days SMALLINT,
  updated_batch_id INT NOT NULL
);
CREATE TABLE IF NOT EXISTS dw.dim_supplier (
  supplier_key   INT PRIMARY KEY,
  supplier_code  TEXT NOT NULL UNIQUE,
  supplier_name  TEXT NOT NULL,
  origin         TEXT NOT NULL                 -- LOCAL | IMPORT
);
CREATE TABLE IF NOT EXISTS dw.fact_sales (
  sales_line_id      BIGSERIAL PRIMARY KEY,
  date_key           INT NOT NULL REFERENCES dw.dim_date,
  product_key        INT NOT NULL REFERENCES dw.dim_product,
  branch_key         INT NOT NULL REFERENCES dw.dim_branch,
  customer_key       INT NOT NULL REFERENCES dw.dim_customer,
  receipt_no         TEXT NOT NULL,             -- degenerate
  line_no            SMALLINT NOT NULL,
  quantity_units     NUMERIC(10,2) NOT NULL,
  gross_amount_pkr   NUMERIC(14,2) NOT NULL,
  discount_pkr       NUMERIC(14,2) NOT NULL,
  net_amount_pkr     NUMERIC(14,2) NOT NULL,
  cost_amount_pkr    NUMERIC(14,2) NOT NULL,
  gross_margin_pkr   NUMERIC(14,2) NOT NULL,
  is_cancelled       BOOLEAN NOT NULL DEFAULT false,
  is_customer_unresolved BOOLEAN NOT NULL DEFAULT false,
  source_system      TEXT NOT NULL,             -- 'sales_db'
  source_key         TEXT NOT NULL,             -- 'GUL-2026-000123|2'
  batch_id           INT NOT NULL,
  UNIQUE (source_system, receipt_no, line_no)
);
CREATE TABLE IF NOT EXISTS dw.fact_purchase (
  purchase_line_id     BIGSERIAL PRIMARY KEY,
  date_key             INT NOT NULL REFERENCES dw.dim_date,
  product_key          INT NOT NULL REFERENCES dw.dim_product,
  branch_key           INT NOT NULL REFERENCES dw.dim_branch,
  supplier_key         INT NOT NULL REFERENCES dw.dim_supplier,
  grn_no               TEXT NOT NULL,
  line_no              SMALLINT NOT NULL,
  quantity_units       NUMERIC(10,2) NOT NULL,
  currency_code        CHAR(3) NOT NULL,
  fx_rate_used         NUMERIC(10,4) NOT NULL,   -- 1 for PKR
  amount_original      NUMERIC(14,2) NOT NULL,
  purchase_amount_pkr  NUMERIC(14,2) NOT NULL,
  is_cancelled         BOOLEAN NOT NULL DEFAULT false,
  source_system        TEXT NOT NULL,
  source_key           TEXT NOT NULL,
  batch_id             INT NOT NULL,
  UNIQUE (source_system, grn_no, line_no)
);

COMMENT ON TABLE dw.dim_date IS 'Conformed date dimension 2023-11-01..2027-01-31, fiscal year Jul-Jun (synthetic project)';
COMMENT ON TABLE dw.dim_product IS 'Conformed product dimension, SCD Type 1; -1 = Unknown (synthetic data)';
COMMENT ON TABLE dw.dim_branch IS 'Conformed branch dimension: branch -> area -> region; -1 = Unknown (synthetic data)';
COMMENT ON TABLE dw.dim_customer IS 'Customer dimension, SCD Type 1; 0 = Walk-in, -1 = Unknown (synthetic data)';
COMMENT ON TABLE dw.dim_supplier IS 'Supplier dimension: supplier -> origin; -1 = Unknown (synthetic data)';
COMMENT ON TABLE dw.fact_sales IS 'One row per till receipt line (synthetic data, seed 472)';
COMMENT ON TABLE dw.fact_purchase IS 'One row per goods-receipt line (synthetic data, seed 472)';
