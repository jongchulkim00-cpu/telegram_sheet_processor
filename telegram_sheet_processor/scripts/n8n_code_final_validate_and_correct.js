// n8n Code node: final Telegram/Postgres gate with auto-correction.
//
// Place this immediately after AI Agent (Router), before Postgres and Telegram.
// It validates the AI report through /validate-report. If the report is stale
// or price-mismatched, it sends a corrected current quote message instead.

const input = items[0]?.json || {};
const fullOutput = String(input.output || input.text || input.message || input.result || "");

function todayKstIso() {
  const now = new Date();
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  return kst.toISOString().slice(0, 10);
}

function todayKorean() {
  const [year, month, day] = todayKstIso().split("-").map(Number);
  return `${year}\uB144 ${month}\uC6D4 ${day}\uC77C`;
}

function parseDbData(text) {
  const candidates = [];
  const tagged = text.match(/<json>([\s\S]*?)<\/json>/);
  if (tagged) candidates.push(tagged[1]);

  const fencedMatches = [...text.matchAll(/```json\s*([\s\S]*?)```/gi)];
  for (const match of fencedMatches) candidates.push(match[1]);

  const normalizeRow = (parsed) => {
    if (!parsed || typeof parsed !== "object") return null;
    if (parsed.symbol || parsed.ticker) return parsed;
    for (const value of Object.values(parsed)) {
      if (value && typeof value === "object" && (value.symbol || value.ticker)) {
        return value;
      }
    }
    return null;
  };

  if (!candidates.length) return { symbol: "N/A", score: 0, decision: "Neutral", target_price: 0, stop_loss: 0 };
  try {
    let parsed = null;
    for (const candidate of candidates) {
      try {
        parsed = normalizeRow(JSON.parse(candidate));
        if (parsed) break;
      } catch (error) {}
    }
    if (!parsed) return { symbol: "N/A", score: 0, decision: "Neutral", target_price: 0, stop_loss: 0 };
    return {
      symbol: String(parsed.symbol || parsed.ticker || "N/A").slice(0, 50),
      score: Number(parsed.score || 0),
      decision: String(parsed.decision || "Neutral").slice(0, 50),
      target_price: Number(parsed.target_price || 0),
      stop_loss: Number(parsed.stop_loss || 0),
    };
  } catch (error) {
    return { symbol: "ERR", score: 0, decision: "ParseError", target_price: 0, stop_loss: 0 };
  }
}

function cleanReport(text) {
  return text
    .replace(/<json>[\s\S]*?<\/json>/g, "")
    .replace(/```json\s*[\s\S]*?```/gi, "")
    .trim();
}

function extractFirstTicker(text) {
  const match = text.match(/\b\d{6}\b/);
  return match ? match[0] : "";
}

function extractAllTickers(text) {
  return [...new Set((text.match(/\b\d{6}\b/g) || []))];
}

function extractReportDate(text) {
  const label = "(?:\\uBD84\\uC11D\\s*\\uAE30\\uC900\\uC77C|\\uB370\\uC774\\uD130\\s*\\uAE30\\uC900\\uC77C|\\uAE30\\uC900\\uC77C|analysis\\s*date|as\\s*of)";
  const kr = text.match(new RegExp(`${label}\\s*[:\uFF1A-]?\\s*(\\d{4})\\s*\\uB144\\s*(\\d{1,2})\\s*\\uC6D4\\s*(\\d{1,2})\\s*\\uC77C`, "i"));
  if (kr) return `${kr[1]}-${String(kr[2]).padStart(2, "0")}-${String(kr[3]).padStart(2, "0")}`;
  const iso = text.match(new RegExp(`${label}\\s*[:\uFF1A-]?\\s*(\\d{4})[-./](\\d{1,2})[-./](\\d{1,2})`, "i"));
  if (iso) return `${iso[1]}-${String(iso[2]).padStart(2, "0")}-${String(iso[3]).padStart(2, "0")}`;
  return "";
}

function buildReasonLines(validation, localReasons) {
  const apiReasons = Array.isArray(validation?.blocking_reasons) ? validation.blocking_reasons : [];
  return [...localReasons, ...apiReasons].filter(Boolean).slice(0, 12);
}

function extractBlockedTickers(validation, fallbackTicker) {
  const tickers = [];
  const addTicker = (ticker) => {
    const normalized = String(ticker || "").trim();
    if (/^\d{6}$/.test(normalized) && !tickers.includes(normalized)) {
      tickers.push(normalized);
    }
  };

  const results = validation?.price_verification?.results;
  if (Array.isArray(results)) {
    for (const row of results) {
      const failed = row?.tradable === false || !["matched", "VERIFIED"].includes(String(row?.claim_status || row?.decision || ""));
      if (failed) addTicker(row?.ticker || row?.symbol);
    }
  }

  const reasons = Array.isArray(validation?.blocking_reasons) ? validation.blocking_reasons : [];
  for (const reason of reasons) {
    const match = String(reason).match(/\b\d{6}\b/);
    if (match) addTicker(match[0]);
  }

  if (!tickers.length) addTicker(fallbackTicker);
  return tickers;
}

