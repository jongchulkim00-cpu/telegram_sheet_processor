// n8n Code node: block Telegram/Postgres publishing when stock prices are stale or mismatched.
//
// Place this after one of these HTTP Request nodes:
// - POST https://asset.jongchul-server.duckdns.org/validate-report
// - POST https://asset.jongchul-server.duckdns.org/verify-prices
//
// Then add an IF node:
// - Value 1: ={{ $json.can_publish }}
// - Operation: is true
//
// True branch: send the report / insert rows.
// False branch: send $json.guard_message to Telegram or route back to the AI Agent for rewrite.

const payload = $input.first().json || {};

function asArray(value) {
  if (!value) return [];
  return Array.isArray(value) ? value : [value];
}

function compact(values) {
  return values.filter((value) => value !== null && value !== undefined && String(value).trim() !== "");
}

function unique(values) {
  return [...new Set(values)];
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return number.toLocaleString("ko-KR");
}

const topLevelReasons = asArray(payload.blocking_reasons);
const resultRows = [
  ...asArray(payload.results),
  ...asArray(payload.price_verification?.results),
];
const resultReasons = resultRows.flatMap((row) => asArray(row.checks));

const badRows = resultRows.filter((row) => {
  const decision = String(row.decision || "").toUpperCase();
  const claimStatus = String(row.claim_status || "").toLowerCase();
  const freshness = String(row.freshness_status || "").toLowerCase();
  const validation = row.validation || {};
  const validationStatus = String(row.validation_status || validation.status || "").toLowerCase();

  return (
    row.tradable === false ||
    freshness === "stale" ||
    validationStatus === "mismatched" ||
    claimStatus.includes("mismatch") ||
    decision.includes("MISMATCH") ||
    decision.includes("STALE")
  );
});

const publishable =
  payload.publishable !== false &&
  payload.ok !== false &&
  badRows.length === 0 &&
  topLevelReasons.length === 0 &&
  Number(payload.error_count || 0) === 0;

const badRowSummaries = badRows.map((row) => {
  const ticker = row.ticker || row.symbol || "UNKNOWN";
  const claimed = row.claimed_price !== undefined ? `claimed ${formatNumber(row.claimed_price)}` : "";
  const verified = row.verified_price !== undefined
    ? `verified ${formatNumber(row.verified_price)}`
    : row.actual_close !== undefined
      ? `verified ${formatNumber(row.actual_close)}`
      : "";
  const asOf = row.data_as_of ? `as_of ${row.data_as_of}` : "";
  const diff = row.price_diff_pct !== undefined ? `diff ${Number(row.price_diff_pct).toFixed(2)}%` : "";
  return compact([ticker, claimed, verified, asOf, diff]).join(" / ");
});

const reasons = unique(compact([
  ...topLevelReasons,
  ...resultReasons,
  ...badRowSummaries,
  payload.error,
]));

const guardMessage = publishable
  ? "가격/기준일 검증 통과: 텔레그램 전송 및 DB 저장 가능"
  : [
      "가격/기준일 검증 실패: 전송을 차단했습니다.",
      "",
      ...reasons.slice(0, 12).map((reason) => `- ${reason}`),
      "",
      "조치: verified_price, data_as_of, validation.status 기준으로 보고서를 다시 작성하세요.",
    ].join("\n");

return [
  {
    json: {
      ...payload,
      can_publish: publishable,
      report_guard_status: publishable ? "passed" : "blocked",
      blocking_reasons: reasons,
      blocked_rows: badRows,
      guard_message: guardMessage,
    },
  },
];
