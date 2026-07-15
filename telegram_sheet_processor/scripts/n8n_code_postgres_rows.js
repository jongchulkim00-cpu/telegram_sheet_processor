// n8n Code node: convert stock-analyze API output into safe Postgres rows.
//
// Use this after the HTTP Request node and before "Insert rows in a table".
// It avoids inserting the long AI answer into varchar(10) columns.

const payload = $input.first().json;

function toRows(data) {
  if (data.can_insert_db === false) return [];
  if (Array.isArray(data.db_rows)) return data.db_rows;
  if (data.result?.db_row) return [data.result.db_row];
  if (Array.isArray(data.results)) return data.results.map((row) => row.db_row || row);
  if (data.db_data && data.can_insert_db !== false) return [data.db_data];
  return [];
}

function clampText(value, max) {
  const text = value === null || value === undefined ? "" : String(value);
  return text.length > max ? text.slice(0, max) : text;
}

const rows = toRows(payload).map((row) => ({
  symbol: clampText(row.symbol || row.ticker, 10),
  ticker: clampText(row.ticker || row.symbol, 10),
  name: clampText(row.name, 80),
  decision: clampText(row.decision, 10),
  score: row.score ?? null,
  technical_score: row.technical_score ?? row.score ?? null,
  analysis_date: row.analysis_date || null,
  data_as_of: row.data_as_of || row.latest_date || null,
  data_age_days: row.data_age_days ?? null,
  freshness_status: clampText(row.freshness_status, 16),
  tradable: row.tradable ?? null,
  no_recommendation_reason: row.no_recommendation_reason || "",
  validation_status: clampText(row.validation_status, 24),
  source_close_diff_pct: row.source_close_diff_pct ?? null,
  source_date_diff_days: row.source_date_diff_days ?? null,
  latest_date: row.latest_date || null,
  latest_close: row.latest_close ?? null,
  provider: clampText(row.provider, 32),
  rsi14: row.rsi14 ?? null,
  sma20: row.sma20 ?? null,
  sma60: row.sma60 ?? null,
  macd_histogram: row.macd_histogram ?? null,
  chart_path: row.chart_path || null,
  summary: row.summary || "",
  warnings: row.warnings || "",
  raw_json: row.raw_json || JSON.stringify(row),
}));

return rows.map((row) => ({ json: row }));
