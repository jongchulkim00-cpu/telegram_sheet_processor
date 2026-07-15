#!/usr/bin/env python3
"""HTTP API wrapper for the Korean stock precision connector.

This file intentionally sits next to, not inside, market_data.py so the
existing CLI analysis flow remains usable if the API layer has trouble.
"""
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import AliasChoices, BaseModel, Field

try:
    from . import market_data
    from . import preview_review_engine
except ImportError:
    import market_data
    import preview_review_engine

APP_VERSION = "0.1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STOCK_UNIVERSE_CACHE: dict[str, Any] = {"rows": None, "generated_at": None, "source": None}
HOT_TECH_ITEMS = [
    {"ticker": "NVDA", "name": "NVIDIA"},
    {"ticker": "TSLA", "name": "Tesla"},
    {"ticker": "AAPL", "name": "Apple"},
    {"ticker": "MSFT", "name": "Microsoft"},
    {"ticker": "AMD", "name": "AMD"},
]
ON_DEVICE_AI_ITEMS = [
    {"ticker": "399720", "name": "가온칩스"},
    {"ticker": "080220", "name": "제주반도체"},
    {"ticker": "394280", "name": "오픈엣지테크놀로지"},
    {"ticker": "094360", "name": "칩스앤미디어"},
    {"ticker": "432720", "name": "퀄리타스반도체"},
]
DEFAULT_KR_ITEMS = [
    {"ticker": "005930", "name": "삼성전자", "market": "KOSPI"},
    {"ticker": "000660", "name": "SK하이닉스", "market": "KOSPI"},
    {"ticker": "005380", "name": "현대차", "market": "KOSPI"},
    {"ticker": "005490", "name": "POSCO홀딩스", "market": "KOSPI"},
    {"ticker": "373220", "name": "LG에너지솔루션", "market": "KOSPI"},
    {"ticker": "042700", "name": "한미반도체", "market": "KOSPI"},
    {"ticker": "039030", "name": "이오테크닉스", "market": "KOSDAQ"},
    {"ticker": "080220", "name": "제주반도체", "market": "KOSDAQ"},
    {"ticker": "399720", "name": "가온칩스", "market": "KOSDAQ"},
    {"ticker": "011790", "name": "SKC", "market": "KOSPI"},
    {"ticker": "196170", "name": "알테오젠", "market": "KOSDAQ"},
    {"ticker": "247540", "name": "에코프로비엠", "market": "KOSDAQ"},
]

app = FastAPI(
    title="Korean Stock Precision API",
    version=APP_VERSION,
    description="n8n/MCP friendly API for Korean stock OHLCV, indicators, scoring, and chart generation.",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=200,
        content=api_error(
            ValueError("Bad request parameters"),
            {
                "path": str(request.url.path),
                "details": exc.errors(),
                "hint": "For n8n, send JSON body. /validate-report accepts report_text, text, output, message, result, or item.json.output. /verify-prices accepts claims or a single ticker row.",
            },
        ),
    )


class AnalyzeRequest(BaseModel):
    ticker: str = Field(
        ...,
        validation_alias=AliasChoices("ticker", "symbol"),
        description="Korean stock code, for example 196170. n8n may send this as symbol.",
    )
    name: Optional[str] = Field(default=None, description="Human-readable stock name")
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    days: int = Field(default=260, ge=60, le=1200)
    force: bool = Field(default=False, description="Fetch live data even if cache is fresh")


class AnalyzeBatchRequest(BaseModel):
    items: list[AnalyzeRequest]
    days: int = Field(default=260, ge=60, le=1200)
    force: bool = False


class HotTechRequest(BaseModel):
    days: int = Field(default=260, ge=60, le=1200)
    force: bool = Field(default=False, description="Fetch live data even if cache is fresh")


class ThemeRequest(BaseModel):
    days: int = Field(default=260, ge=60, le=1200)
    force: bool = Field(default=False, description="Fetch live data even if cache is fresh")


class PriceClaim(BaseModel):
    ticker: str = Field(
        ...,
        validation_alias=AliasChoices("ticker", "symbol"),
        description="Korean stock code, for example 000660. n8n may send this as symbol.",
    )
    name: Optional[str] = None
    claimed_price: Optional[float] = Field(default=None, description="Price shown in an AI report")
    buy_low: Optional[float] = Field(default=None, description="Lower bound of buy range shown in an AI report")
    buy_high: Optional[float] = Field(default=None, description="Upper bound of buy range shown in an AI report")
    target_price: Optional[float] = Field(default=None, description="Target price shown in an AI report")
    stop_loss: Optional[float] = Field(default=None, description="Stop loss shown in an AI report")


class VerifyPricesRequest(BaseModel):
    claims: list[PriceClaim]
    days: int = Field(default=260, ge=60, le=1200)
    force: bool = Field(default=False, description="Fetch live data even if cache is fresh")


class ValidateReportRequest(BaseModel):
    report_text: str = Field(..., description="Full AI-generated report text before Telegram publishing")
    days: int = Field(default=260, ge=60, le=1200)
    force: bool = Field(default=False, description="Fetch live data even if cache is fresh")


class QuoteRequest(BaseModel):
    ticker: str = Field(
        ...,
        validation_alias=AliasChoices("ticker", "symbol"),
        description="Korean stock code, for example 399720. n8n may send this as symbol.",
    )
    name: Optional[str] = Field(default=None, description="Human-readable stock name")
    days: int = Field(default=260, ge=60, le=1200)
    force: bool = Field(default=False, description="Fetch live data even if cache is fresh")


