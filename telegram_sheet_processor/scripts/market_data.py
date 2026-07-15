#!/usr/bin/env python3
"""Reliable Korean stock data fetch, validation, indicators, and charting."""
import argparse
import json
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
CHART_DIR = OUTPUT_DIR / "charts"
REPORT_DIR = OUTPUT_DIR / "reports"
MAX_DATA_AGE_DAYS = 2
MAX_SOURCE_DATE_DIFF_DAYS = 1
MAX_CLOSE_DIFF_PCT = 0.5
MAX_CLAIM_PRICE_DIFF_PCT = 0.5
MAX_STRATEGY_PRICE_GAP_PCT = 3.0

PRICE_RE = r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)\s*" + chr(0xC6D0)
REALTIME_ENV_KEYS = ["KIS_APP_KEY", "KIS_APP_SECRET", "KIS_ACCOUNT_NO"]
ALLOW_STALE_CACHE = os.getenv("ALLOW_STALE_CACHE", "false").lower() in ["1", "true", "yes", "y"]
_KIWOOM_REST_TOKEN_CACHE = {"token": None, "expires_at": 0.0, "expires_dt": None}


def _parse_json_env(key, default="{}"):
    raw = os.getenv(key, default)
    if raw is None:
        return {}
    raw = str(raw).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _extract_numeric_price(payload):
    if isinstance(payload, (int, float)) and not isinstance(payload, bool):
        return float(payload)
    if isinstance(payload, dict):
        for key in [
            "price",
            "current_price",
            "currentPrice",
            "last_price",
            "lastPrice",
            "close",
            "trade_price",
            "tradePrice",
            "cur_prc",
            "stck_prpr",
        ]:
            if key in payload:
                value = payload.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    return float(value)
                if isinstance(value, str):
                    cleaned = value.replace(",", "").replace("+", "").strip()
                    try:
                        return abs(float(cleaned))
                    except Exception:
                        pass
        for key in ["output", "data", "result", "body", "response"]:
            if key in payload:
                nested = _extract_numeric_price(payload.get(key))
                if nested is not None:
                    return nested
        for value in payload.values():
            nested = _extract_numeric_price(value)
            if nested is not None:
                return nested
    if isinstance(payload, list):
        for item in payload:
            nested = _extract_numeric_price(item)
            if nested is not None:
                return nested
    if isinstance(payload, str):
        cleaned = payload.replace(",", "").replace("+", "").strip()
        try:
            return abs(float(cleaned))
        except Exception:
            return None
    return None

def today_kst():
    return datetime.now(timezone(timedelta(hours=9))).date()


DEFAULT_WATCHLIST = [
    {"ticker": "247540", "name": "에코프로비엠", "target_price": 220000, "stop_loss": 165000},
    {"ticker": "196170", "name": "알테오젠", "target_price": 380000, "stop_loss": 290000},
    {"ticker": "403870", "name": "HPSP", "target_price": 55000, "stop_loss": 42000},
    {"ticker": "214150", "name": "클래시스", "target_price": 65000, "stop_loss": 48000},
    {"ticker": "277810", "name": "레인보우로보틱스", "target_price": 180000, "stop_loss": 135000},
]


@dataclass
class FetchResult:
    ticker: str
    name: str
    provider: str
    rows: int
    cache_path: Path
    warnings: list
    frame: pd.DataFrame


def ensure_dirs():
    for path in [DATA_DIR, CACHE_DIR, OUTPUT_DIR, CHART_DIR, REPORT_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def normalize_ohlcv(frame):
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    frame = frame.copy()
    if "Date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["Date"]).dt.date
    elif frame.index.name is not None or not isinstance(frame.index, pd.RangeIndex):
        frame["date"] = pd.to_datetime(frame.index).date
    rename = {
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
        "Change": "change",
    }
    frame = frame.rename(columns=rename)
    required = ["date", "open", "high", "low", "close", "volume"]
    for col in required:
        if col not in frame.columns:
            frame[col] = None
    out = frame[required].copy()
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["date", "close"]).drop_duplicates(subset=["date"]).sort_values("date")
    return out.reset_index(drop=True)


def fetch_with_finance_datareader(ticker, start, end):
    import FinanceDataReader as fdr

    frame = fdr.DataReader(ticker, start, end)
    return normalize_ohlcv(frame)


def fetch_with_pykrx(ticker, start, end):
    from pykrx import stock

    frame = stock.get_market_ohlcv_by_date(
        start.replace("-", ""),
        end.replace("-", ""),
        ticker,
    )
    if frame is None or frame.empty:
        return normalize_ohlcv(frame)
    frame = frame.rename(columns={
        "시가": "Open",
        "고가": "High",
        "저가": "Low",
        "종가": "Close",
        "거래량": "Volume",
    })
    return normalize_ohlcv(frame)


def fetch_naver_public_quote(ticker):
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        response.raise_for_status()
        match = re.search(
            r'<p class="no_today">.*?<span class="blind">([0-9,]+)</span>',
            response.text,
            flags=re.DOTALL,
        )
        if not match:
            return {
                "provider": "naver_finance_public",
                "ok": False,
                "ticker": ticker,
                "price": None,
                "url": url,
                "error": "Could not parse current quote from Naver Finance.",
                "realtime": False,
            }
        return {
            "provider": "naver_finance_public",
            "ok": True,
            "ticker": ticker,
            "price": parse_won(match.group(1)),
            "url": url,
            "error": None,
            "realtime": False,
            "note": "Public web quote; use as current public quote, not broker-grade realtime.",
        }
    except Exception as exc:
        return {
            "provider": "naver_finance_public",
            "ok": False,
            "ticker": ticker,
            "price": None,
            "url": url,
            "error": str(exc),
            "realtime": False,
        }


def lookup_pykrx_name(ticker):
    try:
        from pykrx import stock

        return stock.get_market_ticker_name(ticker)
    except Exception:
        return None


