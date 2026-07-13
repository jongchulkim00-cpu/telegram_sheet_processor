// n8n Code node: convert /quote response into a Telegram-ready text message.
//
// Previous node:
// POST https://asset.jongchul-server.duckdns.org/quote
// Body example: { "symbol": "399720", "force": true }
//
// Telegram node:
// Text: ={{ $json.text }}

const payload = $input.first().json || {};
const quote = payload.quote || payload.result || payload;

function formatWon(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value || "");
  return `${number.toLocaleString("ko-KR")}원`;
}

const text = quote.message || [
  `${quote.name || quote.ticker}(${quote.ticker}) ${quote.quote_wording || "공개 현재가"}: ${formatWon(quote.quote_price)}`,
  `분석 기준일: ${quote.analysis_date || ""}`,
  `데이터 기준일: ${quote.data_as_of || ""}`,
  `출처: ${quote.quote_source || ""}`,
  quote.quote_url ? `URL: ${quote.quote_url}` : "",
].filter(Boolean).join("\n");

return [
  {
    json: {
      ...payload,
      text,
      can_send: payload.ok !== false && Boolean(quote.quote_price),
      broker_realtime_enabled: Boolean(quote.broker_realtime_enabled),
      quote_label: quote.quote_label || "public_current_quote",
    },
  },
];
