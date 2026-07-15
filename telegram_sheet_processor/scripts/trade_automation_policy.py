#!/usr/bin/env python3
"""Automation policy layer between strategy signals and real orders.

This module is intentionally conservative.  It converts preview/review output
into an execution candidate, but it never places an order by itself.  The goal is
to keep the future Kiwoom REST order bridge behind explicit gates.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


DEFAULT_INITIAL_ORDER_BUDGET_KRW = 100_000
DEFAULT_MAX_POSITION_WEIGHT = 0.20
VALID_AUTOMATION_MODES = {"review_only", "approval_required", "paper", "small_auto"}


def today_kst_iso() -> str:
    return datetime.now(timezone(timedelta(hours=9))).date().isoformat()


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except Exception:
        return default


def _env_mode() -> str:
    mode = os.getenv("AUTO_TRADE_MODE", "review_only").strip().lower()
    return mode if mode in VALID_AUTOMATION_MODES else "review_only"


@dataclass(frozen=True)
class AutomationSettings:
    mode: str = "review_only"
    initial_order_budget_krw: float = DEFAULT_INITIAL_ORDER_BUDGET_KRW
    max_position_weight: float = DEFAULT_MAX_POSITION_WEIGHT
    require_human_approval: bool = True
    allow_live_orders: bool = False
    require_broker_realtime: bool = True
    require_intraday_signal: bool = True

    @classmethod
    def from_env(cls) -> "AutomationSettings":
        mode = _env_mode()
        return cls(
            mode=mode,
            initial_order_budget_krw=_env_float(
                "AUTO_TRADE_INITIAL_ORDER_BUDGET_KRW",
                DEFAULT_INITIAL_ORDER_BUDGET_KRW,
            ),
            max_position_weight=_env_float("AUTO_TRADE_MAX_POSITION_WEIGHT", DEFAULT_MAX_POSITION_WEIGHT),
            require_human_approval=_env_bool("AUTO_TRADE_REQUIRE_APPROVAL", True),
            allow_live_orders=_env_bool("AUTO_TRADE_ALLOW_LIVE_ORDERS", False),
            require_broker_realtime=_env_bool("AUTO_TRADE_REQUIRE_BROKER_REALTIME", True),
            require_intraday_signal=_env_bool("AUTO_TRADE_REQUIRE_INTRADAY_SIGNAL", True),
        )


def automation_status(settings: AutomationSettings | None = None) -> dict[str, Any]:
    effective = settings or AutomationSettings.from_env()
    return {
        "analysis_date": today_kst_iso(),
        "mode": effective.mode,
        "valid_modes": sorted(VALID_AUTOMATION_MODES),
        "initial_order_budget_krw": effective.initial_order_budget_krw,
        "max_position_weight": effective.max_position_weight,
        "require_human_approval": effective.require_human_approval,
        "allow_live_orders": effective.allow_live_orders,
        "require_broker_realtime": effective.require_broker_realtime,
        "require_intraday_signal": effective.require_intraday_signal,
        "safety_policy": (
            "Daily preview/review signals can create candidates only. "
            "Live orders require broker realtime data, intraday confirmation, "
            "explicit AUTO_TRADE_ALLOW_LIVE_ORDERS=true, and the chosen mode."
        ),
    }


def latest_signal(review: dict[str, Any]) -> dict[str, Any]:
    signals = review.get("signals") or []
    for row in reversed(signals):
        if row.get("signal") in {"BUY", "PREPARE", "REDUCE", "AVOID"}:
            return dict(row)
    return {}


def _probability(review: dict[str, Any], signal: str) -> float | None:
    bucket = (review.get("probability_10d") or {}).get(signal) or {}
    value = bucket.get("positive_end_probability_pct")
    try:
        return None if value is None else float(value)
    except Exception:
        return None


def _relative_strength_score(relative_strength: dict[str, Any] | None) -> float | None:
    if not isinstance(relative_strength, dict):
        return None
    values = relative_strength.get("relative_strength") or {}
    for key in ["60d", "20d", "120d"]:
        value = values.get(key)
        try:
            return None if value is None else float(value)
        except Exception:
            continue
    return None


def _quote_price(quote: dict[str, Any] | None) -> float | None:
    if not isinstance(quote, dict):
        return None
    for key in ["quote_price", "price"]:
        value = quote.get(key)
        try:
            return None if value is None else float(value)
        except Exception:
            continue
    nested = quote.get("quote")
    if isinstance(nested, dict):
        return _quote_price(nested)
    return None


def _broker_realtime_available(quote: dict[str, Any] | None) -> bool:
    if not isinstance(quote, dict):
        return False
    label = str(quote.get("quote_label") or quote.get("priority") or quote.get("provider") or "")
    source = str(quote.get("quote_source") or quote.get("provider") or "")
    raw = quote.get("raw") if isinstance(quote.get("raw"), dict) else {}
    return any(token in f"{label} {source}".lower() for token in ["kiwoom", "kis", "broker_realtime"]) or bool(
        raw.get("realtime")
    )


def evaluate_candidate(
    review: dict[str, Any],
    quote: dict[str, Any] | None = None,
    relative_strength: dict[str, Any] | None = None,
    settings: AutomationSettings | None = None,
) -> dict[str, Any]:
    """Return an automation decision without placing any order."""

    effective = settings or AutomationSettings.from_env()
    signal_row = latest_signal(review)
    signal = signal_row.get("signal") or "WAIT"
    ticker = str(review.get("ticker") or "")
    name = str(review.get("name") or ticker)
    price = _quote_price(quote)
    buy_probability = _probability(review, "BUY")
    prepare_probability = _probability(review, "PREPARE")
    relative_score = _relative_strength_score(relative_strength)
    broker_realtime = _broker_realtime_available(quote)

    blockers: list[str] = []
    warnings: list[str] = []
    action = "REVIEW_ONLY"
    side = "NONE"
    order_type = "none"
    quantity = 0
    estimated_amount = 0.0

    if signal in {"REDUCE", "AVOID"}:
        action = "RISK_REDUCTION_REVIEW"
        side = "SELL_REVIEW"
        blockers.append(f"latest signal is {signal}; do not open a new buy position.")
    elif signal not in {"BUY", "PREPARE"}:
        blockers.append(f"latest actionable signal is {signal}; wait for BUY/PREPARE.")

    if price is None or price <= 0:
        blockers.append("verified quote price is unavailable.")
    elif price > effective.initial_order_budget_krw:
        blockers.append(
            f"price {price:,.0f} exceeds initial order budget {effective.initial_order_budget_krw:,.0f}."
        )
    else:
        quantity = max(1, int(effective.initial_order_budget_krw // price))
        estimated_amount = round(quantity * price, 2)

    if signal == "BUY" and buy_probability is not None and buy_probability < 55:
        warnings.append(f"BUY 10-day positive probability is low: {buy_probability:.2f}%.")
    if signal == "PREPARE" and prepare_probability is not None and prepare_probability < 50:
        warnings.append(f"PREPARE 10-day positive probability is low: {prepare_probability:.2f}%.")
    if relative_score is not None and relative_score < 0:
        warnings.append(f"relative strength is negative: {relative_score:.2f}%.")

    if effective.require_intraday_signal:
        blockers.append("30-minute intraday confirmation is not connected yet.")
    if effective.require_broker_realtime and not broker_realtime:
        blockers.append("broker realtime quote is not confirmed.")

    if not blockers and signal in {"BUY", "PREPARE"}:
        side = "BUY"
        if effective.mode == "approval_required":
            action = "APPROVAL_REQUIRED"
            order_type = "approval_candidate"
        elif effective.mode == "paper":
            action = "PAPER_TRADE_READY"
            order_type = "paper"
        elif effective.mode == "small_auto" and effective.allow_live_orders and not effective.require_human_approval:
            action = "SMALL_AUTO_READY"
            order_type = "small_auto_live_candidate"
        else:
            action = "REVIEW_ONLY"
            order_type = "review_candidate"
            blockers.append("automation mode does not allow order submission.")

    return {
        "ticker": ticker,
        "name": name,
        "analysis_date": today_kst_iso(),
        "latest_signal": signal,
        "signal_reason": signal_row.get("reason"),
        "action": action,
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
        "estimated_amount_krw": estimated_amount,
        "price": price,
        "buy_probability_10d_pct": buy_probability,
        "prepare_probability_10d_pct": prepare_probability,
        "relative_strength_60d_pct": relative_score,
        "broker_realtime_available": broker_realtime,
        "can_submit_order": action in {"PAPER_TRADE_READY", "SMALL_AUTO_READY"},
        "requires_human_approval": action == "APPROVAL_REQUIRED",
        "blockers": blockers,
        "warnings": warnings,
        "settings": automation_status(effective),
    }
