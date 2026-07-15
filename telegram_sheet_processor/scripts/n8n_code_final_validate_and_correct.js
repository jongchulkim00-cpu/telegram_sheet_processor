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

function ensureDateHeader(text) {
  const trimmed = String(text || "").trim();
  const hasAnalysisLabel = /(?:\uBD84\uC11D\s*\uAE30\uC900\uC77C|analysis\s*date)\s*[:\uFF1A-]?/i.test(trimmed);
  if (hasAnalysisLabel) return trimmed;
  return [
    `\uBD84\uC11D \uAE30\uC900\uC77C: ${todayKstIso()}`,
    `\uB370\uC774\uD130 \uAE30\uC900\uC77C: ${todayKstIso()}`,
    "",
    trimmed,
  ].join("\n");
}

function extractFirstTicker(text) {
  const match = text.match(/\b\d{6}\b/);
  return match ? match[0] : "";
}

function extractAllTickers(text) {
  return [...new Set((text.match(/\b\d{6}\b/g) || []))];
}

function extractReportDate(text) {
  const label = "(?:\\uBD84\\uC11D\\s*\\uAE30\\uC900\\uC77C|\\uBD84\\uC11D\\uC77C|analysis\\s*date)";
  const kr = text.match(new RegExp(`${label}\\s*[:\uFF1A-]?\\s*(\\d{4})\\s*\\uB144\\s*(\\d{1,2})\\s*\\uC6D4\\s*(\\d{1,2})\\s*\\uC77C`, "i"));
  if (kr) return `${kr[1]}-${String(kr[2]).padStart(2, "0")}-${String(kr[3]).padStart(2, "0")}`;
  const iso = text.match(new RegExp(`${label}\\s*[:\uFF1A-]?\\s*(\\d{4})[-./](\\d{1,2})[-./](\\d{1,2})`, "i"));
  if (iso) return `${iso[1]}-${String(iso[2]).padStart(2, "0")}-${String(iso[3]).padStart(2, "0")}`;
  return "";
}