class PreviewReviewRequest(BaseModel):
    ticker: str = Field(
        ...,
        validation_alias=AliasChoices("ticker", "symbol"),
        description="Korean stock code, for example 080220.",
    )
    name: Optional[str] = Field(default=None, description="Human-readable stock name")
    days: int = Field(default=260, ge=60, le=1200)
    force: bool = Field(default=False, description="Fetch live data even if cache is fresh")


class PreviewReviewBatchRequest(BaseModel):
    items: list[PreviewReviewRequest]
    days: int = Field(default=260, ge=60, le=1200)
    force: bool = False


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_item(request: AnalyzeRequest) -> dict[str, Any]:
    return {
        "ticker": request.ticker.strip(),
        "name": request.name or request.ticker.strip(),
        "target_price": request.target_price,
        "stop_loss": request.stop_loss,
    }


def api_success(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "api_version": APP_VERSION,
        "generated_at": now_utc(),
        **payload,
    }


def api_error(error: Exception, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {
        "ok": False,
        "api_version": APP_VERSION,
        "generated_at": now_utc(),
        "error": str(error),
        **(payload or {}),
    }


async def read_json_body(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {"value": payload}


def nested_get(data: dict[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = data
        ok = True
        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                ok = False
                break
        if ok and current not in [None, ""]:
            return current
    return None


def report_text_from_payload(payload: dict[str, Any]) -> str:
    value = nested_get(
        payload,
        "report_text",
        "text",
        "output",
        "message",
        "result",
        "data.output",
        "data.text",
        "json.output",
        "json.text",
        "item.json.output",
        "item.json.text",
    )
    if isinstance(value, dict):
        for key in ["output", "text", "message", "content"]:
            if value.get(key):
                return str(value[key])
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value or "")


def claims_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    claims = payload.get("claims")
    if isinstance(claims, list):
        return claims
    if isinstance(claims, dict):
        return [claims]
    items = payload.get("items") or payload.get("rows")
    if isinstance(items, list):
        return items
    ticker = payload.get("ticker") or payload.get("symbol")
    if ticker:
        return [{
            "ticker": ticker,
            "name": payload.get("name"),
            "claimed_price": payload.get("claimed_price") or payload.get("current_price") or payload.get("price"),
            "buy_low": payload.get("buy_low"),
            "buy_high": payload.get("buy_high"),
            "target_price": payload.get("target_price"),
            "stop_loss": payload.get("stop_loss"),
        }]
    return []


def int_from_payload(payload: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(payload.get(key, default))
    except Exception:
        return default


def bool_from_payload(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in ["1", "true", "yes", "y"]
    return bool(value)


def load_stock_universe(force: bool = False) -> tuple[list[dict[str, Any]], str]:
    if not force and _STOCK_UNIVERSE_CACHE.get("rows"):
        return _STOCK_UNIVERSE_CACHE["rows"], str(_STOCK_UNIVERSE_CACHE.get("source") or "cache")

    rows: list[dict[str, Any]] = []
    source = "fallback"
    try:
        from pykrx import stock

        for market in ["KOSPI", "KOSDAQ"]:
            for ticker in stock.get_market_ticker_list(market=market):
                name = stock.get_market_ticker_name(ticker)
                if name:
                    rows.append({"ticker": ticker, "name": name, "market": market})
        if rows:
            source = "pykrx"
    except Exception:
        rows = []

    if not rows:
        rows.extend(DEFAULT_KR_ITEMS)
        for cache_file in sorted(market_data.CACHE_DIR.glob("*_ohlcv.csv")):
            ticker = cache_file.name.replace("_ohlcv.csv", "")
            if not ticker.isdigit() or len(ticker) != 6:
                continue
            if any(item["ticker"] == ticker for item in rows):
                continue
            rows.append({
                "ticker": ticker,
                "name": market_data.lookup_pykrx_name(ticker) or ticker,
                "market": "UNKNOWN",
            })

    deduped = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip()
        if ticker:
            deduped[ticker] = {
                "ticker": ticker,
                "name": str(row.get("name") or ticker),
                "market": str(row.get("market") or "UNKNOWN"),
            }
    output = sorted(deduped.values(), key=lambda item: (item["market"], item["ticker"]))
    _STOCK_UNIVERSE_CACHE.update({"rows": output, "generated_at": now_utc(), "source": source})
    return output, source


def search_stock_universe(query: str, limit: int = 20, force: bool = False) -> dict[str, Any]:
    query = str(query or "").strip()
    limit = max(1, min(int(limit or 20), 50))
    rows, source = load_stock_universe(force=force)
    if not query:
        return {"query": query, "source": source, "count": 0, "results": []}

    lowered = query.lower()
    digits = "".join(ch for ch in query if ch.isdigit())
    scored = []
    for row in rows:
        ticker = row["ticker"]
        name = row["name"]
        name_lower = name.lower()
        score = None
        if ticker == query or name == query:
            score = 0
        elif digits and ticker.startswith(digits):
            score = 1
        elif name_lower.startswith(lowered):
            score = 2
        elif digits and digits in ticker:
            score = 3
        elif lowered in name_lower:
            score = 4
        if score is not None:
            scored.append((score, ticker, row))
    scored.sort(key=lambda item: (item[0], item[1]))
    results = [item[2] for item in scored[:limit]]
    return {
        "query": query,
        "source": source,
        "universe_count": len(rows),
        "count": len(results),
        "results": results,
    }


def analyze_one(request: AnalyzeRequest) -> dict[str, Any]:
    item = normalize_item(request)
    fetch = market_data.fetch_ohlcv(
        item["ticker"],
        item["name"],
        days=request.days,
        force=request.force,
    )
    frame, score = market_data.score_stock(
        fetch.frame,
        item.get("target_price"),
        item.get("stop_loss"),
    )
    validation = market_data.cross_validate_ohlcv(item["ticker"], fetch.frame, days=request.days)
    score = market_data.apply_validation_to_score(score, validation)
    chart_path = market_data.make_chart(item["ticker"], item["name"], frame)
    result = {
        "ticker": item["ticker"],
        "name": item["name"],
        "provider": fetch.provider,
        "rows": fetch.rows,
        "analysis_date": score["analysis_date"],
        "data_as_of": score["data_as_of"],
        "data_age_days": score["data_age_days"],
        "freshness_status": score["freshness_status"],
        "tradable": score["tradable"],
        "no_recommendation_reason": score["no_recommendation_reason"],
        "latest_date": score["latest_date"],
        "latest_close": score["latest_close"],
        "decision": score["decision"],
        "score": score["score"],
        "technical_score": score["technical_score"],
        "target_price": item.get("target_price"),
        "stop_loss": item.get("stop_loss"),
        "indicators": score["indicators"],
        "validation": validation,
        "reasons": score["reasons"],
        "warnings": fetch.warnings,
        "chart_path": str(chart_path),
        "cache_path": str(fetch.cache_path),
    }
    result["db_row"] = make_db_row(result)
    return result


def decision_code(decision: str) -> str:
    mapping = {
        "Strong Buy": "STRONG_BUY",
        "Buy": "BUY",
        "Hold": "HOLD",
        "Reduce": "REDUCE",
        "DATA_STALE": "DATA_STALE",
        "DATA_MISMATCH": "MISMATCH",
    }
    return mapping.get(decision, str(decision or "UNKNOWN")[:10].upper())


def make_db_row(result: dict[str, Any]) -> dict[str, Any]:
    indicators = result.get("indicators", {})
    reasons = result.get("reasons", [])
    warnings = result.get("warnings", [])
    return {
        "symbol": str(result.get("ticker", ""))[:10],
        "ticker": str(result.get("ticker", ""))[:10],
        "name": str(result.get("name", ""))[:80],
        "decision": decision_code(result.get("decision", "")),
        "score": result.get("score"),
        "technical_score": result.get("technical_score"),
        "analysis_date": result.get("analysis_date"),
        "data_as_of": result.get("data_as_of"),
        "data_age_days": result.get("data_age_days"),
        "freshness_status": str(result.get("freshness_status", ""))[:16],
        "tradable": result.get("tradable"),
        "no_recommendation_reason": result.get("no_recommendation_reason"),
        "validation_status": str(result.get("validation", {}).get("status", ""))[:24],
        "source_close_diff_pct": result.get("validation", {}).get("close_diff_pct"),
        "source_date_diff_days": result.get("validation", {}).get("date_diff_days"),
        "latest_date": result.get("latest_date"),
        "latest_close": result.get("latest_close"),
        "provider": str(result.get("provider", ""))[:32],
        "rsi14": indicators.get("rsi14"),
        "sma20": indicators.get("sma20"),
        "sma60": indicators.get("sma60"),
        "macd_histogram": indicators.get("macd_histogram"),
        "chart_path": result.get("chart_path"),
        "summary": "; ".join(str(reason) for reason in reasons),
        "warnings": "; ".join(str(warning) for warning in warnings),
        "raw_json": json.dumps(result, ensure_ascii=False, default=str),
    }


def quote_payload(ticker: str, name: Optional[str] = None, days: int = 260, force: bool = False) -> dict[str, Any]:
    ticker = ticker.strip()
    display_name = name or market_data.lookup_pykrx_name(ticker) or ticker
    fetch = market_data.fetch_ohlcv(ticker, display_name, days=days, force=force)
    validation = market_data.cross_validate_ohlcv(ticker, fetch.frame, days=days)
    meta = market_data.latest_data_meta(fetch.frame)
    latest = fetch.frame.iloc[-1]
    daily_close = round(float(latest["close"]), 4)
    public_quote = market_data.fetch_best_current_quote(ticker)

    if public_quote.get("ok"):
        quote_price = round(float(public_quote["price"]), 4)
        quote_source = public_quote["provider"]
        quote_url = public_quote.get("url")
    else:
        quote_price = daily_close
        quote_source = fetch.provider
        quote_url = None

    realtime = market_data.realtime_source_status()
    kiwoom = market_data.kiwoom_source_status()
    kiwoom_rest = market_data.kiwoom_rest_source_status()
    broker_realtime_enabled = bool(
        realtime.get("allows_current_price_wording")
        or kiwoom.get("allows_current_price_wording")
        or kiwoom_rest.get("allows_current_price_wording")
    )
    quote_label = "broker_realtime" if broker_realtime_enabled else "public_current_quote"
    quote_wording = "\uc2e4\uc2dc\uac04 \ud604\uc7ac\uac00" if broker_realtime_enabled else "\uacf5\uac1c \ud604\uc7ac\uac00"

    message = (
        f"{display_name}({ticker}) {quote_wording}: {quote_price:,.0f}\uc6d0\n"
        f"\ubd84\uc11d \uae30\uc900\uc77c: {market_data.today_kst().isoformat()}\n"
        f"\ub370\uc774\ud130 \uae30\uc900\uc77c: {meta.get('data_as_of')}\n"
        f"\ucd9c\ucc98: {quote_source}"
    )
    if quote_url:
        message += f"\nURL: {quote_url}"

    return {
        "ticker": ticker,
        "name": display_name,
        "quote_price": quote_price,
        "quote_label": quote_label,
        "quote_wording": quote_wording,
        "quote_source": quote_source,
        "quote_url": quote_url,
        "broker_realtime_enabled": broker_realtime_enabled,
        "public_quote": public_quote,
        "daily_close": daily_close,
        "daily_provider": fetch.provider,
        "analysis_date": market_data.today_kst().isoformat(),
        "data_as_of": meta.get("data_as_of"),
        "data_age_days": meta.get("data_age_days"),
        "freshness_status": meta.get("freshness_status"),
        "tradable": bool(meta.get("tradable")) and bool(validation.get("tradable", True)),
        "validation": validation,
        "message": message,
        "policy": "Do not label this as broker-grade realtime unless broker_realtime_enabled=true.",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return api_success({
        "service": "korean-stock-precision-api",
        "analysis_date": market_data.today_kst().isoformat(),
        "project_root": str(PROJECT_ROOT),
        "data_dir": str(market_data.DATA_DIR),
        "output_dir": str(market_data.OUTPUT_DIR),
        "max_data_age_days": market_data.MAX_DATA_AGE_DAYS,
        "allow_stale_cache": market_data.ALLOW_STALE_CACHE,
        "port_policy": "Use existing service port only; no additional port is required.",
    })


@app.get("/source-status")
def source_status() -> dict[str, Any]:
    return api_success({
        "quote_sources": market_data.quote_source_status(),
        "realtime_source": market_data.realtime_source_status(),
        "daily_sources": [
            {"provider": "pykrx", "role": "primary daily OHLCV / KRX based validation"},
            {"provider": "FinanceDataReader", "role": "secondary daily OHLCV fallback"},
        ],
        "wording_policy": "Use realtime wording only when realtime_source.configured=true. Without KIS, use public current quote or recent trading-day close(data_as_of), never broker-grade realtime wording.",
    })


@app.get("/quote/{ticker}")
def quote_get(ticker: str, name: Optional[str] = None, days: int = 260, force: bool = False) -> dict[str, Any]:
    try:
        return api_success({"quote": quote_payload(ticker, name=name, days=days, force=force)})
    except Exception as exc:
        return api_error(exc, {"ticker": ticker, "name": name})


@app.post("/quote")
async def quote_post(request: Request) -> dict[str, Any]:
    body = await read_json_body(request)
    ticker = str(body.get("ticker") or body.get("symbol") or "").strip()
    if not ticker:
        return api_error(ValueError("ticker or symbol is required"), {
            "received_keys": list(body.keys()),
            "hint": "Send {ticker:'399720'} or {symbol:'399720'}.",
        })
    try:
        return api_success({
            "quote": quote_payload(
                ticker,
                name=body.get("name"),
                days=int_from_payload(body, "days", 260),
                force=bool_from_payload(body, "force", False),
            )
        })
    except Exception as exc:
        return api_error(exc, {"ticker": ticker, "name": body.get("name")})


@app.get("/cache-audit")
def cache_audit(tickers: Optional[str] = None) -> dict[str, Any]:
    if tickers:
        symbols = [ticker.strip() for ticker in tickers.split(",") if ticker.strip()]
    else:
        symbols = sorted(path.name.replace("_ohlcv.csv", "") for path in market_data.CACHE_DIR.glob("*_ohlcv.csv"))
    rows = [market_data.cache_meta(symbol) for symbol in symbols]
    return api_success({
        "count": len(rows),
        "stale_count": sum(1 for row in rows if row.get("stale")),
        "allow_stale_cache": market_data.ALLOW_STALE_CACHE,
        "max_data_age_days": market_data.MAX_DATA_AGE_DAYS,
        "rows": rows,
        "policy": "Stale cache is blocked by default. Set ALLOW_STALE_CACHE=true only for diagnostics.",
    })


@app.get("/stocks/search")
def stocks_search(q: str = "", limit: int = 20, force: bool = False) -> dict[str, Any]:
    try:
        return api_success(search_stock_universe(q, limit=limit, force=force))
    except Exception as exc:
        return api_error(exc, {"query": q, "limit": limit})


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict[str, Any]:
    try:
        return api_success({"result": analyze_one(request)})
    except Exception as exc:
        return api_error(exc, {"ticker": request.ticker, "name": request.name})


@app.post("/analyze-batch")
def analyze_batch(request: AnalyzeBatchRequest) -> dict[str, Any]:
    results = []
    errors = []
    for item in request.items:
        effective = item.copy(update={
            "days": request.days,
            "force": item.force or request.force,
        })
        try:
            results.append(analyze_one(effective))
        except Exception as exc:
            errors.append({
                "ticker": item.ticker,
                "name": item.name,
                "error": str(exc),
            })
    return api_success({
        "count": len(results),
        "error_count": len(errors),
        "results": results,
        "db_rows": [row["db_row"] for row in results],
        "errors": errors,
    })


@app.post("/hot-tech")
def hot_tech(request: HotTechRequest) -> dict[str, Any]:
    results = []
    errors = []
    for item in HOT_TECH_ITEMS:
        try:
            effective = AnalyzeRequest(
                ticker=item["ticker"],
                name=item["name"],
                days=request.days,
                force=request.force,
            )
            results.append(analyze_one(effective))
        except Exception as exc:
            errors.append({
                "ticker": item["ticker"],
                "name": item["name"],
                "error": str(exc),
            })
    return api_success({
        "universe": "US_HOT_TECH",
        "count": len(results),
        "error_count": len(errors),
        "results": results,
        "db_rows": [row["db_row"] for row in results],
        "errors": errors,
        "data_policy": "No recommendation is generated for symbols that fail data collection.",
        "freshness_policy": f"decision is DATA_STALE and tradable=false when data_age_days exceeds {market_data.MAX_DATA_AGE_DAYS}.",
        "validation_policy": f"decision is DATA_MISMATCH and tradable=false when close diff exceeds {market_data.MAX_CLOSE_DIFF_PCT}% or source date diff exceeds {market_data.MAX_SOURCE_DATE_DIFF_DAYS} day.",
        "max_data_age_days": market_data.MAX_DATA_AGE_DAYS,
    })


@app.post("/theme/on-device-ai")
def on_device_ai(request: ThemeRequest) -> dict[str, Any]:
    results = []
    errors = []
    for item in ON_DEVICE_AI_ITEMS:
        try:
            effective = AnalyzeRequest(
                ticker=item["ticker"],
                name=item["name"],
                days=request.days,
                force=request.force,
            )
            results.append(analyze_one(effective))
        except Exception as exc:
            errors.append({
                "ticker": item["ticker"],
                "name": item["name"],
                "error": str(exc),
            })
    return api_success({
        "universe": "KR_ON_DEVICE_AI",
        "count": len(results),
        "error_count": len(errors),
        "analysis_date": market_data.today_kst().isoformat(),
        "results": results,
        "db_rows": [row["db_row"] for row in results],
        "errors": errors,
        "data_policy": "Use data_as_of, not generated_at, as the candle/indicator 기준일. DATA_STALE rows must not be recommended.",
        "freshness_policy": f"decision is DATA_STALE and tradable=false when data_age_days exceeds {market_data.MAX_DATA_AGE_DAYS}.",
        "validation_policy": f"decision is DATA_MISMATCH and tradable=false when close diff exceeds {market_data.MAX_CLOSE_DIFF_PCT}% or source date diff exceeds {market_data.MAX_SOURCE_DATE_DIFF_DAYS} day.",
        "max_data_age_days": market_data.MAX_DATA_AGE_DAYS,
    })


def compact_preview_review(result: dict[str, Any]) -> dict[str, Any]:
    ticker = str(result.get("ticker", ""))
    chart_url = f"/preview-review/chart/{ticker}" if ticker else None
    return {
        **result,
        "chart_url": chart_url,
        "policy": {
            "initial_order_budget_krw": preview_review_engine.INITIAL_ORDER_BUDGET_KRW,
            "watchlist_limit": 50,
            "stage": "daily_preview_review_before_kiwoom_intraday",
            "order_policy": "Review only. Do not auto-order from daily review signals.",
        },
    }


@app.post("/preview-review")
def preview_review(request: PreviewReviewRequest) -> dict[str, Any]:
    try:
        name = request.name or market_data.lookup_pykrx_name(request.ticker) or request.ticker
        result = preview_review_engine.run(
            request.ticker.strip(),
            name=name,
            days=request.days,
            force=request.force,
        )
        return api_success({"review": compact_preview_review(result)})
    except Exception as exc:
        return api_error(exc, {"ticker": request.ticker, "name": request.name})


@app.post("/preview-review-batch")
def preview_review_batch(request: PreviewReviewBatchRequest) -> dict[str, Any]:
    results = []
    errors = []
    for item in request.items[:50]:
        effective = item.copy(update={
            "days": request.days,
            "force": item.force or request.force,
        })
        try:
            name = effective.name or market_data.lookup_pykrx_name(effective.ticker) or effective.ticker
            result = preview_review_engine.run(
                effective.ticker.strip(),
                name=name,
                days=effective.days,
                force=effective.force,
            )
            results.append(compact_preview_review(result))
        except Exception as exc:
            errors.append({
                "ticker": item.ticker,
                "name": item.name,
                "error": str(exc),
            })
    return api_success({
        "count": len(results),
        "error_count": len(errors),
        "max_items": 50,
        "results": results,
        "errors": errors,
        "policy": "Batch review is capped at 50 symbols to match the watchlist limit.",
    })


@app.get("/preview-review/chart/{ticker}")
def preview_review_chart(ticker: str):
    safe_ticker = "".join(ch for ch in ticker if ch.isalnum())
    path = preview_review_engine.OUTPUT_DIR / f"{safe_ticker}_preview_review.html"
    if not path.exists():
        return JSONResponse(
            status_code=404,
            content=api_error(FileNotFoundError(path), {
                "ticker": safe_ticker,
                "hint": "Run POST /preview-review first.",
            }),
        )
    return FileResponse(path, media_type="text/html")


@app.get("/review-ui", response_class=HTMLResponse)
def review_ui() -> str:
    return """
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Preview / Review Lab</title>
  <style>
    :root { color-scheme: light; --bg:#f7f8fb; --panel:#fff; --ink:#172033; --muted:#657084; --line:#d9dfeb; --accent:#2563eb; --good:#138a45; --warn:#b7791f; --bad:#c53030; }
    body { margin:0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background:var(--bg); color:var(--ink); }
    header { padding:20px 24px; border-bottom:1px solid var(--line); background:#fff; position:sticky; top:0; z-index:2; }
    h1 { margin:0 0 6px; font-size:22px; }
    p { margin:0; color:var(--muted); }
    main { display:grid; grid-template-columns: 360px 1fr; gap:16px; padding:16px; }
    section { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px; }
    label { display:block; font-size:13px; color:var(--muted); margin:12px 0 6px; }
    input, select, button { width:100%; box-sizing:border-box; border:1px solid var(--line); border-radius:6px; padding:10px; font-size:15px; }
    button { background:var(--accent); color:white; border:0; font-weight:700; cursor:pointer; margin-top:14px; }
    button:disabled { opacity:.6; cursor:wait; }
    .search-wrap { position:relative; }
    .suggestions { position:absolute; z-index:5; left:0; right:0; top:calc(100% + 4px); border:1px solid var(--line); border-radius:8px; background:white; box-shadow:0 12px 28px rgba(15,23,42,.14); max-height:280px; overflow:auto; display:none; }
    .suggestion { display:flex; justify-content:space-between; gap:10px; padding:10px 12px; cursor:pointer; border-bottom:1px solid #eef2f7; }
    .suggestion:hover { background:#eef5ff; }
    .suggestion strong { font-size:15px; }
    .suggestion small { color:var(--muted); }
    .hint { font-size:12px; color:var(--muted); margin-top:6px; }
    .cards { display:grid; grid-template-columns: repeat(4, minmax(120px,1fr)); gap:10px; margin:12px 0; }
    .card { border:1px solid var(--line); border-radius:8px; padding:10px; background:#fbfcff; }
    .card b { display:block; font-size:18px; }
    .good { color:var(--good); } .warn { color:var(--warn); } .bad { color:var(--bad); }
    iframe { width:100%; height:760px; border:1px solid var(--line); border-radius:8px; background:white; }
    pre { white-space:pre-wrap; word-break:break-word; background:#0f172a; color:#e5e7eb; padding:12px; border-radius:8px; max-height:320px; overflow:auto; }
    textarea { width:100%; min-height:130px; box-sizing:border-box; border:1px solid var(--line); border-radius:6px; padding:10px; font-size:14px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
    table { width:100%; border-collapse:collapse; font-size:13px; }
    th, td { border-bottom:1px solid var(--line); padding:7px; text-align:right; }
    th:first-child, td:first-child { text-align:left; }
    @media (max-width: 980px) { main { grid-template-columns:1fr; } iframe { height:560px; } }
  </style>
</head>
<body>
  <header>
    <h1>Preview / Review Lab</h1>
    <p>과거 차트 위에 준비, 매수, 축소, 회피 신호를 표시하고 10거래일 후 확률을 점검합니다. 현재 버전은 일봉 예습/복습용입니다.</p>
  </header>
  <main>
    <section>
      <h2>검증 실행</h2>
      <label>종목 검색</label>
      <div class="search-wrap">
        <input id="stockSearch" value="제주반도체" placeholder="예: 한미, 042700, 제주" autocomplete="off" />
        <div id="suggestions" class="suggestions"></div>
      </div>
      <div class="hint">종목명 또는 종목코드를 입력하고 목록에서 선택하세요.</div>
      <label>종목코드</label>
      <input id="ticker" value="080220" placeholder="예: 080220" />
      <label>종목명</label>
      <input id="name" value="제주반도체" placeholder="예: 제주반도체" />
      <label>기간</label>
      <select id="days">
        <option value="120">최근 3~4개월</option>
        <option value="260" selected>최근 1년 내외</option>
        <option value="520">최근 2년 내외</option>
        <option value="780">최근 3년 내외</option>
      </select>
      <label><input id="force" type="checkbox" style="width:auto" /> 캐시 무시하고 재조회</label>
      <button id="run">리뷰 생성</button>
      <div class="cards">
        <div class="card"><span>BUY 확률</span><b id="buyProb">-</b></div>
        <div class="card"><span>PREPARE 확률</span><b id="prepareProb">-</b></div>
        <div class="card"><span>BUY 횟수</span><b id="buyCount">-</b></div>
        <div class="card"><span>자동주문 기준</span><b>10만원</b></div>
      </div>
      <h3>확률/성과 요약</h3>
      <div id="stats"></div>
      <h3>상태</h3>
      <pre id="status">대기 중</pre>
      <h3>관찰종목 배치 리뷰</h3>
      <div class="hint">최대 50개. 한 줄에 `종목코드,종목명` 또는 `종목코드` 형식으로 입력합니다.</div>
      <textarea id="batchItems">080220,제주반도체
399720,가온칩스
042700,한미반도체</textarea>
      <button id="addCurrent" type="button">현재 종목을 배치에 추가</button>
      <button id="runBatch" type="button">배치 리뷰 실행</button>
      <div id="batchResults"></div>
    </section>
    <section>
      <h2>차트 리뷰</h2>
      <iframe id="chart" title="preview review chart"></iframe>
    </section>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    const fmt = (value) => value === null || value === undefined ? "-" : value;
    let searchTimer = null;
    function selectStock(item) {
      $("ticker").value = item.ticker;
      $("name").value = item.name;
      $("stockSearch").value = `${item.name} (${item.ticker})`;
      $("suggestions").style.display = "none";
    }
    async function autoFillStockFrom(field) {
      const raw = field === "ticker" ? $("ticker").value : $("name").value;
      const query = raw.trim();
      if (!query) return;
      try {
        const response = await fetch(`/stocks/search?q=${encodeURIComponent(query)}&limit=8`);
        const data = await response.json();
        const results = data.results || [];
        if (!data.ok || !results.length) return;
        const exact = results.find((item) => item.ticker === query || item.name === query);
        const prefix = field === "ticker"
          ? results.find((item) => item.ticker.startsWith(query))
          : results.find((item) => item.name.startsWith(query));
        const chosen = exact || prefix || results[0];
        if (chosen) selectStock(chosen);
      } catch (_error) {
        // Keep manual input if lookup fails.
      }
    }
    async function searchStocks(query) {
      query = query.trim();
      if (query.length < 1) {
        $("suggestions").style.display = "none";
        return;
      }
      const response = await fetch(`/stocks/search?q=${encodeURIComponent(query)}&limit=12`);
      const data = await response.json();
      const results = data.results || [];
      if (!data.ok || !results.length) {
        $("suggestions").innerHTML = `<div class="suggestion"><small>검색 결과 없음</small></div>`;
        $("suggestions").style.display = "block";
        return;
      }
      $("suggestions").innerHTML = results.map((item) => `
        <div class="suggestion" data-ticker="${item.ticker}" data-name="${item.name}">
          <div><strong>${item.name}</strong><br><small>${item.market}</small></div>
          <small>${item.ticker}</small>
        </div>
      `).join("");
      $("suggestions").style.display = "block";
    }
    $("stockSearch").addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => searchStocks($("stockSearch").value), 180);
    });
    $("stockSearch").addEventListener("focus", () => {
      if ($("stockSearch").value.trim()) searchStocks($("stockSearch").value);
    });
    $("suggestions").addEventListener("click", (event) => {
      const row = event.target.closest(".suggestion");
      if (!row || !row.dataset.ticker) return;
      selectStock({ticker: row.dataset.ticker, name: row.dataset.name, market: ""});
    });
    $("ticker").addEventListener("change", () => autoFillStockFrom("ticker"));
    $("ticker").addEventListener("blur", () => autoFillStockFrom("ticker"));
    $("name").addEventListener("change", () => autoFillStockFrom("name"));
    $("name").addEventListener("blur", () => autoFillStockFrom("name"));
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".search-wrap")) $("suggestions").style.display = "none";
    });
    function renderStats(stats) {
      const keys = Object.keys(stats || {});
      if (!keys.length) return "<p>신호 통계가 아직 없습니다.</p>";
      return `<table><thead><tr><th>신호</th><th>횟수</th><th>양수확률</th><th>평균수익</th><th>평균최대상승</th><th>평균최대하락</th></tr></thead><tbody>${keys.map(k => {
        const s = stats[k];
        return `<tr><td>${k}</td><td>${fmt(s.count)}</td><td>${fmt(s.positive_end_probability_pct)}%</td><td>${fmt(s.avg_end_return_pct)}%</td><td>${fmt(s.avg_max_gain_pct)}%</td><td>${fmt(s.avg_max_loss_pct)}%</td></tr>`;
      }).join("")}</tbody></table>`;
    }
    function parseBatchItems() {
      return $("batchItems").value
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean)
        .slice(0, 50)
        .map((line) => {
          const parts = line.split(/[,\t ]+/).filter(Boolean);
          return {ticker: parts[0] || "", name: parts.slice(1).join(" ") || ""};
        })
        .filter((item) => item.ticker);
    }
    function renderBatchResults(results, errors) {
      if ((!results || !results.length) && (!errors || !errors.length)) {
        $("batchResults").innerHTML = "<p>배치 결과가 없습니다.</p>";
        return;
      }
      const rows = (results || []).map((review) => {
        const stats = review.probability_10d || {};
        const buy = stats.BUY || {};
        const prepare = stats.PREPARE || {};
        return `<tr>
          <td>${review.name}<br><small>${review.ticker}</small></td>
          <td>${fmt(buy.positive_end_probability_pct)}%</td>
          <td>${fmt(prepare.positive_end_probability_pct)}%</td>
          <td>${fmt(buy.count)}</td>
          <td>${fmt(review.summary && review.summary.REDUCE)}</td>
          <td><a href="${review.chart_url}" target="_blank">차트</a></td>
        </tr>`;
      }).join("");
      const errorRows = (errors || []).map((error) => `<tr><td>${error.name || error.ticker}<br><small>${error.ticker}</small></td><td colspan="5">${error.error}</td></tr>`).join("");
      $("batchResults").innerHTML = `<table><thead><tr><th>종목</th><th>BUY 확률</th><th>PREPARE 확률</th><th>BUY 횟수</th><th>REDUCE</th><th>차트</th></tr></thead><tbody>${rows}${errorRows}</tbody></table>`;
    }
    $("addCurrent").addEventListener("click", () => {
      const ticker = $("ticker").value.trim();
      const name = $("name").value.trim();
      if (!ticker) return;
      const line = `${ticker},${name}`;
      const current = $("batchItems").value.split(/\r?\n/).map((item) => item.trim());
      if (!current.some((item) => item.startsWith(ticker))) {
        $("batchItems").value = `${$("batchItems").value.trim()}\n${line}`.trim();
      }
    });
    $("runBatch").addEventListener("click", async () => {
      const items = parseBatchItems();
      if (!items.length) {
        $("batchResults").innerHTML = "<p>배치 입력 종목이 없습니다.</p>";
        return;
      }
      $("runBatch").disabled = true;
      $("batchResults").innerHTML = "<p>배치 리뷰 실행 중입니다. 종목 수에 따라 시간이 걸릴 수 있습니다.</p>";
      try {
        const response = await fetch("/preview-review-batch", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            items,
            days: Number($("days").value),
            force: $("force").checked
          })
        });
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || "unknown error");
        renderBatchResults(data.results || [], data.errors || []);
      } catch (error) {
        $("batchResults").innerHTML = `<p>오류: ${error.message}</p>`;
      } finally {
        $("runBatch").disabled = false;
      }
    });
    $("run").addEventListener("click", async () => {
      $("run").disabled = true;
      $("status").textContent = "실행 중입니다. 데이터 재조회는 시간이 걸릴 수 있습니다.";
      try {
        const response = await fetch("/preview-review", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            ticker: $("ticker").value.trim(),
            name: $("name").value.trim(),
            days: Number($("days").value),
            force: $("force").checked
          })
        });
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || "unknown error");
        const review = data.review;
        const probs = review.probability_10d || {};
        $("buyProb").textContent = fmt(probs.BUY && probs.BUY.positive_end_probability_pct) + "%";
        $("prepareProb").textContent = fmt(probs.PREPARE && probs.PREPARE.positive_end_probability_pct) + "%";
        $("buyCount").textContent = fmt(probs.BUY && probs.BUY.count);
        $("stats").innerHTML = renderStats(probs);
        $("chart").src = review.chart_url + "?t=" + Date.now();
        $("status").textContent = JSON.stringify({
          ticker: review.ticker,
          name: review.name,
          provider: review.provider,
          rows: review.rows,
          summary: review.summary,
          decision_summary: review.decision_summary,
          chart_url: review.chart_url
        }, null, 2);
      } catch (error) {
        $("status").textContent = "오류: " + error.message;
      } finally {
        $("run").disabled = false;
      }
    });
  </script>
</body>
</html>
"""


@app.post("/verify-prices")
async def verify_prices(request: Request) -> dict[str, Any]:
    body = await read_json_body(request)
    claims = claims_from_payload(body)
    if not claims:
        return api_error(ValueError("No price claims found"), {
            "received_keys": list(body.keys()),
            "hint": "Send {claims:[{ticker, claimed_price, buy_low, buy_high, target_price, stop_loss}]} or a single {ticker, price}.",
        })
    payload = market_data.verify_price_claims(
        claims,
        days=int_from_payload(body, "days", 260),
        force=bool_from_payload(body, "force", False),
    )
    return api_success({
        **payload,
        "data_policy": "Use this endpoint before publishing AI-generated price tables. CLAIM_MISMATCH rows must be corrected or blocked.",
        "freshness_policy": f"data_age_days must be <= {market_data.MAX_DATA_AGE_DAYS}.",
        "source_validation_policy": f"source close diff must be <= {market_data.MAX_CLOSE_DIFF_PCT}% and source date diff <= {market_data.MAX_SOURCE_DATE_DIFF_DAYS} day.",
        "claim_price_policy": f"claimed price diff must be <= {market_data.MAX_CLAIM_PRICE_DIFF_PCT}%.",
        "strategy_price_policy": f"buy range must be within {market_data.MAX_STRATEGY_PRICE_GAP_PCT}% of verified close when used as current entry; target must be above close and stop loss below close.",
    })


@app.post("/validate-report")
async def validate_report(request: Request) -> dict[str, Any]:
    body = await read_json_body(request)
    report_text = report_text_from_payload(body)
    if not report_text.strip():
        return api_error(ValueError("No report text found"), {
            "received_keys": list(body.keys()),
            "hint": "Send {report_text:'...'} or n8n output as {output:'...'}, {text:'...'}, {message:'...'}, or {result:'...'}.",
        })
    payload = market_data.validate_report_text(
        report_text,
        days=int_from_payload(body, "days", 260),
        force=bool_from_payload(body, "force", False),
    )
    return api_success({
        **payload,
        "data_policy": "Use this endpoint as the final gate before Telegram publishing. publishable=false means the report must be rewritten from verified API data.",
        "price_policy": f"claimed price diff must be <= {market_data.MAX_CLAIM_PRICE_DIFF_PCT}%; strategy range gap must be <= {market_data.MAX_STRATEGY_PRICE_GAP_PCT}%.",
        "evidence_policy": "News/disclosure/sentiment claims should include source URLs or be marked unverified.",
    })


@app.get("/results/latest")
def latest_results() -> dict[str, Any]:
    path = market_data.OUTPUT_DIR / "precision_results.json"
    if not path.exists():
        return api_error(FileNotFoundError(path), {"path": str(path)})
    return api_success({
        "path": str(path),
        "results": json.loads(path.read_text(encoding="utf-8")),
    })


def main() -> None:
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8010"))
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
