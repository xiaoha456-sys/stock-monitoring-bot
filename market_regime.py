#!/usr/bin/env python3
"""Benchmark index regime detection for US / CN / AU markets."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from tuning import get_thresholds

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "portfolio_config.json"

DEFAULT_INDICES: dict[str, dict[str, str]] = {
    "US": {"ticker": "SPY", "name": "标普500 (SPY)"},
    "CN": {"ticker": "000001.SS", "name": "上证指数"},
    "AU": {"ticker": "^AXJO", "name": "ASX 200"},
}


@dataclass(frozen=True)
class MarketRegime:
    market_key: str
    index_name: str
    ticker: str
    price: float
    change_pct: float
    trend: str
    rsi_14: float
    label: str
    stance: str
    buy_threshold_bonus: float
    top_n_multiplier: float
    summary: str


def _load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _index_config(market_key: str) -> dict[str, str]:
    config = _load_config().get("market_indices", {})
    defaults = DEFAULT_INDICES[market_key]
    block = config.get(market_key, {})
    return {
        "ticker": str(block.get("ticker", defaults["ticker"])),
        "name": str(block.get("name", defaults["name"])),
    }


def _trend_label(price: float, sma_50: float, sma_200: float) -> str:
    if price > sma_50 > sma_200:
        return "多头排列"
    if price < sma_50 < sma_200:
        return "空头排列"
    return "均线交错"


def fetch_market_regime(market_key: str) -> MarketRegime | None:
    """Load benchmark index metrics and classify today's market regime."""
    index = _index_config(market_key)
    ticker = index["ticker"]
    name = index["name"]

    try:
        from stock_bot import calculate_rsi

        history = yf.Ticker(ticker).history(period="1y", interval="1d", auto_adjust=True)
        close = history.get("Close", pd.Series(dtype=float)).dropna()
        if len(close) < 55:
            raise ValueError(f"insufficient index history for {ticker}")

        price = float(close.iloc[-1])
        previous = float(close.iloc[-2])
        change_pct = (price / previous - 1) * 100
        sma_50 = float(close.tail(50).mean())
        sma_200 = float(close.tail(min(200, len(close))).mean())
        rsi_14 = float(calculate_rsi(close).iloc[-1])
        trend = _trend_label(price, sma_50, sma_200)
    except Exception as exc:
        print(f"Warning: index regime fetch failed for {market_key} ({ticker}): {exc}", file=sys.stderr)
        return None

    return _classify_regime(
        market_key=market_key,
        index_name=name,
        ticker=ticker,
        price=price,
        change_pct=change_pct,
        trend=trend,
        rsi_14=rsi_14,
    )


def _classify_regime(
    *,
    market_key: str,
    index_name: str,
    ticker: str,
    price: float,
    change_pct: float,
    trend: str,
    rsi_14: float,
) -> MarketRegime:
    score = 0.0
    if trend == "多头排列":
        score += 2
    elif trend == "空头排列":
        score -= 2

    if change_pct >= 1.0:
        score += 1.5
    elif change_pct >= 0:
        score += 0.5
    elif change_pct <= -1.5:
        score -= 1.5
    elif change_pct < 0:
        score -= 0.5

    if 45 <= rsi_14 <= 65:
        score += 0.5
    elif rsi_14 > 72:
        score -= 0.5
    elif rsi_14 < 35:
        score -= 0.5

    if score >= 2:
        label = "强势"
        stance = "大盘偏强，可积极在个股回调中分批布局"
        buy_threshold_bonus = 0.0
        top_n_multiplier = 1.0
    elif score <= -1.5:
        label = "弱势"
        stance = "大盘偏弱，宜精选高评分个股、控制仓位，不宜追涨"
        buy_threshold_bonus = 4.0
        top_n_multiplier = 0.67
    else:
        label = "震荡"
        stance = "大盘震荡，优选个股、等待买入区间内低吸"
        buy_threshold_bonus = 2.0
        top_n_multiplier = 0.85

    sign = "+" if change_pct >= 0 else ""
    summary = (
        f"{index_name} {price:.2f}（{sign}{change_pct:.2f}%），"
        f"{trend}，RSI {rsi_14:.0f} → **{label}**"
    )
    return MarketRegime(
        market_key=market_key,
        index_name=index_name,
        ticker=ticker,
        price=price,
        change_pct=change_pct,
        trend=trend,
        rsi_14=rsi_14,
        label=label,
        stance=stance,
        buy_threshold_bonus=buy_threshold_bonus,
        top_n_multiplier=top_n_multiplier,
        summary=summary,
    )


def fetch_all_regimes() -> dict[str, MarketRegime]:
    regimes: dict[str, MarketRegime] = {}
    for market_key in ("US", "CN", "AU"):
        regime = fetch_market_regime(market_key)
        if regime:
            regimes[market_key] = regime
    return regimes


def regime_to_dict(regime: MarketRegime) -> dict[str, Any]:
    return {
        "index_name": regime.index_name,
        "ticker": regime.ticker,
        "price": regime.price,
        "change_pct": regime.change_pct,
        "trend": regime.trend,
        "rsi_14": regime.rsi_14,
        "label": regime.label,
        "stance": regime.stance,
        "buy_threshold_bonus": regime.buy_threshold_bonus,
        "top_n_multiplier": regime.top_n_multiplier,
        "summary": regime.summary,
    }


def format_regime_overview(regimes: dict[str, MarketRegime]) -> str:
    if not regimes:
        return ""
    labels = {"US": "🇺🇸 美股", "CN": "🇨🇳 A股", "AU": "🇦🇺 澳股"}
    lines = [
        "## 今日大盘环境",
        "",
        "| 市场 | 指数 | 涨跌 | 趋势 | 环境 | 操作基调 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for market_key in ("US", "CN", "AU"):
        regime = regimes.get(market_key)
        if not regime:
            continue
        sign = "+" if regime.change_pct >= 0 else ""
        lines.append(
            f"| {labels[market_key]} | {regime.index_name} | "
            f"{sign}{regime.change_pct:.2f}% | {regime.trend} | "
            f"**{regime.label}** | {regime.stance} |"
        )
    lines.append("")
    return "\n".join(lines)


def select_picks_with_regime(
    ranked: list[Any],
    top_n: int,
    regime: MarketRegime | None,
) -> tuple[list[Any], list[Any]]:
    """Filter and trim picks using benchmark regime thresholds."""
    thresholds = get_thresholds()
    bonus = regime.buy_threshold_bonus if regime else 0.0
    multiplier = regime.top_n_multiplier if regime else 1.0
    effective_top_n = max(1, round(top_n * multiplier))

    buy_line = thresholds["buy"] + bonus
    watch_line = thresholds["watch"] + bonus * 0.5

    actionable = [
        rec
        for rec in ranked
        if rec.score >= watch_line and rec.action in ("买入", "逢低关注")
    ]
    strong = [rec for rec in actionable if rec.score >= buy_line]
    picks_source = strong if strong else actionable
    picks = picks_source[:effective_top_n] if picks_source else ranked[: min(2, len(ranked))]
    pick_tickers = {rec.ticker for rec in picks}
    others = [rec for rec in ranked if rec.ticker not in pick_tickers]
    return picks, others


def regime_context_for_alphasift(regimes: dict[str, MarketRegime]) -> str:
    cn = regimes.get("CN")
    if not cn:
        return ""
    return (
        f"今日A股大盘：{cn.index_name} {cn.change_pct:+.2f}%，{cn.trend}，"
        f"环境{cn.label}。{cn.stance}"
    )
