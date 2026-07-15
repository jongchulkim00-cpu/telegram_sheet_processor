#!/usr/bin/env python3
"""Kiwoom REST bridge for the stock API.

Run this on any machine that can reach Kiwoom REST API. It starts in mock mode
so the Linux home server can test networking before real keys are configured.

Environment:
  KIWOOM_BRIDGE_MODE=mock|rest
  KIWOOM_BRIDGE_HOST=0.0.0.0
  KIWOOM_BRIDGE_PORT=8080
  KIWOOM_REST_APP_KEY=...
  KIWOOM_REST_APP_SECRET=...
  KIWOOM_REST_BASE_URL=https://mockapi.kiwoom.com

Endpoints exposed for the home server:
  GET  /health
  GET  /quote/{ticker}
  POST /quote {"ticker": "005930"}
"""
from __future__ import annotations

import os
import time
from typing import Any

import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Kiwoom REST Bridge", version="0.2.0")

MODE = os.getenv("KIWOOM_BRIDGE_MODE", "mock").strip().lower()
HOST = os.getenv("KIWOOM_BRIDGE_HOST", "0.0.0.0")
PORT = int(os.getenv("KIWOOM_BRIDGE_PORT", "8080"))
BASE_URL = os.getenv("KIWOOM_REST_BASE_URL", "https://mockapi.kiwoom.com").rstrip("/")
APP_KEY = os.getenv("KIWOOM_REST_APP_KEY", "").strip()
APP_SECRET = os.getenv("KIWOOM_REST_APP_SECRET", "").strip()
REQUEST_TIMEOUT = float(os.getenv("KIWOOM_REST_TIMEOUT_SECONDS", "10"))

MOCK_QUOTES = {
    "399720": 123456,
    "005930": 91700,
    "000660": 123000,
    "247540": 215000,
    "039030": 359500,
    "011790": 88000,
}

_TOKEN_CACHE: dict[str, Any] = {"token": None, "expires_at": 0.0, "expires_dt": None}


class QuoteRequest(BaseModel):
    ticker: str


def normalize_ticker(ticker: str) -> str:
    normalized = str(ticker or "").strip()
    if not normalized.isdigit() or len(normalized) != 6:
        raise HTTPException(status_code=400, detail="ticker must be a 6-digit Korean stock code")
    return normalized


def parse_price(value: Any) -> float | None:
    if value in [None, ""]:
        return None
    text = str(value).strip().replace(",", "")
    # Kiwoom REST price fields can contain signs to represent direction.
    text = text.lstrip("+-")
    try:
        return float(text)
    except ValueError:
        return None


def token_cache_is_valid() -> bool:
    token = _TOKEN_CACHE.get("token")
    expires_at = float(_TOKEN_CACHE.get("expires_at") or 0)
    return bool(token) and time.time() < expires_at - 60


def get_access_token() -> str:
    if token_cache_is_valid():
        return str(_TOKEN_CACHE["token"])
    if not APP_KEY or not APP_SECRET:
        raise HTTPException(
            status_code=500,
            detail="KIWOOM_REST_APP_KEY and KIWOOM_REST_APP_SECRET are required in rest mode.",
        )

    response = requests.post(
        f"{BASE_URL}/oauth2/token",
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "api-id": "au10001",
        },
        json={
            "grant_type": "client_credentials",
            "appkey": APP_KEY,
            "secretkey": APP_SECRET,
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("token")
    if not token:
        raise HTTPException(
            status_code=502,
            detail=f"Kiwoom token response did not contain token: {payload.get('return_msg') or payload}",
        )

    _TOKEN_CACHE.update({
        "token": token,
        "expires_at": time.time() + 55 * 60,
        "expires_dt": payload.get("expires_dt"),
    })
    return str(token)


def fetch_mock_quote(ticker: str) -> dict[str, Any]:
    price = MOCK_QUOTES.get(ticker)
    if price is None:
        raise HTTPException(status_code=404, detail=f"No mock quote for {ticker}")
    return {
        "ok": True,
        "ticker": ticker,
        "price": float(price),
        "source": "kiwoom_bridge_mock",
    }


def fetch_kiwoom_rest_quote(ticker: str) -> dict[str, Any]:
    token = get_access_token()
    response = requests.post(
        f"{BASE_URL}/api/dostk/stkinfo",
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "authorization": f"Bearer {token}",
            "api-id": "ka10001",
        },
        json={"stk_cd": ticker},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    price = parse_price(payload.get("cur_prc"))
    if price is None:
        # Some wrappers may transform field names; keep this permissive.
        for key in ["price", "cur_price", "current_price", "last", "close"]:
            price = parse_price(payload.get(key))
            if price is not None:
                break
    if price is None:
        raise HTTPException(status_code=502, detail=f"No current price in Kiwoom response: {payload}")

    return {
        "ok": True,
        "ticker": ticker,
        "name": payload.get("stk_nm"),
        "price": float(price),
        "source": "kiwoom_rest_ka10001",
        "base_url": BASE_URL,
        "api_id": "ka10001",
        "raw": payload,
    }


def fetch_quote(ticker: str) -> dict[str, Any]:
    ticker = normalize_ticker(ticker)
    if MODE == "mock":
        return fetch_mock_quote(ticker)
    if MODE == "rest":
        return fetch_kiwoom_rest_quote(ticker)
    raise HTTPException(status_code=500, detail="KIWOOM_BRIDGE_MODE must be mock or rest")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "mode": MODE,
        "host": HOST,
        "port": PORT,
        "base_url": BASE_URL if MODE == "rest" else None,
        "app_key_configured": bool(APP_KEY),
        "app_secret_configured": bool(APP_SECRET),
        "token_cached": token_cache_is_valid(),
        "token_expires_dt": _TOKEN_CACHE.get("expires_dt"),
    }


@app.get("/quote/{ticker}")
def quote_get(ticker: str) -> dict[str, Any]:
    result = fetch_quote(ticker)
    return {"ok": True, **result}


@app.post("/quote")
def quote_post(request: QuoteRequest) -> dict[str, Any]:
    result = fetch_quote(request.ticker)
    return {"ok": True, **result}


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
