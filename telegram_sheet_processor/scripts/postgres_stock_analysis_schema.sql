-- Postgres schema for n8n stock analysis inserts.
-- Replace "stock_analysis_results" with your actual table name if needed.

-- 1) Diagnose varchar(10) columns in the current schema.
SELECT
  table_schema,
  table_name,
  column_name,
  data_type,
  character_maximum_length
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
  AND data_type = 'character varying'
  AND character_maximum_length <= 10
ORDER BY table_schema, table_name, ordinal_position;

-- 2) Recommended table for the n8n "Insert rows in a table" node.
CREATE TABLE IF NOT EXISTS stock_analysis_results (
  id BIGSERIAL PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  symbol VARCHAR(10) NOT NULL,
  ticker VARCHAR(10),
  name VARCHAR(80),
  decision VARCHAR(10),
  score NUMERIC(8, 2),
  technical_score NUMERIC(8, 2),
  analysis_date DATE,
  data_as_of DATE,
  data_age_days INTEGER,
  freshness_status VARCHAR(16),
  tradable BOOLEAN,
  no_recommendation_reason TEXT,
  validation_status VARCHAR(24),
  source_close_diff_pct NUMERIC(10, 4),
  source_date_diff_days INTEGER,
  latest_date DATE,
  latest_close NUMERIC(18, 4),
  provider VARCHAR(32),
  rsi14 NUMERIC(10, 4),
  sma20 NUMERIC(18, 4),
  sma60 NUMERIC(18, 4),
  macd_histogram NUMERIC(18, 4),
  chart_path TEXT,
  summary TEXT,
  warnings TEXT,
  raw_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_stock_analysis_results_symbol_created
  ON stock_analysis_results (symbol, created_at DESC);

-- 3) If your existing table was created before freshness columns were added,
-- add them safely.
ALTER TABLE stock_analysis_results ADD COLUMN IF NOT EXISTS technical_score NUMERIC(8, 2);
ALTER TABLE stock_analysis_results ADD COLUMN IF NOT EXISTS analysis_date DATE;
ALTER TABLE stock_analysis_results ADD COLUMN IF NOT EXISTS data_as_of DATE;
ALTER TABLE stock_analysis_results ADD COLUMN IF NOT EXISTS data_age_days INTEGER;
ALTER TABLE stock_analysis_results ADD COLUMN IF NOT EXISTS freshness_status VARCHAR(16);
ALTER TABLE stock_analysis_results ADD COLUMN IF NOT EXISTS tradable BOOLEAN;
ALTER TABLE stock_analysis_results ADD COLUMN IF NOT EXISTS no_recommendation_reason TEXT;
ALTER TABLE stock_analysis_results ADD COLUMN IF NOT EXISTS validation_status VARCHAR(24);
ALTER TABLE stock_analysis_results ADD COLUMN IF NOT EXISTS source_close_diff_pct NUMERIC(10, 4);
ALTER TABLE stock_analysis_results ADD COLUMN IF NOT EXISTS source_date_diff_days INTEGER;

-- 4) If your existing table has output/message/result columns as varchar(10),
-- widen them. Run only the lines that match your actual columns.
-- ALTER TABLE stock_analysis_results ALTER COLUMN output TYPE TEXT;
-- ALTER TABLE stock_analysis_results ALTER COLUMN message TYPE TEXT;
-- ALTER TABLE stock_analysis_results ALTER COLUMN result TYPE TEXT;
-- ALTER TABLE stock_analysis_results ALTER COLUMN summary TYPE TEXT;
-- ALTER TABLE stock_analysis_results ALTER COLUMN raw_json TYPE JSONB USING raw_json::jsonb;
