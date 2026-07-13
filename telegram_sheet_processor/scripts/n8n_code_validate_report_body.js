// n8n Code node: build a safe request body for /validate-report.
//
// Put this before the HTTP Request node that calls:
// POST https://asset.jongchul-server.duckdns.org/validate-report
// Internal fallback: POST http://192.168.1.12:8010/validate-report

const input = $input.first().json;

function pickReportText(data) {
  if (!data) return "";
  if (typeof data === "string") return data;
  return (
    data.report_text ||
    data.output ||
    data.text ||
    data.message ||
    data.result ||
    data.data?.output ||
    data.data?.text ||
    data.json?.output ||
    data.json?.text ||
    ""
  );
}

return [
  {
    json: {
      report_text: String(pickReportText(input)),
      days: Number(input.days || 260),
      force: Boolean(input.force || false),
    },
  },
];