def cache_path_for(ticker):
    return CACHE_DIR / f"{ticker}_ohlcv.csv"


def load_cache(ticker):
    path = cache_path_for(ticker)
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def cache_meta(ticker):
    path = cache_path_for(ticker)
    if not path.exists():
        return {
            "ticker": ticker,
            "exists": False,
            "path": str(path),
            "rows": 0,
            "latest_date": None,
            "age_days": None,
            "stale": None,
        }
    frame = normalize_ohlcv(load_cache(ticker))
    if frame.empty:
        return {
            "ticker": ticker,
            "exists": True,
            "path": str(path),
            "rows": 0,
            "latest_date": None,
            "age_days": None,
            "stale": True,
        }
    latest = pd.to_datetime(frame["date"]).max().date()
    age = (today_kst() - latest).days
    return {
        "ticker": ticker,
        "exists": True,
        "path": str(path),
        "rows": int(len(frame)),
        "latest_date": latest.isoformat(),
        "age_days": age,
        "stale": age > MAX_DATA_AGE_DAYS,
        "allow_stale_cache": ALLOW_STALE_CACHE,
    }


def save_cache(ticker, frame):
    path = cache_path_for(ticker)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def latest_data_meta(frame):
    if frame is None or frame.empty:
        return {
            "analysis_date": today_kst().isoformat(),
            "data_as_of": None,
            "data_age_days": None,
            "freshness_status": "empty",
            "tradable": False,
            "no_recommendation_reason": "No OHLCV data was collected.",
        }
    latest = pd.to_datetime(frame["date"]).max().date()
    age = (today_kst() - latest).days
    is_fresh = age <= MAX_DATA_AGE_DAYS
    return {
        "analysis_date": today_kst().isoformat(),
        "data_as_of": latest.isoformat(),
        "data_age_days": age,
        "freshness_status": "fresh" if is_fresh else "stale",
        "tradable": is_fresh,
        "no_recommendation_reason": None if is_fresh else (
            f"Latest candle is {age} days old ({latest}); "
            f"recommendation blocked by {MAX_DATA_AGE_DAYS}-day freshness policy."
        ),
    }


def provider_snapshot(provider, frame):
    if frame is None or frame.empty:
        return {
            "provider": provider,
            "ok": False,
            "data_as_of": None,
            "close": None,
            "rows": 0,
            "error": "No rows",
        }
    latest = frame.iloc[-1]
    return {
        "provider": provider,
        "ok": True,
        "data_as_of": str(latest["date"]),
        "close": round(float(latest["close"]), 4),
        "rows": int(len(frame)),
        "error": None,
    }


def compare_source_frames(primary, secondary, primary_name="FinanceDataReader", secondary_name="pykrx"):
    validation = {
        "status": "unchecked",
        "tradable": True,
        "checks": [],
        "sources": [
            provider_snapshot(primary_name, primary),
            provider_snapshot(secondary_name, secondary),
        ],
        "max_source_date_diff_days": MAX_SOURCE_DATE_DIFF_DAYS,
        "max_close_diff_pct": MAX_CLOSE_DIFF_PCT,
    }
    if primary is None or primary.empty:
        validation["status"] = "primary_empty"
        validation["tradable"] = False
        validation["checks"].append("Primary source returned no OHLCV rows.")
        return validation
    if secondary is None or secondary.empty:
        validation["status"] = "secondary_unavailable"
        validation["checks"].append("Secondary source unavailable; freshness check still applies.")
        return validation

    p_latest = primary.iloc[-1]
    s_latest = secondary.iloc[-1]
    p_date = pd.to_datetime(p_latest["date"]).date()
    s_date = pd.to_datetime(s_latest["date"]).date()
    date_diff = abs((p_date - s_date).days)
    p_close = float(p_latest["close"])
    s_close = float(s_latest["close"])
    close_diff_pct = abs(p_close - s_close) / p_close * 100 if p_close else 100
    validation["date_diff_days"] = date_diff
    validation["close_diff_pct"] = round(close_diff_pct, 4)

    if date_diff > MAX_SOURCE_DATE_DIFF_DAYS:
        validation["checks"].append(f"Source date mismatch: {p_date} vs {s_date}.")
    if close_diff_pct > MAX_CLOSE_DIFF_PCT:
        validation["checks"].append(f"Close mismatch: {p_close:.4f} vs {s_close:.4f} ({close_diff_pct:.2f}%).")

    validation["status"] = "matched" if not validation["checks"] else "mismatch"
    validation["tradable"] = validation["status"] == "matched"
    return validation


def cross_validate_ohlcv(ticker, primary_frame, days=260):
    end = today_kst()
    start = end - timedelta(days=days + 20)
    try:
        secondary = fetch_with_pykrx(ticker, start.isoformat(), end.isoformat()).tail(days)
        validation = compare_source_frames(primary_frame, secondary)
        validation["ticker_name_pykrx"] = lookup_pykrx_name(ticker)
        return validation
    except ImportError as exc:
        return {
            "status": "secondary_not_installed",
            "tradable": True,
            "checks": [f"pykrx is not installed: {exc}"],
            "sources": [provider_snapshot("FinanceDataReader", primary_frame)],
            "max_source_date_diff_days": MAX_SOURCE_DATE_DIFF_DAYS,
            "max_close_diff_pct": MAX_CLOSE_DIFF_PCT,
        }
    except Exception as exc:
        return {
            "status": "secondary_error",
            "tradable": True,
            "checks": [f"pykrx validation failed: {exc}"],
            "sources": [provider_snapshot("FinanceDataReader", primary_frame)],
            "max_source_date_diff_days": MAX_SOURCE_DATE_DIFF_DAYS,
            "max_close_diff_pct": MAX_CLOSE_DIFF_PCT,
        }


def apply_validation_to_score(score, validation):
    if score.get("tradable") and not validation.get("tradable", True):
        score = score.copy()
        score["decision"] = "DATA_MISMATCH"
        score["tradable"] = False
        reason = "; ".join(validation.get("checks", []))
        score["no_recommendation_reason"] = reason
        score["reasons"] = list(score.get("reasons", [])) + [reason]
    return score