async function fetchQuote(ticker) {
  if (!ticker) return null;
  try {
    const response = await this.helpers.httpRequest({
      method: "POST",
      url: "http://192.168.1.12:8010/quote",
      body: { symbol: ticker, force: true },
      json: true,
      timeout: 120000,
    });
    return response?.quote || null;
  } catch (error) {
    return null;
  }
}

async function fetchQuotes(tickers) {
  const quotes = [];
  for (const ticker of tickers) {
    const quote = await fetchQuote.call(this, ticker);
    if (quote) quotes.push(quote);
  }
  return quotes;
}

function correctedMessage(quotes, reasons) {
  const quoteList = Array.isArray(quotes) ? quotes : (quotes ? [quotes] : []);
  const base = quoteList.length ? quoteList.map((quote) => quote.message).join("\n\n") : [
    `\uC624\uB298(${todayKorean()}) \uAE30\uC900 \uAC80\uC99D \uAC00\uB2A5\uD55C \uD604\uC7AC\uAC00\uB97C \uB2E4\uC2DC \uC870\uD68C\uD574\uC57C \uD569\uB2C8\uB2E4.`,
  ].join("\n");
  return [
    "\uAE30\uC874 AI \uBCF4\uACE0\uC11C\uB294 \uB0A0\uC9DC \uB610\uB294 \uAC00\uACA9 \uAC80\uC99D \uC2E4\uD328\uB85C \uC804\uC1A1\uC744 \uCC28\uB2E8\uD588\uC2B5\uB2C8\uB2E4.",
    "",
    "\uAC80\uC99D \uC2E4\uD328 \uC885\uBAA9\uC758 \uD604\uC7AC \uAE30\uC900\uAC00:",
    "",
    base,
    "",
    "\uCC28\uB2E8 \uC0AC\uC720:",
    ...(reasons.length ? reasons.map((reason) => `- ${reason}`) : ["- \uAC80\uC99D \uC2E4\uD328"]),
  ].join("\n");
}

return await (async () => {
  try {
    const dbData = parseDbData(fullOutput);
    const cleanMessage = cleanReport(fullOutput);
    const allTickers = extractAllTickers(cleanMessage);
    const ticker = allTickers[0] || dbData.symbol;
    const expectedDate = todayKstIso();
    const reportDate = extractReportDate(cleanMessage);
    const localReasons = [];

    if (!reportDate) {
      localReasons.push("\uBCF4\uACE0\uC11C\uC5D0 '\uBD84\uC11D \uAE30\uC900\uC77C:' \uB77C\uBCA8\uC774 \uC5C6\uC5B4 \uB0A0\uC9DC \uAC80\uC99D\uC774 \uBD88\uC644\uC804\uD569\uB2C8\uB2E4.");
    }

    if (reportDate && reportDate !== expectedDate) {
      localReasons.push(`\uBCF4\uACE0\uC11C \uBD84\uC11D \uAE30\uC900\uC77C ${reportDate}\uAC00 \uC624\uB298 KST \uAE30\uC900\uC77C ${expectedDate}\uC640 \uB2E4\uB985\uB2C8\uB2E4.`);
    }

    const validation = await this.helpers.httpRequest({
      method: "POST",
      url: "http://192.168.1.12:8010/validate-report",
      body: { report_text: cleanMessage, days: 260, force: true },
      json: true,
      timeout: 120000,
    });

    const reasons = buildReasonLines(validation, localReasons);
    const blocked = !validation?.ok || validation.publishable === false || reasons.length > 0;

    if (blocked) {
      let blockedTickers = extractBlockedTickers(validation, ticker);
      const apiReasonCount = Array.isArray(validation?.blocking_reasons) ? validation.blocking_reasons.length : 0;
      if (localReasons.length && apiReasonCount === 0 && allTickers.length) {
        blockedTickers = allTickers;
      }
      const quotes = await fetchQuotes.call(this, blockedTickers);
      return [{
        json: {
          db_data: { symbol: "BLOCKED", score: 0, decision: "Blocked", target_price: 0, stop_loss: 0 },
          telegram_message: correctedMessage(quotes, reasons),
          can_publish: false,
          validation,
          blocked_tickers: blockedTickers,
          quotes,
          original_report: cleanMessage,
        },
      }];
    }

    return [{
      json: {
        db_data: dbData,
        telegram_message: cleanMessage,
        can_publish: true,
        validation,
      },
    }];
  } catch (error) {
    return [{
      json: {
        db_data: { symbol: "ERR", score: 0, decision: "Error", target_price: 0, stop_loss: 0 },
        telegram_message: `\uAC80\uC99D \uC911 \uC624\uB958 \uBC1C\uC0DD: ${error.message}`,
        can_publish: false,
      },
    }];
  }
})();
