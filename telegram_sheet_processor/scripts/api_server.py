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
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, BaseModel, Field

try:
    from . import market_data
except ImportError:
    import market_data

APP_VERSION = "0.1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
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