def parse_won(value):
    if value is None:
        return None
    return float(str(value).replace(",", ""))


def normalize_report_text(text):
    text = text or ""
    text = re.sub(r"[*_`>#|]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def realtime_source_status():
    installed = True
    install_error = None
    try:
        import pykis  # noqa: F401
    except Exception as exc:
        installed = False
        install_error = str(exc)
    missing_env = [key for key in REALTIME_ENV_KEYS if not os.getenv(key)]
    configured = installed and not missing_env
    return {
        "provider": "KIS Open API",
        "library": "python-kis",
        "installed": installed,
        "install_error": install_error,
        "configured": configured,
        "missing_env": missing_env,
        "allows_current_price_wording": configured,
    }


def kiwoom_source_status():
    enabled = os.getenv("KIWOOM_ENABLED", "false").lower() in ["1", "true", "yes", "y"]
    bridge_url = os.getenv("KIWOOM_BRIDGE_URL", "").strip()
    account_no = os.getenv("KIWOOM_ACCOUNT_NO", "").strip()
    configured = enabled and bool(bridge_url)
    return {
        "provider": "Kiwoom OpenAPI+",
        "enabled": enabled,
        "configured": configured,
        "bridge_url_configured": bool(bridge_url),
        "account_no_configured": bool(account_no),
        "docker_note": "Kiwoom OpenAPI+ is Windows COM/GUI based. Use KIWOOM_BRIDGE_URL from a Windows bridge; do not run Kiwoom directly inside Linux Docker.",
        "allows_current_price_wording": configured,
    }



def kiwoom_rest_source_status():
    enabled = os.getenv("KIWOOM_ENABLED", "false").lower() in ["1", "true", "yes", "y"]
    rest_enabled = os.getenv("KIWOOM_REST_ENABLED", "false").lower() in ["1", "true", "yes", "y"]
    quote_url = os.getenv("KIWOOM_REST_QUOTE_URL", "").strip()
    method = os.getenv("KIWOOM_REST_METHOD", "GET").strip().upper() or "GET"
    base_url = os.getenv("KIWOOM_REST_BASE_URL", "https://mockapi.kiwoom.com").rstrip("/")
    app_key = os.getenv("KIWOOM_REST_APP_KEY", "").strip()
    app_secret = os.getenv("KIWOOM_REST_APP_SECRET", "").strip()
    try:
        timeout_seconds = int(os.getenv("KIWOOM_REST_TIMEOUT_SECONDS", "10"))
    except Exception:
        timeout_seconds = 10
    headers = _parse_json_env("KIWOOM_REST_HEADERS_JSON", "{}")
    direct_configured = bool(app_key and app_secret)
    configured = (enabled or rest_enabled) and (bool(quote_url) or direct_configured)
    return {
        "provider": "Kiwoom REST",
        "enabled": enabled or rest_enabled,
        "configured": configured,
        "quote_url_configured": bool(quote_url),
        "quote_url_template": quote_url,
        "direct_api_configured": direct_configured,
        "base_url": base_url,
        "app_key_configured": bool(app_key),
        "app_secret_configured": bool(app_secret),
        "method": method,
        "timeout_seconds": timeout_seconds,
        "headers_configured": bool(headers),
        "allows_current_price_wording": configured,
        "note": "Set KIWOOM_REST_APP_KEY and KIWOOM_REST_APP_SECRET for direct Kiwoom REST calls, or KIWOOM_REST_QUOTE_URL for an external bridge.",
    }


def _kiwoom_rest_token_cache_is_valid():
    token = _KIWOOM_REST_TOKEN_CACHE.get("token")
    expires_at = float(_KIWOOM_REST_TOKEN_CACHE.get("expires_at") or 0)
    return bool(token) and time.time() < expires_at - 60


def _get_kiwoom_rest_access_token(status):
    if _kiwoom_rest_token_cache_is_valid():
        return str(_KIWOOM_REST_TOKEN_CACHE["token"])

    app_key = os.getenv("KIWOOM_REST_APP_KEY", "").strip()
    app_secret = os.getenv("KIWOOM_REST_APP_SECRET", "").strip()
    if not app_key or not app_secret:
        raise ValueError("KIWOOM_REST_APP_KEY and KIWOOM_REST_APP_SECRET are required for direct Kiwoom REST.")

    response = requests.post(
        f"{status['base_url']}/oauth2/token",
        headers={"Content-Type": "application/json;charset=UTF-8"},
        json={
            "grant_type": "client_credentials",
            "appkey": app_key,
            "secretkey": app_secret,
        },
        timeout=status["timeout_seconds"],
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("token")
    if not token:
        raise ValueError(f"Kiwoom token response did not contain token: {payload.get('return_msg') or payload}")

    _KIWOOM_REST_TOKEN_CACHE.update({
        "token": token,
        "expires_at": time.time() + 55 * 60,
        "expires_dt": payload.get("expires_dt"),
    })
    return str(token)


def _fetch_kiwoom_rest_direct_quote(ticker, status):
    token = _get_kiwoom_rest_access_token(status)
    response = requests.post(
        f"{status['base_url']}/api/dostk/stkinfo",
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {token}",
            "api-id": "ka10001",
        },
        json={"stk_cd": ticker},
        timeout=status["timeout_seconds"],
    )
    response.raise_for_status()
    payload = response.json()
    price = _extract_numeric_price(payload)
    if price is None:
        raise ValueError(f"No numeric price found in Kiwoom REST response: {payload}")
    return {
        "ok": True,
        "source": "kiwoom_rest_ka10001",
        "ticker": ticker,
        "name": payload.get("stk_nm"),
        "price": float(price),
        "url": f"{status['base_url']}/api/dostk/stkinfo",
        "api_id": "ka10001",
        "raw": payload,
        "error": None,
    }


def fetch_kiwoom_rest_quote(ticker):
    status = kiwoom_rest_source_status()
    if not status.get("configured"):
        return {
            "ok": False,
            "source": "kiwoom_rest",
            "ticker": ticker,
            "price": None,
            "url": None,
            "error": "Kiwoom REST is not configured.",
        }
    if status.get("direct_api_configured") and not status.get("quote_url_configured"):
        try:
            return _fetch_kiwoom_rest_direct_quote(ticker, status)
        except Exception as exc:
            return {
                "ok": False,
                "source": "kiwoom_rest_ka10001",
                "ticker": ticker,
                "price": None,
                "url": f"{status['base_url']}/api/dostk/stkinfo",
                "error": str(exc),
            }

    url = status["quote_url_template"].format(ticker=ticker)
    headers = _parse_json_env("KIWOOM_REST_HEADERS_JSON", "{}")
    body = _parse_json_env("KIWOOM_REST_BODY_JSON", "{}")
    try:
        response = requests.request(
            method=status["method"],
            url=url,
            headers=headers,
            json=body or None,
            timeout=status["timeout_seconds"],
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return {
            "ok": False,
            "source": "kiwoom_rest",
            "ticker": ticker,
            "price": None,
            "url": url,
            "error": str(exc),
        }

    price = _extract_numeric_price(payload)
    if price is None:
        return {
            "ok": False,
            "source": "kiwoom_rest",
            "ticker": ticker,
            "price": None,
            "url": url,
            "error": "No numeric price found in Kiwoom REST response.",
        }

    return {
        "ok": True,
        "source": "kiwoom_rest",
        "ticker": ticker,
        "price": float(price),
        "url": url,
        "error": None,
    }


def quote_source_status():
    realtime = realtime_source_status()
    kiwoom = kiwoom_source_status()
    kiwoom_rest = kiwoom_rest_source_status()
    return {
        "primary_realtime": realtime,
        "kiwoom_realtime": kiwoom,
        "kiwoom_rest_realtime": kiwoom_rest,
        "public_quote": {
            "provider": "Naver Finance public quote",
            "configured": True,
            "realtime": False,
            "role": "No-key public current quote fallback. Do not label as broker-grade realtime.",
        },
        "daily_primary": "pykrx",
        "daily_fallback": "FinanceDataReader",
    }


def report_claims_realtime_wording(report_text):
    text = normalize_report_text(report_text)
    patterns = [
        "\ud604\uc7ac\uac00",
        "\ud604\uc7ac \uc2dc\uc138",
        "\uc2e4\uc2dc\uac04",
        "real-time",
        "realtime",
        "current price",
    ]
    return [pattern for pattern in patterns if pattern.lower() in text.lower()]


def report_claims_strict_realtime_wording(report_text):
    text = normalize_report_text(report_text)
    patterns = ["\uc2e4\uc2dc\uac04", "real-time", "realtime"]
    return [pattern for pattern in patterns if pattern.lower() in text.lower()]

def parse_report_date(year, month, day):
    try:
        return date(int(year), int(month), int(day))
    except Exception:
        return None


def extract_report_analysis_dates(report_text):
    text = normalize_report_text(report_text)
    label = r"(?:분석\s*기준일|기준일|분석일|analysis\s*date|as\s*of)"
    patterns = [
        label + r"\s*[:：]?\s*([0-9]{4})\s*년\s*([0-9]{1,2})\s*월\s*([0-9]{1,2})\s*일",
        label + r"\s*[:：]?\s*([0-9]{4})[-./]([0-9]{1,2})[-./]([0-9]{1,2})",
    ]
    found = []
    seen = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            parsed = parse_report_date(*match.groups())
            if parsed and parsed.isoformat() not in seen:
                found.append(parsed)
                seen.add(parsed.isoformat())
    return found


def first_price_after(pattern, text):
    match = re.search(pattern + r".{0,80}?" + PRICE_RE, text, flags=re.IGNORECASE | re.DOTALL)
    return parse_won(match.groups()[-1]) if match else None


def extract_claim_fields(text):
    claimed_price = first_price_after(
        r"(?:현재\s*(?:시세|가|주가)|현재가|current\s*(?:price|quote)|market\s*price|last\s*price)",
        text,
    )
    buy_match = re.search(
        r"(?:매수.{0,12}?구간|buy.{0,12}?(?:range|zone|area|low)).{0,80}?"
        + PRICE_RE
        + r"\s*(?:~|-|부터|에서|to)\s*"
        + PRICE_RE,
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    buy_low = parse_won(buy_match.group(1)) if buy_match else None
    buy_high = parse_won(buy_match.group(2)) if buy_match else None
    target_price = first_price_after(r"(?:목표가|target\s*price|price\s*target|target)", text)
    stop_loss = first_price_after(r"(?:손절가|stop\s*loss|stoploss|cut\s*loss|risk\s*line)", text)
    return {
        "claimed_price": claimed_price,
        "buy_low": buy_low,
        "buy_high": buy_high,
        "target_price": target_price,
        "stop_loss": stop_loss,
    }


def first_price_in_same_line(text, start_pos=0):
    line_start = text.rfind("\n", 0, start_pos) + 1
    line_end = text.find("\n", start_pos)
    if line_end == -1:
        line_end = len(text)
    line = text[line_start:line_end]
    local_start = max(0, start_pos - line_start)
    match = re.search(PRICE_RE, line[local_start:])
    return parse_won(match.group(1)) if match else None


def extract_report_claims(report_text):
    text = normalize_report_text(report_text)
    ticker_matches = []
    seen = set()
    for match in re.finditer(r"\b[0-9]{6}\b", text):
        ticker = match.group(0)
        if ticker in seen:
            continue
        seen.add(ticker)
        ticker_matches.append((ticker, match.start()))
    if not ticker_matches:
        return []

    claims = []
    for idx, (ticker, start) in enumerate(ticker_matches):
        end = ticker_matches[idx + 1][1] if idx + 1 < len(ticker_matches) else len(text)
        segment = text[start:end]
        fields = extract_claim_fields(segment)
        if fields.get("claimed_price") is None:
            row_price = first_price_in_same_line(text, start)
            if row_price is not None:
                fields["claimed_price"] = row_price
        if all(value is None for value in fields.values()):
            fields = extract_claim_fields(text)
        name = lookup_pykrx_name(ticker) or ticker
        claims.append({
            "ticker": ticker,
            "name": name,
            **fields,
        })
    return claims


def find_report_evidence_warnings(report_text):
    text = normalize_report_text(report_text)
    evidence_words = ["뉴스", "공시", "수주", "센티먼트", "Catalyst", "촉매제", "사상 최대", "컨센서스"]
    has_market_claim = any(word in text for word in evidence_words)
    has_source_link = bool(re.search(r"https?://", text))
    warnings = []
    if has_market_claim and not has_source_link:
        warnings.append(
            "News/disclosure/sentiment claims exist without source URLs; treat context score as unverified."
        )
    return warnings


def report_claims_realtime_wording(report_text):
    text = normalize_report_text(report_text)
    patterns = [
        "\ud604\uc7ac\uac00",
        "\ud604\uc7ac \uc2dc\uc138",
        "\ud604\uc7ac \uc8fc\uac00",
        "\uc2e4\uc2dc\uac04",
        "real-time",
        "realtime",
        "current price",
    ]
    return [pattern for pattern in patterns if pattern.lower() in text.lower()]


def report_claims_strict_realtime_wording(report_text):
    text = normalize_report_text(report_text)
    patterns = ["\uc2e4\uc2dc\uac04", "real-time", "realtime"]
    return [pattern for pattern in patterns if pattern.lower() in text.lower()]

def extract_report_analysis_dates(report_text):
    text = normalize_report_text(report_text)
    label = (
        "(?:"
        "\ubd84\uc11d\\s*\uae30\uc900\uc77c|"
        "\ubd84\uc11d\uc77c|"
        "analysis\\s*date"
        ")"
    )
    patterns = [
        label + "\\s*[:\uff1a-]?\\s*([0-9]{4})\\s*\ub144\\s*([0-9]{1,2})\\s*\uc6d4\\s*([0-9]{1,2})\\s*\uc77c",
        label + r"\s*[:\uff1a-]?\s*([0-9]{4})[-./]([0-9]{1,2})[-./]([0-9]{1,2})",
    ]
    found = []
    seen = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            parsed = parse_report_date(*match.groups())
            if parsed and parsed.isoformat() not in seen:
                found.append(parsed)
                seen.add(parsed.isoformat())
    return found

def extract_claim_fields(text):
    claimed_price = first_price_after(
        (
            "(?:"
            "\ud604\uc7ac\\s*(?:\uc2dc\uc138|\uac00|\uc8fc\uac00)|"
            "\ud604\uc7ac\uac00|"
            "current\\s*(?:price|quote)|market\\s*price|last\\s*price"
            ")"
        ),
        text,
    )
    buy_match = re.search(
        "(?:\ub9e4\uc218.{0,12}?\uad6c\uac04|buy.{0,12}?(?:range|zone|area|low)).{0,80}?"
        + PRICE_RE
        + "\\s*(?:~|-|\ubd80\ud130|\uc5d0\uc11c|to)\\s*"
        + PRICE_RE,
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    buy_low = parse_won(buy_match.group(1)) if buy_match else None
    buy_high = parse_won(buy_match.group(2)) if buy_match else None
    target_price = first_price_after("(?:\ubaa9\ud45c\uac00|target\\s*price|price\\s*target|target)", text)
    stop_loss = first_price_after("(?:\uc190\uc808\uac00|stop\\s*loss|stoploss|cut\\s*loss|risk\\s*line)", text)
    return {
        "claimed_price": claimed_price,
        "buy_low": buy_low,
        "buy_high": buy_high,
        "target_price": target_price,
        "stop_loss": stop_loss,
    }

def find_report_evidence_warnings(report_text):
    text = normalize_report_text(report_text)
    evidence_words = [
        "\ub274\uc2a4",
        "\uacf5\uc2dc",
        "\uc218\uc8fc",
        "\uc13c\ud2f0\uba3c\ud2b8",
        "Catalyst",
        "\ucd09\ub9e4\uc81c",
        "\uc0ac\uc0c1 \ucd5c\ub300",
        "\ucee8\uc13c\uc11c\uc2a4",
    ]
    has_market_claim = any(word in text for word in evidence_words)
    has_source_link = bool(re.search(r"https?://", text))
    warnings = []
    if has_market_claim and not has_source_link:
        warnings.append(
            "News/disclosure/sentiment claims exist without source URLs; treat context score as unverified."
        )
    return warnings


def validate_report_text(report_text, days=260, force=False):
    claims = extract_report_claims(report_text)
    report_analysis_dates = extract_report_analysis_dates(report_text)
    evidence_warnings = find_report_evidence_warnings(report_text)
    realtime_status = realtime_source_status()
    kiwoom_status = kiwoom_source_status()
    kiwoom_rest_status = kiwoom_rest_source_status()
    realtime_wording = report_claims_realtime_wording(report_text)
    strict_realtime_wording = report_claims_strict_realtime_wording(report_text)
    today = today_kst()
    if not claims:
        return {
            "publishable": False,
            "report_guard_status": "no_ticker_found",
            "claims": [],
            "report_analysis_dates": [item.isoformat() for item in report_analysis_dates],
            "expected_analysis_date": today.isoformat(),
            "price_verification": {
                "count": 0,
                "error_count": 0,
                "results": [],
                "errors": [],
            },
            "evidence_warnings": evidence_warnings,
            "realtime_source": realtime_status,
            "kiwoom_source": kiwoom_status,
            "kiwoom_rest_source": kiwoom_rest_status,
            "blocking_reasons": ["No 6-digit Korean stock ticker was found in report text."],
        }

    price_verification = verify_price_claims(claims, days=days, force=force)
    blocking_reasons = []
    stale_report_dates = [item for item in report_analysis_dates if item != today]
    for item in stale_report_dates:
        blocking_reasons.append(
            f"Report analysis date {item.isoformat()} does not match today's KST date {today.isoformat()}."
        )
    allows_realtime_wording = (
        realtime_status["allows_current_price_wording"]
        or kiwoom_status["allows_current_price_wording"]
        or kiwoom_rest_status["allows_current_price_wording"]
    )
    if strict_realtime_wording and not allows_realtime_wording:
        blocking_reasons.append(
            "Report uses realtime wording without a configured KIS or Kiwoom realtime provider. "
            "Use 'public current quote' or 'recent trading-day close(data_as_of)' instead."
        )
    for row in price_verification["results"]:
        if not row.get("tradable"):
            blocking_reasons.append(
                f"{row['ticker']} {row.get('name')}: {row.get('claim_status')} - {'; '.join(row.get('checks', []))}"
            )
    for error in price_verification["errors"]:
        blocking_reasons.append(f"{error.get('ticker')}: {error.get('error')}")
    blocking_reasons.extend(evidence_warnings)

    return {
        "publishable": not blocking_reasons,
        "report_guard_status": "passed" if not blocking_reasons else "blocked",
        "claims": claims,
        "report_analysis_dates": [item.isoformat() for item in report_analysis_dates],
        "expected_analysis_date": today.isoformat(),
        "price_verification": price_verification,
        "evidence_warnings": evidence_warnings,
        "realtime_source": realtime_status,
        "kiwoom_source": kiwoom_status,
        "kiwoom_rest_source": kiwoom_rest_status,
        "realtime_wording": realtime_wording,
        "strict_realtime_wording": strict_realtime_wording,
        "blocking_reasons": blocking_reasons,
    }


def verify_price_claims(claims, days=260, force=False):
    results = []
    errors = []
    for claim in claims:
        ticker = str(claim.get("ticker") or claim.get("symbol") or "").strip()
        name = claim.get("name") or ticker
        claimed_price = claim.get("claimed_price")
        buy_low = claim.get("buy_low")
        buy_high = claim.get("buy_high")
        target_price = claim.get("target_price")
        stop_loss = claim.get("stop_loss")
        if not ticker:
            errors.append({"claim": claim, "error": "ticker is required"})
            continue
        try:
            fetch = fetch_ohlcv(ticker, name, days=days, force=force)
            validation = cross_validate_ohlcv(ticker, fetch.frame, days=days)
            meta = latest_data_meta(fetch.frame)
            latest = fetch.frame.iloc[-1]
            actual_close = round(float(latest["close"]), 4)
            public_quote = fetch_naver_public_quote(ticker)
            verified_price = round(float(public_quote["price"]), 4) if public_quote.get("ok") else actual_close
            verified_price_source = public_quote["provider"] if public_quote.get("ok") else fetch.provider
            price_diff = None
            price_diff_pct = None
            claim_status = "unchecked"
            tradable = bool(meta["tradable"]) and bool(validation.get("tradable", True))
            checks = []
            if claimed_price is None:
                claim_status = "missing_claim_price"
                checks.append("claimed_price is missing; strategy fields will be checked against verified close.")
            else:
                claimed = float(claimed_price)
                price_diff = round(claimed - verified_price, 4)
                price_diff_pct = round(abs(claimed - verified_price) / verified_price * 100, 4) if verified_price else 100
                if price_diff_pct > MAX_CLAIM_PRICE_DIFF_PCT:
                    claim_status = "price_mismatch"
                    tradable = False
                    checks.append(
                        f"Claimed price {claimed:.4f} differs from verified price {verified_price:.4f} ({verified_price_source}) by {price_diff_pct:.2f}%."
                    )
                else:
                    claim_status = "matched"
            if buy_low is not None and buy_high is not None:
                low = float(buy_low)
                high = float(buy_high)
                if low > high:
                    tradable = False
                    checks.append(f"Buy range is invalid: {low:.4f} > {high:.4f}.")
                elif verified_price > high:
                    gap = (verified_price - high) / verified_price * 100
                    if gap > MAX_STRATEGY_PRICE_GAP_PCT:
                        tradable = False
                        checks.append(
                            f"Buy range {low:.4f}-{high:.4f} is {gap:.2f}% below verified price {verified_price:.4f}."
                        )
                elif verified_price < low:
                    gap = (low - verified_price) / verified_price * 100
                    if gap > MAX_STRATEGY_PRICE_GAP_PCT:
                        tradable = False
                        checks.append(
                            f"Buy range {low:.4f}-{high:.4f} is {gap:.2f}% above verified price {verified_price:.4f}."
                        )
            if target_price is not None:
                target = float(target_price)
                if target <= verified_price:
                    tradable = False
                    checks.append(f"Target price {target:.4f} is not above verified price {verified_price:.4f}.")
            if stop_loss is not None:
                stop = float(stop_loss)
                if stop >= verified_price:
                    tradable = False
                    checks.append(f"Stop loss {stop:.4f} is not below verified price {verified_price:.4f}.")
            if not meta["tradable"]:
                checks.append(meta["no_recommendation_reason"])
            if not validation.get("tradable", True):
                checks.extend(validation.get("checks", []))
            if not tradable and claim_status in ["matched", "missing_claim_price", "unchecked"]:
                claim_status = "strategy_mismatch"
            results.append({
                **meta,
                "ticker": ticker,
                "name": name,
                "claimed_price": claimed_price,
                "buy_low": buy_low,
                "buy_high": buy_high,
                "target_price": target_price,
                "stop_loss": stop_loss,
                "actual_close": actual_close,
                "verified_price": verified_price,
                "verified_price_source": verified_price_source,
                "public_quote": public_quote,
                "price_diff": price_diff,
                "price_diff_pct": price_diff_pct,
                "claim_status": claim_status,
                "tradable": tradable,
                "decision": "VERIFIED" if tradable else "CLAIM_MISMATCH",
                "checks": checks,
                "provider": fetch.provider,
                "rows": fetch.rows,
                "validation": validation,
            })
        except Exception as exc:
            errors.append({"ticker": ticker, "name": name, "error": str(exc)})
    return {
        "count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
        "max_claim_price_diff_pct": MAX_CLAIM_PRICE_DIFF_PCT,
        "max_strategy_price_gap_pct": MAX_STRATEGY_PRICE_GAP_PCT,
    }


def fetch_ohlcv(ticker, name="", days=260, force=False):
    ensure_dirs()
    end = today_kst()
    start = end - timedelta(days=days + 20)
    cache = load_cache(ticker)
    warnings = []
    if not force and not cache.empty:
        latest = pd.to_datetime(cache["date"]).max().date()
        if (end - latest).days <= MAX_DATA_AGE_DAYS and len(cache) >= min(days // 2, 60):
            frame = normalize_ohlcv(cache).tail(days)
            return FetchResult(ticker, name, "cache", len(frame), cache_path_for(ticker), warnings, frame)

    providers = [("pykrx", fetch_with_pykrx), ("FinanceDataReader", fetch_with_finance_datareader)]
    last_error = None
    for provider, func in providers:
        try:
            frame = func(ticker, start.isoformat(), end.isoformat())
            if not frame.empty:
                frame = frame.tail(days)
                path = save_cache(ticker, frame)
                warnings.extend(validate_ohlcv(frame))
                return FetchResult(ticker, name, provider, len(frame), path, warnings, frame)
        except Exception as exc:
            last_error = exc
            warnings.append(f"{provider} failed: {exc}")

    if not cache.empty:
        frame = normalize_ohlcv(cache).tail(days)
        meta = latest_data_meta(frame)
        if not meta["tradable"] and not ALLOW_STALE_CACHE:
            warning_text = "; ".join(warnings) if warnings else "No live provider succeeded."
            raise RuntimeError(
                f"Live fetch failed and stale cache is blocked for {ticker}. "
                f"cache_data_as_of={meta['data_as_of']}, age_days={meta['data_age_days']}. "
                f"Set ALLOW_STALE_CACHE=true only for diagnostics. Provider errors: {warning_text}"
            )
        warnings.append("Using stale cache because live fetch failed.")
        warnings.extend(validate_ohlcv(frame))
        return FetchResult(ticker, name, "stale_cache", len(frame), cache_path_for(ticker), warnings, frame)
    raise RuntimeError(f"No data for {ticker}. Last error: {last_error}")


def validate_ohlcv(frame):
    warnings = []
    if frame.empty:
        return ["No OHLCV rows."]
    latest = pd.to_datetime(frame["date"]).max().date()
    age = (today_kst() - latest).days
    if age > MAX_DATA_AGE_DAYS:
        warnings.append(f"Latest candle is {age} days old: {latest}; exceeds {MAX_DATA_AGE_DAYS}-day freshness policy")
    if len(frame) < 60:
        warnings.append(f"Only {len(frame)} rows; indicators may be weak.")
    if frame["close"].isna().any():
        warnings.append("Close price contains missing values.")
    if (frame["volume"].fillna(0) <= 0).tail(20).all():
        warnings.append("Recent volume is empty or zero.")
    return warnings


def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def rsi(close, window=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / loss.replace(0, math.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(100)


def add_indicators(frame):
    frame = frame.copy()
    close = frame["close"]
    frame["sma20"] = close.rolling(20).mean()
    frame["sma60"] = close.rolling(60).mean()
    frame["ema12"] = ema(close, 12)
    frame["ema26"] = ema(close, 26)
    frame["macd"] = frame["ema12"] - frame["ema26"]
    frame["macd_signal"] = ema(frame["macd"], 9)
    frame["macd_histogram"] = frame["macd"] - frame["macd_signal"]
    frame["rsi14"] = rsi(close, 14)
    high_low = frame["high"] - frame["low"]
    high_close = (frame["high"] - close.shift()).abs()
    low_close = (frame["low"] - close.shift()).abs()
    frame["atr14"] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
    frame["volume20"] = frame["volume"].rolling(20).mean()
    return frame


def score_stock(frame, target_price=None, stop_loss=None):
    frame = add_indicators(frame)
    latest = frame.iloc[-1]
    freshness = latest_data_meta(frame)
    score = 50.0
    reasons = []
    close = latest["close"]
    if pd.notna(latest["sma20"]):
        gap = ((close - latest["sma20"]) / latest["sma20"]) * 100
        score += max(-15, min(15, gap * 1.2))
        reasons.append(f"SMA20 대비 {gap:.2f}%")
    if pd.notna(latest["sma60"]) and pd.notna(latest["sma20"]):
        score += 10 if latest["sma20"] > latest["sma60"] else -10
        reasons.append("SMA20>SMA60" if latest["sma20"] > latest["sma60"] else "SMA20<SMA60")
    score += 8 if latest["ema12"] > latest["ema26"] else -8
    reasons.append("EMA12>EMA26" if latest["ema12"] > latest["ema26"] else "EMA12<EMA26")
    if latest["macd_histogram"] > 0:
        score += 7
        reasons.append("MACD histogram positive")
    else:
        score -= 7
        reasons.append("MACD histogram negative")
    if 45 <= latest["rsi14"] <= 65:
        score += 5
    elif latest["rsi14"] > 75:
        score -= 8
    elif latest["rsi14"] < 30:
        score -= 5
    reasons.append(f"RSI14 {latest['rsi14']:.1f}")
    if target_price:
        upside = ((target_price - close) / close) * 100
        score += max(-8, min(12, upside * 0.2))
        reasons.append(f"목표가까지 {upside:.1f}%")
    if stop_loss and close < stop_loss:
        score -= 18
        reasons.append("손절가 이탈")
    score = round(max(0, min(100, score)), 2)
    decision = "Strong Buy" if score >= 80 else "Buy" if score >= 65 else "Hold" if score > 40 else "Reduce"
    if not freshness["tradable"]:
        decision = "DATA_STALE"
        reasons.append(freshness["no_recommendation_reason"])
    return frame, {
        "score": score,
        "technical_score": score,
        "decision": decision,
        "latest_close": round(float(close), 2),
        "latest_date": str(latest["date"]),
        **freshness,
        "reasons": reasons,
        "indicators": {
            "sma20": round_float(latest["sma20"]),
            "sma60": round_float(latest["sma60"]),
            "ema12": round_float(latest["ema12"]),
            "ema26": round_float(latest["ema26"]),
            "macd": round_float(latest["macd"]),
            "macd_signal": round_float(latest["macd_signal"]),
            "macd_histogram": round_float(latest["macd_histogram"]),
            "rsi14": round_float(latest["rsi14"]),
            "atr14": round_float(latest["atr14"]),
            "volume20": round_float(latest["volume20"]),
        },
    }


def round_float(value, digits=2):
    if pd.isna(value):
        return None
    return round(float(value), digits)


def make_chart(ticker, name, frame):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    frame = add_indicators(frame)
    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.55, 0.22, 0.23],
        subplot_titles=(f"{name}({ticker}) Price", "RSI14", "MACD"),
    )
    fig.add_trace(go.Candlestick(x=frame["date"], open=frame["open"], high=frame["high"], low=frame["low"], close=frame["close"], name="OHLC"), row=1, col=1)
    fig.add_trace(go.Scatter(x=frame["date"], y=frame["sma20"], name="SMA20"), row=1, col=1)
    fig.add_trace(go.Scatter(x=frame["date"], y=frame["sma60"], name="SMA60"), row=1, col=1)
    fig.add_trace(go.Bar(x=frame["date"], y=frame["volume"], name="Volume", opacity=0.3), row=1, col=1)
    fig.add_trace(go.Scatter(x=frame["date"], y=frame["rsi14"], name="RSI14"), row=2, col=1)
    fig.add_hline(y=70, line_dash="dot", row=2, col=1)
    fig.add_hline(y=30, line_dash="dot", row=2, col=1)
    fig.add_trace(go.Scatter(x=frame["date"], y=frame["macd"], name="MACD"), row=3, col=1)
    fig.add_trace(go.Scatter(x=frame["date"], y=frame["macd_signal"], name="Signal"), row=3, col=1)
    fig.add_trace(go.Bar(x=frame["date"], y=frame["macd_histogram"], name="Histogram"), row=3, col=1)
    fig.update_layout(template="plotly_white", height=850, xaxis_rangeslider_visible=False)
    path = CHART_DIR / f"{ticker}_{name}_chart.html"
    fig.write_html(str(path), include_plotlyjs="cdn")
    return path


def load_watchlist(path=None):
    if path and Path(path).exists():
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else payload.get("items", DEFAULT_WATCHLIST)
    return DEFAULT_WATCHLIST


def analyze_watchlist(watchlist, days=260, force=False):
    ensure_dirs()
    results = []
    for item in watchlist:
        ticker = item["ticker"]
        name = item.get("name", ticker)
        fetch = fetch_ohlcv(ticker, name, days=days, force=force)
        frame, score = score_stock(fetch.frame, item.get("target_price"), item.get("stop_loss"))
        validation = cross_validate_ohlcv(ticker, fetch.frame, days=days)
        score = apply_validation_to_score(score, validation)
        chart_path = make_chart(ticker, name, frame)
        results.append({
            "ticker": ticker,
            "name": name,
            "provider": fetch.provider,
            "rows": fetch.rows,
            "cache_path": str(fetch.cache_path),
            "chart_path": str(chart_path),
            "warnings": fetch.warnings,
            "validation": validation,
            "target_price": item.get("target_price"),
            "stop_loss": item.get("stop_loss"),
            **score,
        })
    results.sort(key=lambda row: (bool(row.get("tradable")), row.get("score") or -1), reverse=True)
    out = OUTPUT_DIR / "precision_results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(results)
    return results


def write_report(results):
    lines = [
        f"# 정밀 데이터 연동 검증 리포트",
        "",
        f"- 생성 시각: {datetime.now(timezone.utc).replace(microsecond=0).isoformat()} UTC",
        f"- 분석 종목 수: {len(results)}",
        "",
        "## 데이터 연동 상태",
    ]
    for row in results:
        warn = "; ".join(row["warnings"]) if row["warnings"] else "정상"
        lines.append(f"- {row['name']}({row['ticker']}): {row['provider']}, {row['rows']} rows, {warn}")
    lines.extend(["", "## 전략 점수"])
    for idx, row in enumerate(results, start=1):
        lines.extend([
            f"{idx}. {row['name']}({row['ticker']}) - {row['decision']} / score {row['score']}",
            f"   - 분석일/데이터 기준일: {row.get('analysis_date')} / {row.get('data_as_of')}",
            f"   - 최근가: {row['latest_close']} ({row['latest_date']})",
            f"   - 신선도: {row.get('freshness_status')} / 추천 가능: {row.get('tradable')}",
            f"   - 목표가: {row.get('target_price')} / 손절가: {row.get('stop_loss')}",
            f"   - 근거: {', '.join(row['reasons'])}",
            f"   - 차트: {row['chart_path']}",
        ])
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "precision_report.md").write_text("\n".join(lines), encoding="utf-8")


def build_parser():
    parser = argparse.ArgumentParser(description="Korean stock precision data connector")
    parser.add_argument("--watchlist")
    parser.add_argument("--days", type=int, default=260)
    parser.add_argument("--force", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()
    results = analyze_watchlist(load_watchlist(args.watchlist), days=args.days, force=args.force)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
