#!/usr/bin/env python3
"""Preview/review chart engine for strategy rehearsal.

The first version works on daily OHLCV so the workflow can review historical
signals before the Kiwoom intraday engine is available.
"""

import argparse
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import market_data


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs" / "preview_review"
INITIAL_ORDER_BUDGET_KRW = 100_000


def add_stochastic(frame, k_window=5, k_smooth=3, d_window=3):
    data = market_data.add_indicators(frame).copy()
    data["date"] = pd.to_datetime(data["date"])
    low_min = data["low"].rolling(k_window).min()
    high_max = data["high"].rolling(k_window).max()
    raw_k = ((data["close"] - low_min) / (high_max - low_min).replace(0, pd.NA)) * 100
    data["stoch_k"] = raw_k.rolling(k_smooth).mean()
    data["stoch_d"] = data["stoch_k"].rolling(d_window).mean()
    data["stoch_gap"] = (data["stoch_k"] - data["stoch_d"]).abs()
    return data


def classify_signal(row, previous):
    if pd.isna(row.get("sma20")) or pd.isna(row.get("sma60")):
        return "WAIT", "indicator_warmup"

    trend_ok = row["sma20"] >= row["sma60"] or row["close"] >= row["sma20"]
    down_risk = row["sma20"] < row["sma60"] and row["close"] < row["sma20"]
    oversold_setup = (
        pd.notna(row.get("stoch_k"))
        and pd.notna(row.get("stoch_d"))
        and row["stoch_k"] <= 20
        and row["stoch_d"] <= 25
        and row["stoch_gap"] <= 7
    )
    cross_up = (
        previous is not None
        and pd.notna(previous.get("stoch_k"))
        and pd.notna(previous.get("stoch_d"))
        and pd.notna(row.get("stoch_k"))
        and pd.notna(row.get("stoch_d"))
        and previous["stoch_k"] <= previous["stoch_d"]
        and row["stoch_k"] > row["stoch_d"]
    )
    volume_ok = pd.notna(row.get("volume20")) and row["volume"] >= row["volume20"] * 0.8
    breakout_fail = (
        previous is not None
        and row["close"] < previous["close"]
        and row["volume"] > previous["volume"] * 1.2
        and row["stoch_k"] < row["stoch_d"]
    )

    if breakout_fail:
        return "REDUCE", "high_volume_reversal_or_breakout_failure"
    if down_risk:
        return "AVOID", "downtrend_or_sma20_break"
    if trend_ok and oversold_setup and not cross_up:
        return "PREPARE", "stochastic_gap_narrowing_before_cross"
    if trend_ok and cross_up and volume_ok:
        return "BUY", "stochastic_cross_up_with_trend_support"
    if trend_ok:
        return "HOLD", "trend_ok_wait_for_precise_trigger"
    return "WAIT", "no_edge"


def build_review_rows(frame):
    rows = []
    previous = None
    for _, row in frame.iterrows():
        signal, reason = classify_signal(row, previous)
        rows.append(
            {
                "date": str(pd.to_datetime(row["date"]).date()),
                "close": float(row["close"]),
                "signal": signal,
                "reason": reason,
                "stoch_k": None if pd.isna(row.get("stoch_k")) else round(float(row["stoch_k"]), 2),
                "stoch_d": None if pd.isna(row.get("stoch_d")) else round(float(row["stoch_d"]), 2),
                "sma20": None if pd.isna(row.get("sma20")) else round(float(row["sma20"]), 2),
                "sma60": None if pd.isna(row.get("sma60")) else round(float(row["sma60"]), 2),
                "volume": int(row["volume"]) if pd.notna(row.get("volume")) else None,
                "eligible_initial_auto_order": (
                    bool(row["close"] <= INITIAL_ORDER_BUDGET_KRW)
                    if pd.notna(row.get("close"))
                    else False
                ),
            }
        )
        previous = row
    return rows


