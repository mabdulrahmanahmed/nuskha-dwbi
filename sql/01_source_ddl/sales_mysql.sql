-- Sales department (till / POS): MySQL database sales_db.
-- SYNTHETIC DATA ONLY: every row is produced by src/generate_sources.py (seed 472).
-- Columns exactly as in docs/blueprint.md; only DROP statements and table comments added.
DROP TABLE IF EXISTS receipt_line;
DROP TABLE IF EXISTS receipt;
DROP TABLE IF EXISTS pos_item;
DROP TABLE IF EXISTS loyalty_member;

CREATE TABLE loyalty_member (
  card_no      VARCHAR(12) PRIMARY KEY,
  member_name  VARCHAR(80),
  joined_on    DATE
) COMMENT = 'Synthetic data (seed 472): loyalty card holders';

CREATE TABLE pos_item (
  item_code    VARCHAR(20) PRIMARY KEY,      -- 'PCM-500-STR'
  item_desc    VARCHAR(100),
  sell_unit    VARCHAR(10)                   -- STRIP | BOTTLE | PIECE
) COMMENT = 'Synthetic data (seed 472): till item list';

CREATE TABLE receipt (
  receipt_no         VARCHAR(16) PRIMARY KEY, -- 'GUL-2026-000123'
  branch_name        VARCHAR(60) NOT NULL,    -- typed, inconsistent
  receipt_ts         DATETIME NOT NULL,
  customer_type      ENUM('WALKIN','LOYALTY','PANEL') NOT NULL,
  card_no            VARCHAR(12) NULL REFERENCES loyalty_member(card_no),
  panel_company_text VARCHAR(80) NULL,        -- typed by cashier
  status             ENUM('POSTED','VOIDED') NOT NULL DEFAULT 'POSTED',
  updated_at         DATETIME NOT NULL
) COMMENT = 'Synthetic data (seed 472): till receipt headers';

CREATE TABLE receipt_line (
  receipt_no      VARCHAR(16) NOT NULL REFERENCES receipt(receipt_no),
  line_no         SMALLINT NOT NULL,
  item_code       VARCHAR(20) NOT NULL REFERENCES pos_item(item_code),
  qty             DECIMAL(8,2) NOT NULL,       -- selling units
  unit_price_pkr  DECIMAL(10,2) NOT NULL,
  discount_pkr    DECIMAL(10,2) NULL,
  updated_at      DATETIME NOT NULL,
  PRIMARY KEY (receipt_no, line_no)
) COMMENT = 'Synthetic data (seed 472): till receipt lines';
