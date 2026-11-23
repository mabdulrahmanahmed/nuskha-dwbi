-- Finance department: MySQL database finance_db (same engine as Sales, separate database).
-- SYNTHETIC DATA ONLY: every row is produced by src/generate_sources.py (seed 472).
-- Columns exactly as in docs/blueprint.md; only DROP statements and table comments added.
DROP TABLE IF EXISTS panel_invoice;
DROP TABLE IF EXISTS fx_rate;
DROP TABLE IF EXISTS panel_account;

CREATE TABLE panel_account (
  account_no        INT PRIMARY KEY,         -- 40021
  company_name      VARCHAR(100) NOT NULL,   -- fictional company name
  credit_limit_pkr  DECIMAL(12,2),
  terms_days        SMALLINT,
  updated_at        DATETIME NOT NULL
) COMMENT = 'Synthetic data (seed 472): fictional companies on the credit panel';

CREATE TABLE fx_rate (
  rate_date  DATE PRIMARY KEY,
  usd_pkr    DECIMAL(10,4) NOT NULL
) COMMENT = 'Synthetic data (seed 472): daily USD/PKR rate, not real market rates';

CREATE TABLE panel_invoice (
  invoice_no   VARCHAR(16) PRIMARY KEY,
  account_no   INT NOT NULL REFERENCES panel_account(account_no),
  month_start  DATE NOT NULL,
  amount_pkr   DECIMAL(12,2) NOT NULL
) COMMENT = 'Synthetic data (seed 472): monthly panel invoices';