function hasStockPriceClaimWithoutTicker(text) {
  return /(?:\uD604\uC7AC\uAC00|\uD604\uC7AC\s*\uC2DC\uC138|current\s*(?:price|quote)).{0,80}?([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\s*\uC6D0/i.test(text);
}

function hasStockPriceClaim(text) {
  return /(?:\uACF5\uAC1C\s*)?(?:\uD604\uC7AC\uAC00|\uD604\uC7AC\s*\uC2DC\uC138|\uD604\uC7AC\s*\uC8FC\uAC00|current\s*(?:price|quote)|market\s*price|last\s*price).{0,80}?([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\s*\uC6D0/i.test(text);
}

function hasStrategyPriceClaim(text) {
  return /(?:\uBAA9\uD45C\uAC00|\uC190\uC808\uAC00|\uB9E4\uC218.{0,12}?\uAD6C\uAC04|target\s*price|price\s*target|stop\s*loss|buy.{0,12}?(?:range|zone|area)).{0,100}?([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\s*\uC6D0/i.test(text);
}

function hasDbJsonPayload(text) {
  return /<json>[\s\S]*?<\/json>/i.test(text) || /```json\s*[\s\S]*?```/i.test(text);
}

function isTickerMarketBriefing(text, tickers) {
  return (
    Array.isArray(tickers) &&
    tickers.length > 0 &&
    !hasDbJsonPayload(text) &&
    !hasStockPriceClaim(text) &&
    !hasStrategyPriceClaim(text)
  );
}

function isAvoidanceResponse(text) {
  return /(?:\uC885\uBAA9\uBCC4\s*\uC815\uBC00\s*\uBD84\uC11D\uC5D0\s*\uCD5C\uC801\uD654|\uC2A4\uD06C\uB9AC\uB2DD\uD558\uC5EC\s*\uB9AC\uC2A4\uD2B8\uC5C5\uD558\uB294\s*\uAE30\uB2A5\uC740\s*\uC81C\uD55C|\uAD00\uC2EC\uC744\s*\uAC00\uC9C0\uC2DC\uB294\s*\uC139\uD130|\uD2B9\uC815\s*\uC885\uBAA9.*\uB9D0\uC500|\uB9D0\uC500\uD574\uC8FC\uC2DC\uBA74.*\uBD84\uC11D|\uC2EC\uCE35\s*\uBD84\uC11D\uC744\s*\uC2DC\uC791)/i.test(text);
}

function isNonBlockingReason(reason) {
  const text = String(reason || "");
  return (
    /News\/disclosure\/sentiment claims exist without source URLs/i.test(text) ||
    /source URLs.*unverified/i.test(text) ||
    /뉴스|공시|센티먼트|근거\s*URL|출처\s*URL/i.test(text) && /없|미확인|미검증|unverified/i.test(text)
  );
}

function buildReasonState(validation, localReasons) {
  const apiReasons = Array.isArray(validation?.blocking_reasons) ? validation.blocking_reasons : [];
  const warningFields = [
    ...(Array.isArray(validation?.non_blocking_warnings) ? validation.non_blocking_warnings : []),
    ...(Array.isArray(validation?.evidence_warnings) ? validation.evidence_warnings : []),
  ];
  const allReasons = [...localReasons, ...apiReasons].filter(Boolean);
  const blocking = allReasons.filter((reason) => !isNonBlockingReason(reason)).slice(0, 12);
  const warnings = [...allReasons.filter(isNonBlockingReason), ...warningFields].filter(Boolean).slice(0, 12);
  const apiHadOnlyNonBlockingReasons = apiReasons.length > 0 && apiReasons.every(isNonBlockingReason);
  return {
    blocking,
    warnings,
    apiHadOnlyNonBlockingReasons,
  };
}

function classifyBlockReason(reasons) {
  const joined = reasons.join("\n").toLowerCase();
  const hasDate = /date|기준일|날짜/.test(joined);
  const hasPrice = /price|현재가|시세|주가|목표가|손절가|mismatch|verified/.test(joined);
  if (hasDate && hasPrice) return "날짜 또는 가격 검증 실패";
  if (hasDate) return "날짜 검증 실패";
  if (hasPrice) return "가격 검증 실패";
  return "검증 정책 실패";
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
  const reasonLabel = classifyBlockReason(reasons);
  return [
    `\uAE30\uC874 AI \uBCF4\uACE0\uC11C\uB294 ${reasonLabel}\uB85C \uC804\uC1A1\uC744 \uCC28\uB2E8\uD588\uC2B5\uB2C8\uB2E4.`,
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
    let cleanMessage = cleanReport(fullOutput);
    const allTickers = extractAllTickers(cleanMessage);
    const ticker = allTickers[0] || dbData.symbol;
    const expectedDate = todayKstIso();
    const reportDate = extractReportDate(cleanMessage);
    const localReasons = [];

    if (isAvoidanceResponse(cleanMessage)) {
      const messageWithDate = ensureDateHeader([
        "\uC5D0\uC774\uC804\uD2B8\uAC00 \uAE30\uBCF8 \uD6C4\uBCF4\uAD70 \uC2A4\uD06C\uB9AC\uB2DD\uC744 \uC218\uD589\uD558\uC9C0 \uC54A\uACE0 \uC0AC\uC6A9\uC790\uC5D0\uAC8C \uB2E4\uC2DC \uC9C8\uBB38\uD588\uC2B5\uB2C8\uB2E4.",
        "",
        "\uC870\uCE58: \uAE30\uBCF8 \uD6C4\uBCF4\uAD70(\uBC18\uB3C4\uCCB4, 2\uCC28\uC804\uC9C0, \uC790\uB3D9\uCC28, \uBC14\uC774\uC624) 5~10\uAC1C\uB97C \uC790\uB3D9 \uC120\uC815\uD558\uACE0 stock API /analyze-batch\uB85C \uC7AC\uC791\uC131\uD574\uC57C \uD569\uB2C8\uB2E4.",
      ].join("\n"));
      return [{
        json: {
          db_data: { symbol: "BLOCKED", score: 0, decision: "AvoidanceResponse", target_price: 0, stop_loss: 0 },
          telegram_message: messageWithDate,
          can_publish: true,
          can_send_telegram: true,
          can_insert_db: false,
          report_publishable: false,
          validation: {
            ok: false,
            publishable: false,
            report_guard_status: "avoidance_response",
            expected_analysis_date: expectedDate,
            blocking_reasons: [
              "AI agent asked the user for a sector/ticker instead of running the default screening workflow.",
            ],
          },
          original_report: cleanMessage,
        },
      }];
    }

    if (!allTickers.length && !hasStockPriceClaimWithoutTicker(cleanMessage)) {
      const messageWithDate = ensureDateHeader(cleanMessage);
      return [{
        json: {
          db_data: { symbol: "INFO", score: 0, decision: "MarketContext", target_price: 0, stop_loss: 0 },
          telegram_message: messageWithDate,
          can_publish: true,
          can_send_telegram: true,
          can_insert_db: false,
          report_publishable: true,
          validation: {
            ok: true,
            publishable: true,
            report_guard_status: "informational_no_ticker",
            expected_analysis_date: expectedDate,
            note: "No stock ticker or stock price claim found; treated as market context, not a per-stock investment report.",
          },
          original_report: cleanMessage,
        },
      }];
    }

    if (isTickerMarketBriefing(cleanMessage, allTickers)) {
      const messageWithDate = ensureDateHeader(cleanMessage);
      return [{
        json: {
          db_data: { symbol: "INFO", score: 0, decision: "MarketContext", target_price: 0, stop_loss: 0 },
          telegram_message: messageWithDate,
          can_publish: true,
          can_send_telegram: true,
          can_insert_db: false,
          report_publishable: true,
          validation: {
            ok: true,
            publishable: true,
            report_guard_status: "informational_ticker_briefing",
            expected_analysis_date: expectedDate,
            tickers: allTickers,
            note: "Ticker briefing without current/target/stop price claims; treated as market context, not a per-stock investment report.",
          },
          original_report: cleanMessage,
        },
      }];
    }

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

    const reasonState = buildReasonState(validation, localReasons);
    const reasons = reasonState.blocking;
    const legacyEvidenceOnlyBlock =
      validation?.publishable === false &&
      reasonState.apiHadOnlyNonBlockingReasons &&
      reasons.length === 0 &&
      localReasons.length === 0;
    const blocked = !validation?.ok || reasons.length > 0 || (validation.publishable === false && !legacyEvidenceOnlyBlock);

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
          can_publish: true,
          can_send_telegram: true,
          can_insert_db: false,
          report_publishable: false,
          validation,
          non_blocking_warnings: reasonState.warnings,
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
        can_send_telegram: true,
        can_insert_db: !["N/A", "INFO", "BLOCKED", "ERR"].includes(String(dbData.symbol || "")),
        report_publishable: true,
        non_blocking_warnings: reasonState.warnings,
        validation,
      },
    }];
  } catch (error) {
    return [{
      json: {
        db_data: { symbol: "ERR", score: 0, decision: "Error", target_price: 0, stop_loss: 0 },
        telegram_message: `\uAC80\uC99D \uC911 \uC624\uB958 \uBC1C\uC0DD: ${error.message}`,
        can_publish: true,
        can_send_telegram: true,
        can_insert_db: false,
        report_publishable: false,
      },
    }];
  }
})();
