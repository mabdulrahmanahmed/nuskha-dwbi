-- Nuskha warehouse: metadata repository (meta) and AI outputs (ai) (unit 3.01).
-- SYNTHETIC DATA ONLY (seed 472). Safe to rerun.

-- ---------------- meta: metadata repository (replaces Practical 8) ----------------
CREATE TABLE IF NOT EXISTS meta.source_system (
  source_system  TEXT PRIMARY KEY,                 -- 'sales_db'
  engine         TEXT NOT NULL,                    -- MySQL | PostgreSQL | SQLite
  database_name  TEXT NOT NULL,
  department     TEXT NOT NULL,
  owner          TEXT NOT NULL,
  is_synthetic   BOOLEAN NOT NULL DEFAULT true
);
CREATE TABLE IF NOT EXISTS meta.source_object (
  source_system  TEXT NOT NULL REFERENCES meta.source_system,
  object_name    TEXT NOT NULL,                    -- source table
  primary_key    TEXT NOT NULL,                    -- 'receipt_no, line_no'
  batch_id       INT NOT NULL,
  row_count      BIGINT NOT NULL,
  PRIMARY KEY (source_system, object_name, batch_id)
);
CREATE TABLE IF NOT EXISTS meta.transform_rule (
  rule_id         TEXT PRIMARY KEY,                -- 'R-UNIT-01'
  description     TEXT NOT NULL,                   -- plain-language rule
  code_reference  TEXT NOT NULL                    -- 'src/normalize.py: convert_purchase_lines'
);
CREATE TABLE IF NOT EXISTS meta.column_map (
  map_id            SERIAL PRIMARY KEY,
  source_system     TEXT NOT NULL,
  source_object     TEXT NOT NULL,
  source_column     TEXT NOT NULL,
  staging_table     TEXT,
  staging_column    TEXT,
  warehouse_table   TEXT NOT NULL,
  warehouse_column  TEXT NOT NULL,
  rule_id           TEXT REFERENCES meta.transform_rule,
  UNIQUE (source_system, source_object, source_column, warehouse_table, warehouse_column)
);
CREATE TABLE IF NOT EXISTS meta.lineage (
  warehouse_table  TEXT NOT NULL,                  -- 'dw.fact_sales'
  natural_key      TEXT NOT NULL,                  -- 'sales_db|GUL-2026-000123|2'
  source_system    TEXT NOT NULL,
  source_table     TEXT NOT NULL,
  source_key       TEXT NOT NULL,
  batch_id         INT NOT NULL,
  PRIMARY KEY (warehouse_table, natural_key)
);

-- ---------------- ai: model runs and outputs (never inside fact tables) ----------------
CREATE TABLE IF NOT EXISTS ai.model_run (
  run_id           TEXT PRIMARY KEY,               -- hash of config + data batch
  task             TEXT NOT NULL,                  -- forecast | anomaly
  method           TEXT NOT NULL,
  parameters       JSONB NOT NULL,
  training_window  TEXT NOT NULL,
  data_batch_id    INT NOT NULL,
  metrics          JSONB,
  code_version     TEXT NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS ai.forecast_result (
  run_id      TEXT NOT NULL REFERENCES ai.model_run,
  date_key    INT NOT NULL REFERENCES dw.dim_date,     -- first day of the month
  prediction  NUMERIC(14,2) NOT NULL,
  lower       NUMERIC(14,2),
  upper       NUMERIC(14,2),
  actual      NUMERIC(14,2),
  is_holdout  BOOLEAN NOT NULL,
  UNIQUE (run_id, date_key)
);
CREATE TABLE IF NOT EXISTS ai.anomaly_result (
  run_id            TEXT NOT NULL REFERENCES ai.model_run,
  date_key          INT NOT NULL REFERENCES dw.dim_date,
  region            TEXT NOT NULL,
  category          TEXT NOT NULL,
  value             NUMERIC(14,2) NOT NULL,
  expected          NUMERIC(14,2),
  score             NUMERIC(12,4),
  method            TEXT NOT NULL,                     -- robust_z | isolation_forest
  is_flag           BOOLEAN NOT NULL,
  is_injected_copy  BOOLEAN NOT NULL DEFAULT false,
  UNIQUE (run_id, date_key, region, category, method)
);

COMMENT ON TABLE meta.lineage IS 'Warehouse row -> source system, table, key and batch (synthetic data)';
COMMENT ON TABLE ai.model_run IS 'One row per model run; run_id = hash of config + data batch (synthetic data)';
COMMENT ON TABLE ai.forecast_result IS 'Monthly net sales forecasts and holdout actuals (synthetic data)';
COMMENT ON TABLE ai.anomaly_result IS 'Region x category x month anomaly scores and flags (synthetic data)';
