-- Inventory department (legacy app): SQLite file inventory.db.
-- SYNTHETIC DATA ONLY: every row is produced by src/generate_sources.py (seed 472).
-- Legacy design on purpose: no declared foreign keys, dates as DD/MM/YYYY text, cost as REAL.
-- Columns exactly as in docs/blueprint.md; only DROP statements added. SQLite has no table
-- comments, so the synthetic note is kept as a comment inside each CREATE statement.
DROP TABLE IF EXISTS item;
DROP TABLE IF EXISTS store;
DROP TABLE IF EXISTS stock_count;
DROP TABLE IF EXISTS item_cost_history;

CREATE TABLE item (                         -- synthetic data (seed 472)
  item_id             INTEGER PRIMARY KEY,   -- 312
  generic_name        TEXT,                  -- 'Paracetamol'
  strength            TEXT,                  -- '500 mg'
  category            TEXT,                  -- ' analgesics ', 'ANALGESICS'
  tablets_per_strip   INTEGER,
  std_cost_per_strip  REAL,
  pos_code            TEXT,                  -- partly filled
  vendor_code         TEXT,                  -- partly filled
  last_updated        TEXT                   -- 'DD/MM/YYYY'
);
CREATE TABLE store (                        -- synthetic data (seed 472)
  store_code  TEXT PRIMARY KEY,              -- 'BR-GUL'
  store_name  TEXT,
  area        TEXT,
  region      TEXT                           -- North | East | South
);
CREATE TABLE stock_count (                  -- synthetic data (seed 472)
  store_code       TEXT,
  item_id          INTEGER,
  count_date       TEXT,
  tablets_on_hand  INTEGER
);
CREATE TABLE item_cost_history (            -- synthetic data (seed 472)
  item_id             INTEGER,               -- no declared FK
  effective_from      TEXT,                  -- 'DD/MM/YYYY'
  std_cost_per_strip  REAL
);