def make_review_chart(ticker, name, frame, rows):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.48, 0.16, 0.18, 0.18],
        subplot_titles=("Price and signals", "Volume", "Stochastic 5,3,3", "MACD"),
    )
    fig.add_trace(
        go.Candlestick(
            x=frame["date"],
            open=frame["open"],
            high=frame["high"],
            low=frame["low"],
            close=frame["close"],
            name="OHLC",
        ),
        row=1,
        col=1,
    )
    fig.add_trace(go.Scatter(x=frame["date"], y=frame["sma20"], name="SMA20"), row=1, col=1)
    fig.add_trace(go.Scatter(x=frame["date"], y=frame["sma60"], name="SMA60"), row=1, col=1)
    fig.add_trace(go.Bar(x=frame["date"], y=frame["volume"], name="Volume"), row=2, col=1)
    fig.add_trace(go.Scatter(x=frame["date"], y=frame["stoch_k"], name="%K"), row=3, col=1)
    fig.add_trace(go.Scatter(x=frame["date"], y=frame["stoch_d"], name="%D"), row=3, col=1)
    fig.add_hline(y=20, line_dash="dot", row=3, col=1)
    fig.add_hline(y=80, line_dash="dot", row=3, col=1)
    fig.add_trace(go.Scatter(x=frame["date"], y=frame["macd"], name="MACD"), row=4, col=1)
    fig.add_trace(go.Scatter(x=frame["date"], y=frame["macd_signal"], name="MACD Signal"), row=4, col=1)
    fig.add_trace(go.Bar(x=frame["date"], y=frame["macd_histogram"], name="MACD Hist"), row=4, col=1)

    marker_style = {
        "PREPARE": ("triangle-up", "#f59e0b"),
        "BUY": ("star", "#16a34a"),
        "REDUCE": ("triangle-down", "#dc2626"),
        "AVOID": ("x", "#6b7280"),
    }
    row_by_date = {item["date"]: item for item in rows}
    for signal, (symbol, color) in marker_style.items():
        points = frame[
            frame["date"].dt.date.astype(str).map(lambda value: row_by_date.get(value, {}).get("signal") == signal)
        ]
        if points.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=points["date"],
                y=points["close"],
                mode="markers",
                name=signal,
                marker={"symbol": symbol, "size": 12, "color": color},
                text=[
                    row_by_date[str(pd.to_datetime(item).date())]["reason"]
                    for item in points["date"]
                ],
                hovertemplate="%{x}<br>%{y}<br>%{text}<extra></extra>",
            ),
            row=1,
            col=1,
        )

    fig.update_layout(
        title=f"{name}({ticker}) preview/review",
        xaxis_rangeslider_visible=False,
        height=1100,
        template="plotly_white",
    )
    path = OUTPUT_DIR / f"{ticker}_preview_review.html"
    fig.write_html(path, include_plotlyjs="cdn")
    return path


def summarize(rows):
    counts = {}
    for row in rows:
        counts[row["signal"]] = counts.get(row["signal"], 0) + 1
    return counts


def review_outcomes(rows, lookahead_days=10):
    outcomes = []
    for index, row in enumerate(rows):
        if row["signal"] not in {"PREPARE", "BUY", "REDUCE", "AVOID"}:
            continue
        future = rows[index + 1 : index + 1 + lookahead_days]
        future_closes = [item["close"] for item in future if item.get("close") is not None]
        if not future_closes:
            continue
        entry = row["close"]
        max_gain = ((max(future_closes) - entry) / entry) * 100
        max_loss = ((min(future_closes) - entry) / entry) * 100
        end_return = ((future_closes[-1] - entry) / entry) * 100
        outcomes.append(
            {
                "date": row["date"],
                "signal": row["signal"],
                "reason": row["reason"],
                "entry_close": round(entry, 2),
                "lookahead_days": lookahead_days,
                "max_gain_pct": round(max_gain, 2),
                "max_loss_pct": round(max_loss, 2),
                "end_return_pct": round(end_return, 2),
                "initial_auto_order_allowed": row["eligible_initial_auto_order"],
            }
        )
    return outcomes


def run(ticker, name="", days=260, force=False):
    fetch = market_data.fetch_ohlcv(ticker, name or ticker, days=days, force=force)
    frame = add_stochastic(fetch.frame)
    rows = build_review_rows(frame)
    chart_path = make_review_chart(ticker, name or ticker, frame, rows)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"{ticker}_preview_review.json"
    result = {
        "ticker": ticker,
        "name": name or ticker,
        "provider": fetch.provider,
        "initial_order_budget_krw": INITIAL_ORDER_BUDGET_KRW,
        "initial_auto_order_note": "Rows above the budget are review-only until the user changes the policy.",
        "rows": len(rows),
        "summary": summarize(rows),
        "outcomes_10d": review_outcomes(rows, lookahead_days=10),
        "chart_path": str(chart_path),
        "signals": rows,
    }
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["json_path"] = str(json_path)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("--name", default="")
    parser.add_argument("--days", type=int, default=260)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = run(args.ticker, args.name, args.days, args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
