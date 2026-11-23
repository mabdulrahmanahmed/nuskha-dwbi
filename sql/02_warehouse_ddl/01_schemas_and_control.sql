-- Nuskha warehouse (PostgreSQL database nuskha_dw): schemas and ETL control tables (unit 2.01).
-- SYNTHETIC DATA ONLY (seed 472). Safe to rerun: every object uses IF NOT EXISTS.

CREATE SCHEMA IF NOT EXISTS dw;    -- the two stars and their dimensions
CREATE SCHEMA IF NOT EXISTS stg;   -- staged (cleaned) copies and crosswalks
CREATE SCHEMA IF NOT EXISTS etl;   -- batches, step logs, rejects, deletions, validation results
CREATE SCHEMA IF NOT EXISTS meta;  -- metadata repository and lineage
CREATE SCHEMA IF NOT EXISTS ai;    -- model runs and outputs

-- One row per batch run; the watermark range says which updated_at values it extracted.
CREATE TABLE IF NOT EXISTS etl.batch (
  batch_id        SERIAL PRIMARY KEY,
  watermark_from  TIMESTAMP,                       -- exclusive; NULL for the first batch
  watermark_to    TIMESTAMP NOT NULL,              -- inclusive (the batch cut-off)
  started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at     TIMESTAMPTZ,
  status          TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
  rows_loaded     BIGINT,
  amount_loaded   NUMERIC(14,2),
  note            TEXT
);

-- One row per pipeline step and table (rows and amounts in and out).
CREATE TABLE IF NOT EXISTS etl.batch_stage_log (
  log_id      BIGSERIAL PRIMARY KEY,
  batch_id    INT REFERENCES etl.batch,
  stage       TEXT NOT NULL,                       -- extract, normalize, quality, load_dim, load_fact...
  table_name  TEXT NOT NULL,
  rows_in     BIGINT,
  rows_out    BIGINT,
  amount_in   NUMERIC(14,2),
  amount_out  NUMERIC(14,2),
  status      TEXT NOT NULL,
  note        TEXT,
  logged_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Quarantined source rows, with the reason and the raw record as it was extracted.
CREATE TABLE IF NOT EXISTS etl.rejects (
  reject_id      BIGSERIAL PRIMARY KEY,
  batch_id       INT NOT NULL REFERENCES etl.batch,
  source_system  TEXT NOT NULL,
  source_table   TEXT NOT NULL,
  source_key     TEXT NOT NULL,
  reason_code    TEXT NOT NULL,                    -- R01 ... R07 (docs/blueprint.md)
  reason_text    TEXT NOT NULL,
  raw_record     JSONB NOT NULL,
  rejected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (batch_id, source_system, source_table, source_key)   -- a rerun upserts, never doubles
);

-- Rows that disappeared from a source: logged, never deleted from the warehouse automatically.
CREATE TABLE IF NOT EXISTS etl.deletion_log (
  deletion_id    BIGSERIAL PRIMARY KEY,
  batch_id       INT NOT NULL REFERENCES etl.batch,
  source_system  TEXT NOT NULL,
  source_table   TEXT NOT NULL,
  source_key     TEXT NOT NULL,
  detected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  note           TEXT,
  UNIQUE (source_system, source_table, source_key)
);

-- Every validation check: what was expected, what was found, pass or fail.
CREATE TABLE IF NOT EXISTS etl.validation_result (
  result_id   BIGSERIAL PRIMARY KEY,
  batch_id    INT REFERENCES etl.batch,
  check_name  TEXT NOT NULL,
  expected    TEXT,
  actual      TEXT,
  passed      BOOLEAN NOT NULL,
  checked_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Crosswalks: each department's key -> one canonical code, with how it was matched.
CREATE TABLE IF NOT EXISTS stg.xw_product (
  source_system   TEXT NOT NULL,
  source_object   TEXT NOT NULL,
  source_key      TEXT NOT NULL,
  canonical_code  TEXT,                            -- 'P-0312'; NULL = unmatched (R01)
  match_method    TEXT NOT NULL,                   -- exact | rule | rule (description) | manual | unmatched
  batch_id        INT NOT NULL,
  PRIMARY KEY (source_system, source_object, source_key)
);
CREATE TABLE IF NOT EXISTS stg.xw_branch (
  source_system   TEXT NOT NULL,
  source_object   TEXT NOT NULL,
  source_key      TEXT NOT NULL,
  canonical_code  TEXT,                            -- 'BR-GUL'; NULL = unmatched (R05)
  match_method    TEXT NOT NULL,                   -- exact | rule | rule (alias list) | unmatched
  batch_id        INT NOT NULL,
  PRIMARY KEY (source_system, source_object, source_key)
);
CREATE TABLE IF NOT EXISTS stg.xw_customer (
  source_system   TEXT NOT NULL,
  source_object   TEXT NOT NULL,
  source_key      TEXT NOT NULL,
  canonical_code  TEXT,                            -- 'L-100043' | 'PANEL-40011'; NULL = Unknown (U01)
  match_method    TEXT NOT NULL,
  batch_id        INT NOT NULL,
  PRIMARY KEY (source_system, source_object, source_key)
);

COMMENT ON SCHEMA etl IS 'ETL control for the Nuskha project (synthetic data, seed 472)';
COMMENT ON TABLE etl.batch IS 'One row per batch: watermark range, status, totals';
COMMENT ON TABLE etl.rejects IS 'Quarantined source rows with reason codes R01-R07 (synthetic data)';
COMMENT ON TABLE etl.deletion_log IS 'Source rows that disappeared; logged, not deleted';
COMMENT ON TABLE stg.xw_product IS 'Product crosswalk: till / vendor / inventory keys -> canonical product code';
COMMENT ON TABLE stg.xw_branch IS 'Branch crosswalk: typed names / branch ids / store codes -> canonical branch code';
COMMENT ON TABLE stg.xw_customer IS 'Customer crosswalk: cards / typed panel names / accounts -> canonical customer code';
