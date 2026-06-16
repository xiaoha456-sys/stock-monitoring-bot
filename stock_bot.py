#!/usr/bin/env python3
"""Generate daily equity recommendations by market and deliver them to WeChat."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import smtplib
import sys
from dataclasses import dataclass, replace
from email.message import EmailMessage
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

from market_regime import (
    MarketRegime,
    fetch_all_regimes,
    fetch_market_regime,
    format_regime_overview,
    regime_context_for_alphasift,
    regime_to_dict,
    select_picks_with_regime,
)
from tuning import (
    get_market_tuning,
    get_price_level_params,
    get_quant_params,
    get_thresholds,
)

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "portfolio_config.json"
PREDICTIONS_DIR = ROOT / "data" / "predictions"
REVIEW_SCORES_PATH = ROOT / "data" / "review_scores.json"
SYDNEY = ZoneInfo("Australia/Sydney")

Action = Literal["买入", "逢低关注", "观望", "减仓", "回避"]
MARKET_ORDER = ("US", "CN", "AU")

NEWS_QUERIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "NVDA": ("NVIDIA", ("nvidia", "nvda")),
    "MU": ("Micron Technology", ("micron", "mu stock")),
    "QCOM": ("Qualcomm", ("qualcomm", "qcom")),
    "TSLA": ("Tesla", ("tesla", "tsla")),
    "AMD": ("AMD", ("amd", "advanced micro")),
    "MSFT": ("Microsoft", ("microsoft", "msft")),
    "AAPL": ("Apple", ("apple", "aapl")),
    "GOOGL": ("Alphabet Google", ("alphabet", "google", "googl")),
    "META": ("Meta Platforms", ("meta", "facebook")),
    "AMZN": ("Amazon", ("amazon", "amzn")),
    "AVGO": ("Broadcom", ("broadcom", "avgo")),
    "SMCI": ("Super Micro Computer", ("super micro", "smci")),
    "PLTR": ("Palantir", ("palantir", "pltr")),
    "COIN": ("Coinbase", ("coinbase", "coin")),
    "ARM": ("ARM Holdings", ("arm holdings", "arm stock")),
    "600519.SS": ("Kweichow Moutai", ("moutai", "茅台", "600519")),
    "000858.SZ": ("Wuliangye", ("wuliangye", "五粮液", "000858")),
    "600036.SS": ("China Merchants Bank", ("merchants bank", "招商银行", "600036")),
    "601318.SS": ("Ping An Insurance", ("ping an", "平安", "601318")),
    "300750.SZ": ("CATL", ("catl", "宁德时代", "300750")),
    "002594.SZ": ("BYD", ("byd", "比亚迪", "002594")),
    "600900.SS": ("China Yangtze Power", ("yangtze power", "长江电力", "600900")),
    "000333.SZ": ("Midea Group", ("midea", "美的", "000333")),
    "601012.SS": ("LONGi Green Energy", ("longi", "隆基", "601012")),
    "688981.SS": ("SMIC", ("smic", "中芯国际", "688981")),
    "002402.SZ": ("H&T Intelligent Control", ("和而泰", "002402")),
    "600406.SS": ("NARI Technology", ("国电南瑞", "600406")),
    "002065.SZ": ("DHC Software", ("东华软件", "002065")),
    "CBA.AX": (
        "Commonwealth Bank of Australia",
        ("commonwealth bank", "cba stock", "cba shares"),
    ),
    "WTC.AX": ("WiseTech Global", ("wisetech", "wtc stock", "wtc shares")),
    "TLX.AX": ("Telix Pharmaceuticals", ("telix", "tlx stock", "tlx shares")),
    "BHP.AX": ("BHP Group", ("bhp", "bhp stock")),
    "CSL.AX": ("CSL Limited", ("csl", "csl stock")),
    "FMG.AX": ("Fortescue", ("fortescue", "fmg stock")),
    "WDS.AX": ("Woodside Energy", ("woodside", "wds stock")),
    "XRO.AX": ("Xero", ("xero", "xro stock")),
}


CN_TICKER_NAMES: dict[str, str] = {
    "600519.SS": "贵州茅台",
    "000858.SZ": "五粮液",
    "600036.SS": "招商银行",
    "601318.SS": "中国平安",
    "300750.SZ": "宁德时代",
    "002594.SZ": "比亚迪",
    "600900.SS": "长江电力",
    "000333.SZ": "美的集团",
    "601012.SS": "隆基绿能",
    "688981.SS": "中芯国际",
    "002402.SZ": "和而泰",
    "600406.SS": "国电南瑞",
    "002065.SZ": "东华软件",
}


def _ticker_display_name(ticker: str) -> str:
    """Resolve a human-readable label; A-shares prefer configured Chinese names."""
    holdings = load_config().get("holdings", {})
    holding_name = str((holdings.get(ticker) or {}).get("name", "") or "").strip()
    if holding_name:
        return holding_name
    cn_name = CN_TICKER_NAMES.get(ticker, "").strip()
    if cn_name:
        return cn_name
    news_entry = NEWS_QUERIES.get(ticker)
    if news_entry:
        return news_entry[0]
    return ""


@dataclass(frozen=True)
class StockSnapshot:
    ticker: str
    price: float
    currency: str
    change_pct: float
    week_52_low: float
    week_52_high: float
    week_52_position: float
    rsi_14: float
    sma_50: float
    sma_200: float
    atr_14: float
    headlines: tuple[str, ...]
    headline_links: tuple[str, ...] = ()
    momentum_20d: float = 0.0
    momentum_60d: float = 0.0
    volume_ratio: float = 1.0
    volatility_20d: float = 0.0
    sma_20: float = 0.0


@dataclass(frozen=True)
class Recommendation:
    ticker: str
    action: Action
    score: float
    stars: int
    buy_low: float
    buy_high: float
    target_price: float
    stop_loss: float
    reasons: tuple[str, ...]
    snapshot: StockSnapshot
    name: str = ""
    strategy: str = ""
    alphasift_rank: int | None = None


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Return RSI using Wilder-style exponential smoothing."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    relative_strength = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + relative_strength))
    return rsi.mask((avg_loss == 0) & (avg_gain > 0), 100).fillna(50)


def calculate_atr(history: pd.DataFrame, period: int = 14) -> float:
    high = history["High"]
    low = history["Low"]
    close = history["Close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    value = float(atr.iloc[-1]) if len(atr.dropna()) else 0.0
    return value if value > 0 else max(float((high - low).tail(period).mean()), 0.01)


def _news_value(article: dict[str, Any], key: str) -> Any:
    content = article.get("content")
    if isinstance(content, dict) and key in content:
        return content[key]
    return article.get(key)


def _news_url(article: dict[str, Any]) -> str:
    for key in ("canonicalUrl", "clickThroughUrl"):
        value = _news_value(article, key)
        if isinstance(value, dict) and value.get("url"):
            return str(value["url"])
    return str(_news_value(article, "link") or "")


def fetch_headlines(ticker: str, limit: int = 1) -> tuple[tuple[str, str], ...]:
    """Fetch Yahoo Finance headlines as (title, url) pairs without failing the report."""
    query_pack = NEWS_QUERIES.get(ticker)
    if not query_pack:
        return ()
    query, aliases = query_pack
    try:
        articles = yf.Search(
            query,
            max_results=1,
            news_count=max(limit * 4, 8),
            lists_count=0,
            include_nav_links=False,
            include_research=False,
            raise_errors=False,
        ).news
    except Exception as exc:
        print(f"Warning: news fetch failed for {ticker}: {exc}", file=sys.stderr)
        return ()

    headlines: list[tuple[str, str]] = []
    seen: set[str] = set()
    for article in articles or []:
        title = str(_news_value(article, "title") or "").strip()
        if not title or title.casefold() in seen:
            continue
        summary = str(_news_value(article, "summary") or "")
        searchable = f"{title} {summary}".casefold()
        if not any(alias in searchable for alias in aliases):
            continue
        seen.add(title.casefold())
        headlines.append((title, _news_url(article)))
        if len(headlines) == limit:
            break
    return tuple(headlines)


def _default_currency(ticker: str) -> str:
    if ticker.endswith(".SS") or ticker.endswith(".SZ"):
        return "CNY"
    if ticker.endswith(".AX"):
        return "AUD"
    return "USD"


def fetch_snapshot(ticker: str) -> StockSnapshot:
    stock = yf.Ticker(ticker)
    history = stock.history(period="2y", interval="1d", auto_adjust=True)
    close = history.get("Close", pd.Series(dtype=float)).dropna()
    if len(close) < 200:
        raise ValueError(f"only {len(close)} daily closes available; 200 required")

    latest = float(close.iloc[-1])
    previous = float(close.iloc[-2])
    year = history.loc[close.tail(252).index]
    year_low = float(year["Low"].min())
    year_high = float(year["High"].max())
    range_size = year_high - year_low
    position = 50.0 if range_size == 0 else (latest - year_low) / range_size * 100

    try:
        currency = str(stock.fast_info.get("currency") or "")
    except Exception:
        currency = ""
    if not currency:
        currency = _default_currency(ticker)

    momentum_20d = (latest / float(close.iloc[-21]) - 1) * 100 if len(close) > 21 else 0.0
    momentum_60d = (latest / float(close.iloc[-61]) - 1) * 100 if len(close) > 61 else 0.0
    volume = history.get("Volume", pd.Series(dtype=float)).dropna()
    volume_ratio = 1.0
    if len(volume) >= 20:
        avg_20 = float(volume.tail(20).mean())
        if avg_20 > 0:
            volume_ratio = float(volume.tail(5).mean()) / avg_20
    returns = close.pct_change().dropna()
    volatility_20d = float(returns.tail(20).std() * 100) if len(returns) >= 20 else 0.0
    news_items = fetch_headlines(ticker)

    return StockSnapshot(
        ticker=ticker,
        price=latest,
        currency=currency,
        change_pct=(latest / previous - 1) * 100,
        week_52_low=year_low,
        week_52_high=year_high,
        week_52_position=max(0.0, min(position, 100.0)),
        rsi_14=float(calculate_rsi(close).iloc[-1]),
        sma_50=float(close.tail(50).mean()),
        sma_200=float(close.tail(200).mean()),
        sma_20=float(close.tail(20).mean()),
        atr_14=calculate_atr(history),
        headlines=tuple(title for title, _ in news_items),
        headline_links=tuple(url for _, url in news_items),
        momentum_20d=momentum_20d,
        momentum_60d=momentum_60d,
        volume_ratio=volume_ratio,
        volatility_20d=volatility_20d,
    )


def _trend_text(snapshot: StockSnapshot) -> str:
    if snapshot.price > snapshot.sma_50 > snapshot.sma_200:
        return "多头排列"
    if snapshot.price < snapshot.sma_50 < snapshot.sma_200:
        return "空头排列"
    return "均线交错"


def _score_snapshot(snapshot: StockSnapshot) -> tuple[float, list[str]]:
    score = 50.0
    reasons: list[str] = []

    if snapshot.price > snapshot.sma_50 > snapshot.sma_200:
        score += 18
        reasons.append("中期趋势向上，均线多头排列")
    elif snapshot.price < snapshot.sma_50 < snapshot.sma_200:
        score -= 18
        reasons.append("中期趋势偏弱，均线空头排列")
    else:
        reasons.append("均线纠缠，方向待确认")

    if 45 <= snapshot.rsi_14 <= 62:
        score += 12
        reasons.append(f"RSI {snapshot.rsi_14:.0f} 处于健康区间")
    elif snapshot.rsi_14 < 30:
        score += 8
        reasons.append(f"RSI {snapshot.rsi_14:.0f} 超卖，存在反弹空间")
    elif snapshot.rsi_14 > 72:
        score -= 12
        reasons.append(f"RSI {snapshot.rsi_14:.0f} 偏热，追高风险上升")
    elif snapshot.rsi_14 > 65:
        score -= 5
        reasons.append(f"RSI {snapshot.rsi_14:.0f} 略偏强")

    if 25 <= snapshot.week_52_position <= 65:
        score += 10
        reasons.append("52周位置适中，上涨空间与安全边际较均衡")
    elif snapshot.week_52_position < 20:
        score += 4
        reasons.append("接近52周低位，需确认基本面未恶化")
    elif snapshot.week_52_position > 88:
        score -= 10
        reasons.append("接近52周高位，获利盘压力较大")

    if 0 < snapshot.change_pct <= 2.5:
        score += 5
    elif snapshot.change_pct < -2 and snapshot.rsi_14 < 45:
        score += 8
        reasons.append("短线回调且未超买，适合等待低吸")
    elif snapshot.change_pct > 4:
        score -= 6
        reasons.append("单日涨幅偏大，不宜追高")

    if snapshot.price > snapshot.sma_50 * 0.98:
        score += 4
    elif snapshot.price < snapshot.sma_200:
        score -= 6

    return max(0.0, min(score, 100.0)), reasons[:3]


def _action_from_score(score: float) -> Action:
    thresholds = get_thresholds()
    if score >= thresholds["buy"]:
        return "买入"
    if score >= thresholds["watch"]:
        return "逢低关注"
    if score >= thresholds["hold"]:
        return "观望"
    if score >= thresholds["reduce"]:
        return "减仓"
    return "回避"


def _stars_from_score(score: float) -> int:
    thresholds = get_thresholds()
    if score >= thresholds["buy"] + 8:
        return 5
    if score >= thresholds["buy"]:
        return 4
    if score >= thresholds["watch"]:
        return 3
    if score >= thresholds["hold"]:
        return 2
    return 1


def _price_levels(snapshot: StockSnapshot, action: Action) -> tuple[float, float, float, float]:
    """Intraday-executable levels: the buy zone hugs today's price.

    The anchor is the nearer of the 20-day SMA and (price - 1 ATR), so the
    zone always sits within roughly 1.5 ATR below the latest close instead of
    drifting down to deep-pullback levels that may never trade today.
    """
    params = get_price_level_params()
    atr = snapshot.atr_14
    near_support = max(snapshot.sma_20, snapshot.price - atr)
    buy_anchor = min(snapshot.price, near_support)
    buy_high = min(snapshot.price, buy_anchor + atr * params["buy_high_atr"])
    buy_low = buy_high - atr * params["buy_low_atr"]

    if action in ("买入", "逢低关注"):
        target = snapshot.price + atr * params["target_atr"]
        target = min(target, snapshot.week_52_high * 1.02)
    else:
        target = snapshot.price + atr * params["target_atr_neutral"]
    target = max(target, buy_high + atr * 0.5)

    # Stop is anchored to the buy zone: stop_atr ATRs below entry, but the
    # max loss from buy_low is capped by stop_max_drawdown_pct.
    stop = max(
        buy_low - atr * params["stop_atr"],
        buy_low * (1 - params["stop_max_drawdown_pct"]),
    )

    return buy_low, buy_high, target, stop


def build_recommendation(snapshot: StockSnapshot) -> Recommendation:
    score, reasons = _score_snapshot(snapshot)
    action = _action_from_score(score)
    buy_low, buy_high, target, stop = _price_levels(snapshot, action)
    return Recommendation(
        ticker=snapshot.ticker,
        action=action,
        score=round(score, 1),
        stars=_stars_from_score(score),
        buy_low=round(buy_low, 2),
        buy_high=round(buy_high, 2),
        target_price=round(target, 2),
        stop_loss=round(stop, 2),
        reasons=tuple(reasons),
        snapshot=snapshot,
        name=_ticker_display_name(snapshot.ticker),
    )


def _apply_quant_overlay(
    recommendations: list[Recommendation],
    *,
    factor_weights: dict[str, float] | None = None,
    strategy: str = "",
) -> list[Recommendation]:
    """Blend rule scores with cross-sectional multi-factor quant scores."""
    from quant_factors import cross_sectional_scores, strategy_factor_weights

    params = get_quant_params()
    if not params.get("enabled", True):
        return recommendations
    weights = factor_weights or strategy_factor_weights(strategy) if strategy else None
    if weights is None:
        weights = {key: float(value) for key, value in params.get("factor_weights", {}).items()}
    quant_scores = cross_sectional_scores([rec.snapshot for rec in recommendations], weights)
    if not quant_scores:
        return recommendations

    rule_weight = float(params.get("rule_weight", 0.6))
    quant_weight = float(params.get("quant_weight", 0.4))
    total = rule_weight + quant_weight or 1.0

    blended_recs: list[Recommendation] = []
    for rec in recommendations:
        entry = quant_scores.get(rec.ticker)
        if entry is None:
            blended_recs.append(rec)
            continue
        quant_score, dominant = entry
        blended = max(0.0, min((rule_weight * rec.score + quant_weight * quant_score) / total, 100.0))
        action = _action_from_score(blended)
        buy_low, buy_high, target, stop = _price_levels(rec.snapshot, action)
        reasons = rec.reasons + (f"量化因子 {quant_score:.0f}分（{dominant}）",)
        blended_recs.append(
            replace(
                rec,
                score=round(blended, 1),
                action=action,
                stars=_stars_from_score(blended),
                buy_low=round(buy_low, 2),
                buy_high=round(buy_high, 2),
                target_price=round(target, 2),
                stop_loss=round(stop, 2),
                reasons=reasons[:4],
                strategy=strategy or rec.strategy,
            )
        )
    return blended_recs


def _market_quant_strategy(market_key: str) -> str:
    market = load_config().get("markets", {}).get(market_key, {})
    quant_screen = market.get("quant_screen", {})
    if quant_screen.get("strategy"):
        return str(quant_screen["strategy"])
    if market_key == "CN":
        return str(_cn_alphasift_config().get("strategy", "volume_breakout"))
    tuning = get_market_tuning(market_key)
    return str(tuning.get("quant_strategy", "volume_breakout"))


def _market_section_note(market_key: str, extras: dict[str, Any]) -> str:
    if market_key == "CN":
        return _cn_section_note(extras)
    from alphasift_cn import strategy_display_name

    quant = extras.get("quant_screen", {})
    if not quant:
        return ""
    strategy = quant.get("strategy", "volume_breakout")
    strategy_label = strategy_display_name(strategy)
    count = quant.get("watchlist_count", 0)
    return (
        f"数据来源：Yahoo Finance 观察池（{count} 只），策略 {strategy_label}/{strategy} 截面量化打分；"
        f"买卖价与技术面同 A 股逻辑。"
    )


def _money(value: float, currency: str) -> str:
    symbol = {"USD": "$", "AUD": "A$", "CNY": "¥"}.get(currency, "")
    if symbol:
        return f"{symbol}{value:.2f}"
    return f"{value:.2f} {currency}"


def _stars_text(count: int) -> str:
    return "★" * count + "☆" * (5 - count)


def _display_ticker(rec: Recommendation) -> str:
    if rec.name:
        return f"{rec.name} ({rec.ticker})"
    return rec.ticker


def _headline_markdown(snap: StockSnapshot) -> str:
    if not snap.headlines:
        return "暂无重点新闻"
    title = snap.headlines[0]
    url = snap.headline_links[0] if snap.headline_links else ""
    return f"[{title}]({url})" if url else title


def format_pick(rank: int, rec: Recommendation) -> str:
    snap = rec.snapshot
    sign = "+" if snap.change_pct >= 0 else ""
    headline = _headline_markdown(snap)
    reason = " · ".join(rec.reasons)
    strategy_note = f" · 策略 {rec.strategy}" if rec.strategy else ""
    return (
        f"### {rank}. {_display_ticker(rec)} · {rec.action} "
        f"{_stars_text(rec.stars)} ({rec.score:.0f}分{strategy_note})\n\n"
        f"| 项目 | 数值 |\n"
        f"| --- | --- |\n"
        f"| 现价 | {_money(snap.price, snap.currency)} ({sign}{snap.change_pct:.2f}%) |\n"
        f"| 建议买入 | {_money(rec.buy_low, snap.currency)} ~ {_money(rec.buy_high, snap.currency)} |\n"
        f"| 目标卖出 | {_money(rec.target_price, snap.currency)} |\n"
        f"| 止损参考 | {_money(rec.stop_loss, snap.currency)} |\n\n"
        f"**技术面**：{_trend_text(snap)} · RSI {snap.rsi_14:.0f} · 52周位置 {snap.week_52_position:.0f}%\n\n"
        f"**逻辑**：{reason}\n\n"
        f"**新闻**：{headline}"
    )


def format_compact(rec: Recommendation) -> str:
    snap = rec.snapshot
    sign = "+" if snap.change_pct >= 0 else ""
    return (
        f"- **{_display_ticker(rec)}** {rec.action} ({rec.score:.0f}分) · "
        f"{_money(snap.price, snap.currency)} ({sign}{snap.change_pct:.2f}%) · "
        f"买 {_money(rec.buy_low, snap.currency)}~{_money(rec.buy_high, snap.currency)} · "
        f"卖 {_money(rec.target_price, snap.currency)}"
    )


def _market_section_lines(
    market_key: str,
    picks: list[Recommendation],
    others: list[Recommendation],
    errors: dict[str, str],
    section_note: str = "",
) -> list[str]:
    config = load_config()
    market = config["markets"][market_key]
    lines = [
        f"## {market['emoji']} {market['label']}",
        "",
    ]
    if section_note:
        lines.extend([f"> {section_note}", ""])
    lines.extend(
        [
            "### 今日首选操作",
            "",
        ]
    )

    if picks:
        for index, rec in enumerate(picks, start=1):
            lines.append(format_pick(index, rec))
            lines.append("")
            lines.append("---")
            lines.append("")
    else:
        lines.append("_今日暂无达到买入/关注阈值的标的，建议观望或等待更好价格。_")
        lines.append("")
        lines.append("---")
        lines.append("")

    if others:
        lines.extend(["### 观察池其余标的", ""])
        lines.extend(format_compact(rec) for rec in others)
        lines.append("")

    if errors:
        lines.extend(["### 数据异常", ""])
        for ticker, error in errors.items():
            lines.append(f"- {ticker}：{error}")
        lines.append("")

    return lines


def build_market_report(
    market_key: str,
    picks: list[Recommendation],
    others: list[Recommendation],
    errors: dict[str, str],
    now: datetime | None = None,
    section_note: str = "",
) -> str:
    config = load_config()
    market = config["markets"][market_key]
    report_time = (now or datetime.now(SYDNEY)).astimezone(SYDNEY)
    lines = [
        f"# {market['emoji']} {market['label']}每日投资简报",
        f"**{report_time:%Y-%m-%d %H:%M}** 悉尼时间",
        "",
        "> 基于技术面自动评分，从观察池筛选今日优先操作标的。仅供研究，不构成投资建议。",
        "",
        "---",
        "",
    ]
    lines.extend(_market_section_lines(market_key, picks, others, errors, section_note))
    lines.append("**提示**：优先在建议买入区间内分批建仓；触及止损参考位需重新评估。")
    return "\n".join(lines)


def _cn_alphasift_config() -> dict[str, Any]:
    base = load_config().get("markets", {}).get("CN", {}).get("alphasift", {})
    overrides = get_market_tuning("CN")
    merged = dict(base)
    if overrides.get("alphasift_strategy"):
        merged["strategy"] = overrides["alphasift_strategy"]
    if overrides.get("score_blend"):
        merged["score_blend"] = overrides["score_blend"]
    return merged


def _cn_alphasift_enabled() -> bool:
    return bool(_cn_alphasift_config().get("enabled", False))


def _enrich_with_alphasift(
    technical: Recommendation,
    candidate: Any,
    alphasift_config: dict[str, Any],
) -> Recommendation:
    from alphasift_cn import blend_scores, build_screen_reasons

    blended = blend_scores(candidate.final_score, technical.score, alphasift_config)
    action = _action_from_score(blended)
    buy_low, buy_high, target, stop = _price_levels(technical.snapshot, action)
    screen_reasons = build_screen_reasons(candidate)
    reasons = tuple((screen_reasons + technical.reasons)[:4])
    return Recommendation(
        ticker=technical.ticker,
        action=action,
        score=round(blended, 1),
        stars=_stars_from_score(blended),
        buy_low=round(buy_low, 2),
        buy_high=round(buy_high, 2),
        target_price=round(target, 2),
        stop_loss=round(stop, 2),
        reasons=reasons,
        snapshot=technical.snapshot,
        name=candidate.name,
        strategy=str(alphasift_config.get("strategy", "")),
        alphasift_rank=candidate.rank,
    )


def _regime_section_note(extras: dict[str, Any]) -> str:
    regime = extras.get("regime")
    if not regime:
        return ""
    return f"大盘环境：{regime.get('summary', '')}。{regime.get('stance', '')}"


def _cn_section_note(extras: dict[str, Any]) -> str:
    from alphasift_cn import strategy_display_name

    meta = extras.get("alphasift")
    if not meta:
        return ""
    strategy = meta.get("strategy", "volume_breakout")
    strategy_label = strategy_display_name(strategy)
    snapshot_count = meta.get("snapshot_count", 0)
    after_filter = meta.get("after_filter_count", 0)
    pick_count = meta.get("pick_count", 0)
    source = meta.get("snapshot_source", "akshare")
    diversify = meta.get("diversify", {})
    diversify_note = ""
    if diversify.get("enabled"):
        skipped = diversify.get("skipped_count", 0)
        diversify_note = f" 行业分散已启用（金融股最多 1 只，跳过 {skipped} 只重复行业）。"
    return (
        f"数据来源：alphasift 全市场筛选（{source} 快照，策略 {strategy_label}/{strategy}），"
        f"快照 {snapshot_count} 只 → 硬筛后 {after_filter} 只 → 入选 {pick_count} 只；"
        f"买卖价与技术面来自 Yahoo Finance。{diversify_note}"
    )


def scan_cn_market(
    regime: MarketRegime | None = None,
) -> tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]:
    from alphasift_cn import (
        alphasift_import_error,
        diversify_candidates,
        is_alphasift_available,
        run_alphasift_screen,
    )

    config = load_config()["markets"]["CN"]
    alphasift_config = _cn_alphasift_config()
    top_n = int(config.get("top_n", 3))
    fallback_watchlist = list(config.get("watchlist", []))
    extras: dict[str, Any] = {}
    if regime:
        extras["regime"] = regime_to_dict(regime)
    errors: dict[str, str] = {}
    candidates = []

    if regime:
        regime_ctx = regime_context_for_alphasift({"CN": regime})
        base_context = str(alphasift_config.get("context", "") or "").strip()
        alphasift_config = dict(alphasift_config)
        alphasift_config["context"] = f"{base_context} {regime_ctx}".strip()

    if alphasift_config.get("enabled", False):
        if not is_alphasift_available():
            message = alphasift_import_error() or "alphasift package not installed"
            errors["alphasift"] = message
            print(f"Warning: {message}", file=sys.stderr)
        else:
            try:
                candidates, extras["alphasift"] = run_alphasift_screen(alphasift_config)
                candidates, diversify_meta = diversify_candidates(candidates, alphasift_config)
                extras["alphasift"]["diversify"] = diversify_meta
                extras["alphasift"]["pick_count"] = len(candidates)
            except Exception as exc:
                errors["alphasift"] = str(exc)
                print(f"Warning: alphasift screen failed: {exc}", file=sys.stderr)

    tickers: list[str] = []
    candidate_by_ticker: dict[str, Any] = {}
    for candidate in candidates:
        if candidate.yahoo_ticker in candidate_by_ticker:
            continue
        tickers.append(candidate.yahoo_ticker)
        candidate_by_ticker[candidate.yahoo_ticker] = candidate

    if not tickers and alphasift_config.get("fallback_to_watchlist", True):
        tickers = list(fallback_watchlist)
        print("Warning: using static CN watchlist fallback.", file=sys.stderr)
    elif alphasift_config.get("merge_fallback_watchlist", False):
        for ticker in fallback_watchlist:
            if ticker not in tickers:
                tickers.append(ticker)

    recommendations: list[Recommendation] = []
    for ticker in tickers:
        try:
            technical = build_recommendation(fetch_snapshot(ticker))
            if ticker in candidate_by_ticker:
                recommendations.append(
                    _enrich_with_alphasift(
                        technical,
                        candidate_by_ticker[ticker],
                        alphasift_config,
                    )
                )
            else:
                recommendations.append(technical)
        except Exception as exc:
            print(f"Warning: data fetch failed for {ticker}: {exc}", file=sys.stderr)
            errors[ticker] = str(exc)

    recommendations = _apply_quant_overlay(
        recommendations,
        strategy=_market_quant_strategy("CN"),
    )
    ranked = sorted(
        recommendations,
        key=lambda item: (item.alphasift_rank or 999, -item.score),
    )
    picks, others = select_picks_with_regime(ranked, top_n, regime)
    return picks, others, errors, extras


HOLDING_ADVICE = {
    "买入": "可加仓",
    "逢低关注": "持有，回调到买入区间可加仓",
    "观望": "持有观望，暂不操作",
    "减仓": "建议减仓",
    "回避": "建议止盈/离场",
}


def _holding_today_action(rec: Recommendation, regime: MarketRegime | None = None) -> str:
    snap = rec.snapshot
    currency = snap.currency
    buy_zone = f"{_money(rec.buy_low, currency)} ~ {_money(rec.buy_high, currency)}"
    target = _money(rec.target_price, currency)
    stop = _money(rec.stop_loss, currency)
    regime_caution = ""
    if regime and regime.label == "弱势":
        regime_caution = "（大盘偏弱，轻仓）"

    if rec.action in ("买入", "逢低关注"):
        if snap.price <= rec.buy_high:
            return f"今日可挂单买入 {buy_zone}{regime_caution}"
        return f"现价偏高，等回踩 {buy_zone} 再动手"
    if rec.action == "观望":
        return "今日持有不动，不加仓不减仓"
    if rec.action == "减仓":
        return f"今日可考虑减仓，反弹至 {target} 附近分批卖出"
    return f"今日建议止盈/离场，目标 {target}，跌破 {stop} 果断处理"


def scan_holdings(
    regimes: dict[str, MarketRegime] | None = None,
) -> tuple[list[Recommendation], dict[str, str]]:
    """Analyze configured holdings with quant strategy per market."""
    from quant_factors import strategy_factor_weights

    holdings = load_config().get("holdings", {})
    grouped: dict[str, list[tuple[str, dict[str, Any]]]] = {key: [] for key in MARKET_ORDER}
    for ticker, info in holdings.items():
        market_key = str((info or {}).get("market") or _holding_market(ticker))
        grouped.setdefault(market_key, []).append((ticker, info or {}))

    recommendations: list[Recommendation] = []
    errors: dict[str, str] = {}
    for market_key in MARKET_ORDER:
        for ticker, info in grouped.get(market_key, []):
            try:
                rec = build_recommendation(fetch_snapshot(ticker))
                name = str(info.get("name", "") or "")
                if name:
                    rec = replace(rec, name=name)
                recommendations.append(rec)
            except Exception as exc:
                print(f"Warning: holding fetch failed for {ticker}: {exc}", file=sys.stderr)
                errors[ticker] = str(exc)

        market_recs = [rec for rec in recommendations if _holding_market(rec.ticker) == market_key]
        if len(market_recs) < 2:
            continue
        strategy = _market_quant_strategy(market_key)
        enriched = _apply_quant_overlay(
            market_recs,
            factor_weights=strategy_factor_weights(strategy),
            strategy=strategy,
        )
        enriched_by_ticker = {rec.ticker: rec for rec in enriched}
        recommendations = [
            enriched_by_ticker.get(rec.ticker, rec) if _holding_market(rec.ticker) == market_key else rec
            for rec in recommendations
        ]

    recommendations.sort(key=lambda item: item.score, reverse=True)
    return recommendations, errors


def _holding_market(ticker: str) -> str:
    if ticker.endswith(".SS") or ticker.endswith(".SZ"):
        return "CN"
    if ticker.endswith(".AX"):
        return "AU"
    return "US"


_HOLDING_STATUS_ICON = {
    "买入": "🟢",
    "逢低关注": "🟢",
    "观望": "🟡",
    "减仓": "🔴",
    "回避": "🔴",
}


def format_holdings_section(
    recommendations: list[Recommendation],
    errors: dict[str, str],
    regimes: dict[str, MarketRegime] | None = None,
) -> list[str]:
    lines = [
        "## 💼 持仓今日操作指南",
        "",
        "> **核心板块**：以下为你当前持仓的今日操作建议，买入区间为当日可挂单价位。",
        "",
    ]
    group_titles = {"US": "美股", "CN": "A股", "AU": "澳股"}
    for market_key in MARKET_ORDER:
        group = [rec for rec in recommendations if _holding_market(rec.ticker) == market_key]
        if not group:
            continue
        lines.append(f"**{group_titles.get(market_key, market_key)}**")
        lines.append("")
        regime = (regimes or {}).get(market_key)
        for rec in group:
            snap = rec.snapshot
            sign = "+" if snap.change_pct >= 0 else ""
            icon = _HOLDING_STATUS_ICON.get(rec.action, "🟡")
            advice = HOLDING_ADVICE.get(rec.action, rec.action)
            currency = snap.currency
            today_action = _holding_today_action(rec, regime)
            lines.append(
                f"- {icon} **{_display_ticker(rec)}** "
                f"{_money(snap.price, currency)} ({sign}{snap.change_pct:.2f}%) · {rec.score:.0f}分 · "
                f"**{advice}**"
            )
            lines.append(f"  　**今日操作**：{today_action}")
            lines.append(
                f"  　买入区间 {_money(rec.buy_low, currency)}~{_money(rec.buy_high, currency)} · "
                f"目标 {_money(rec.target_price, currency)} · "
                f"止损 {_money(rec.stop_loss, currency)}"
            )
        lines.append("")
    if errors:
        for ticker, error in errors.items():
            lines.append(f"- ⚠️ {ticker} 数据获取失败：{error}")
        lines.append("")
    return lines


def build_holdings_report(now: datetime | None = None) -> str:
    report_time = (now or datetime.now(SYDNEY)).astimezone(SYDNEY)
    regimes = fetch_all_regimes()
    recommendations, errors = scan_holdings(regimes=regimes)
    lines = [
        "# 💼 持仓今日操作指南",
        f"**{report_time:%Y-%m-%d %H:%M}** 悉尼时间",
        "",
        "> 基于放量突破量化策略 + 技术面，评估你当前持仓的今日可执行操作。仅供研究，不构成投资建议。",
        "",
    ]
    if regimes:
        lines.append(format_regime_overview(regimes))
        lines.append("---")
        lines.append("")
    lines.extend(format_holdings_section(recommendations, errors, regimes=regimes))
    return "\n".join(lines)


def _merge_markets_enabled() -> bool:
    return bool(_notification_settings().get("merge_markets", True))


def _combined_report_title() -> str:
    return str(_notification_settings().get("combined_title", "每日全球投资简报"))


def build_combined_report(
    market_reports: dict[str, tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]],
    now: datetime | None = None,
    regimes: dict[str, MarketRegime] | None = None,
    holdings: tuple[list[Recommendation], dict[str, str]] | None = None,
    social: Any | None = None,
    serenity: Any | None = None,
    potential: tuple[list[Any], dict[str, str]] | None = None,
    research: list[Any] | None = None,
) -> str:
    from morning_brief import compose_morning_brief

    return compose_morning_brief(
        market_reports,
        now=now,
        regimes=regimes,
        holdings=holdings,
        social=social,
        serenity=serenity,
        potential=potential,
        research=research,
    )


def scan_market(
    market_key: str,
    regime: MarketRegime | None = None,
) -> tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]:
    if regime is None:
        regime = fetch_market_regime(market_key)

    if market_key == "CN" and _cn_alphasift_enabled():
        return scan_cn_market(regime)

    config = load_config()
    market = config["markets"][market_key]
    watchlist = market["watchlist"]
    top_n = int(market.get("top_n", 3))
    strategy = _market_quant_strategy(market_key)
    extras: dict[str, Any] = {
        "quant_screen": {
            "strategy": strategy,
            "watchlist_count": len(watchlist),
        }
    }
    if regime:
        extras["regime"] = regime_to_dict(regime)

    recommendations: list[Recommendation] = []
    errors: dict[str, str] = {}
    for ticker in watchlist:
        try:
            recommendations.append(build_recommendation(fetch_snapshot(ticker)))
        except Exception as exc:
            print(f"Warning: data fetch failed for {ticker}: {exc}", file=sys.stderr)
            errors[ticker] = str(exc)

    from quant_factors import strategy_factor_weights

    recommendations = _apply_quant_overlay(
        recommendations,
        factor_weights=strategy_factor_weights(strategy),
        strategy=strategy,
    )
    ranked = sorted(recommendations, key=lambda item: item.score, reverse=True)
    picks, others = select_picks_with_regime(ranked, top_n, regime)
    return picks, others, errors, extras


def prediction_record(rec: Recommendation) -> dict[str, Any]:
    snap = rec.snapshot
    record = {
        "ticker": rec.ticker,
        "action": rec.action,
        "score": rec.score,
        "price_at_signal": snap.price,
        "currency": snap.currency,
        "buy_low": rec.buy_low,
        "buy_high": rec.buy_high,
        "target_price": rec.target_price,
        "stop_loss": rec.stop_loss,
    }
    if rec.name:
        record["name"] = rec.name
    if rec.strategy:
        record["strategy"] = rec.strategy
    if rec.alphasift_rank is not None:
        record["alphasift_rank"] = rec.alphasift_rank
    return record


def _summarize_graded(graded: list[dict[str, Any]]) -> dict[str, Any]:
    if not graded:
        return {}
    scores = [item["score"] for item in graded]
    count = len(graded)
    return {
        "count": count,
        "average_score": round(sum(scores) / count, 1),
        "hit_rate": round(sum(1 for item in graded if item["score"] >= 60) / count, 3),
        "direction_rate": round(
            sum(1 for item in graded if "方向判断正确" in item["notes"]) / count,
            3,
        ),
        "target_rate": round(sum(1 for item in graded if item["target_hit"]) / count, 3),
        "stop_rate": round(sum(1 for item in graded if item["stop_hit"]) / count, 3),
        "details": graded,
    }


def _grade_records(
    records: list[dict[str, Any]],
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    graded: list[dict[str, Any]] = []
    for record in records:
        price_range = _fetch_price_range(record["ticker"], start, end)
        if not price_range:
            continue
        last_close, low, high = price_range
        graded.append(_grade_prediction(record, last_close, low, high))
    return graded


def _format_graded_table(graded: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| 标的 | 动作 | 信号价 | 现价 | 涨跌 | 得分 | 备注 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    record_by_ticker = {record["ticker"]: record for record in records}
    for result in graded:
        record = record_by_ticker.get(result["ticker"], {})
        name = record.get("name")
        label = f"{name} ({result['ticker']})" if name else result["ticker"]
        notes = "；".join(result["notes"])
        lines.append(
            f"| {label} | {result['action']} | "
            f"{result['signal_price']:.2f} | {result['last_close']:.2f} | "
            f"{result['return_pct']:+.2f}% | {result['score']:.0f} | {notes} |"
        )
    return lines


def _holdings_prediction_records(
    recommendations: list[Recommendation],
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for rec in recommendations:
        market_key = _holding_market(rec.ticker)
        record = prediction_record(rec)
        record["market"] = market_key
        grouped.setdefault(market_key, []).append(record)
    return grouped


def save_predictions(
    market_reports: dict[str, tuple[list[Recommendation], list[Recommendation], dict[str, Any]]],
    holdings: dict[str, list[dict[str, Any]]] | None = None,
    now: datetime | None = None,
) -> Path:
    report_time = (now or datetime.now(SYDNEY)).astimezone(SYDNEY)
    date_key = report_time.strftime("%Y-%m-%d")
    payload: dict[str, Any] = {
        "date": date_key,
        "generated_at": report_time.isoformat(),
        "markets": {},
    }
    if holdings:
        payload["holdings"] = holdings
    for market_key, (picks, others, extras) in market_reports.items():
        block: dict[str, Any] = {
            "picks": [prediction_record(rec) for rec in picks],
            "watchlist": [prediction_record(rec) for rec in others],
        }
        if extras.get("alphasift"):
            block["alphasift"] = extras["alphasift"]
        payload["markets"][market_key] = block

    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = PREDICTIONS_DIR / f"{date_key}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _fetch_price_range(ticker: str, start: datetime, end: datetime) -> tuple[float, float, float] | None:
    history = yf.Ticker(ticker).history(
        start=start.strftime("%Y-%m-%d"),
        end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=True,
    )
    if history.empty:
        return None
    close = history["Close"].dropna()
    if close.empty:
        return None
    return float(close.iloc[-1]), float(history["Low"].min()), float(history["High"].max())


def _grade_prediction(record: dict[str, Any], last_close: float, low: float, high: float) -> dict[str, Any]:
    signal_price = float(record["price_at_signal"])
    action = record["action"]
    direction = last_close / signal_price - 1

    bullish = action in ("买入", "逢低关注")
    direction_hit = (direction > 0) if bullish else (direction <= 0)

    buy_zone_hit = low <= float(record["buy_high"])
    target_hit = high >= float(record["target_price"])
    stop_hit = low <= float(record["stop_loss"])

    points = 0.0
    notes: list[str] = []
    if direction_hit:
        points += 40
        notes.append("方向判断正确")
    else:
        notes.append("方向判断错误")

    if bullish and buy_zone_hit:
        points += 20
        notes.append("触及建议买入区间")
    if bullish and target_hit:
        points += 30
        notes.append("达到目标卖出价")
    if stop_hit:
        points -= 25
        notes.append("触及止损参考位")

    points = max(0.0, min(points, 100.0))
    return {
        "ticker": record["ticker"],
        "action": action,
        "signal_price": signal_price,
        "last_close": round(last_close, 2),
        "return_pct": round(direction * 100, 2),
        "buy_zone_hit": buy_zone_hit,
        "target_hit": target_hit,
        "stop_hit": stop_hit,
        "score": round(points, 1),
        "notes": notes,
    }


def review_predictions(
    horizons: list[int] | None = None,
    now: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    config = load_config()
    review_cfg = config.get("review", {})
    default_horizons = review_cfg.get("horizons_days") or config.get("review_horizons_days", [5])
    horizons = horizons or list(default_horizons)
    report_time = (now or datetime.now(SYDNEY)).astimezone(SYDNEY)
    review_payload: dict[str, Any] = {
        "reviewed_at": report_time.isoformat(),
        "horizons": {},
    }

    lines = [
        "# 📊 推荐复盘打分",
        f"**{report_time:%Y-%m-%d %H:%M}** 悉尼时间",
        "",
        "> 周度复盘，默认评估 T+5（约一周前推送）表现。",
        "",
    ]

    for horizon in horizons:
        signal_date = (report_time - timedelta(days=horizon)).strftime("%Y-%m-%d")
        path = PREDICTIONS_DIR / f"{signal_date}.json"
        if not path.exists():
            lines.append(f"## T+{horizon}（{signal_date}）")
            lines.append("")
            lines.append(f"_未找到 {signal_date} 的推送记录，跳过。_")
            lines.append("")
            continue

        payload = json.loads(path.read_text(encoding="utf-8"))
        start = datetime.strptime(signal_date, "%Y-%m-%d").replace(tzinfo=SYDNEY)
        end = report_time
        horizon_result: dict[str, Any] = {
            "signal_date": signal_date,
            "markets": {},
            "holdings": {},
        }
        lines.extend([f"## T+{horizon}（{signal_date}）", ""])

        for market_key in MARKET_ORDER:
            market_block = payload.get("markets", {}).get(market_key)
            market_label = config["markets"][market_key]["label"]
            if market_block:
                picks = market_block.get("picks", [])
                if picks:
                    graded = _grade_records(picks, start, end)
                    if graded:
                        lines.append(f"### {market_label} · 观察池推荐")
                        lines.append("")
                        lines.extend(_format_graded_table(graded, picks))
                        lines.append("")
                        summary = _summarize_graded(graded)
                        horizon_result["markets"][market_key] = summary
                        lines.append(
                            f"**{market_label}观察池小结**：平均分 {summary['average_score']:.1f}，"
                            f"命中率(≥60分) {summary['hit_rate'] * 100:.0f}%"
                        )
                        lines.append("")

            holdings_records = (payload.get("holdings") or {}).get(market_key, [])
            if holdings_records:
                holdings_graded = _grade_records(holdings_records, start, end)
                if holdings_graded:
                    lines.append(f"### {market_label} · 持仓操作")
                    lines.append("")
                    lines.extend(_format_graded_table(holdings_graded, holdings_records))
                    lines.append("")
                    holdings_summary = _summarize_graded(holdings_graded)
                    horizon_result["holdings"][market_key] = holdings_summary
                    lines.append(
                        f"**{market_label}持仓小结**：平均分 {holdings_summary['average_score']:.1f}，"
                        f"命中率(≥60分) {holdings_summary['hit_rate'] * 100:.0f}%"
                    )
                    lines.append("")

        review_payload["horizons"][f"T+{horizon}"] = horizon_result

    if REVIEW_SCORES_PATH.exists():
        history = json.loads(REVIEW_SCORES_PATH.read_text(encoding="utf-8"))
    else:
        history = {"runs": []}
    history["runs"].append(review_payload)
    history["runs"] = history["runs"][-60:]
    REVIEW_SCORES_PATH.parent.mkdir(parents=True, exist_ok=True)
    REVIEW_SCORES_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")

    lines.append("---")
    lines.append("")
    lines.append("复盘结果已写入 `data/review_scores.json`。观察池推荐与持仓操作分开统计准确率。")
    return "\n".join(lines), review_payload


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from .env without overriding existing environment."""
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _split_recipients(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _notification_settings() -> dict[str, Any]:
    config = load_config()
    notifications = config.get("notifications", {})
    if notifications:
        return notifications
    wechat = config.get("wechat", {})
    channels = ["wechat"] if wechat else ["email"]
    return {
        "channels": channels,
        "email": {
            "smtp_host_env": "SMTP_HOST",
            "smtp_port_env": "SMTP_PORT",
            "smtp_port_default": 587,
            "smtp_user_env": "SMTP_USER",
            "smtp_password_env": "SMTP_PASSWORD",
            "from_env": "EMAIL_FROM",
            "to_env": "EMAIL_TO",
            "use_tls": True,
        },
        "wechat": {
            "sendkey_env": wechat.get("sendkey_env", "SERVERCHAN_SENDKEY"),
        },
    }


def _email_settings() -> dict[str, Any]:
    return _notification_settings().get("email", {})


def _wechat_settings() -> dict[str, Any]:
    return _notification_settings().get("wechat", {})


def _email_configured() -> bool:
    settings = _email_settings()
    host = _env(str(settings.get("smtp_host_env", "SMTP_HOST")))
    to_value = _env(str(settings.get("to_env", "EMAIL_TO")))
    from_value = _env(str(settings.get("from_env", "EMAIL_FROM")))
    return bool(host and to_value and from_value)


def _wechat_configured() -> bool:
    settings = _wechat_settings()
    sendkey_env = str(settings.get("sendkey_env", "SERVERCHAN_SENDKEY"))
    return bool(_env(sendkey_env))


def resolve_notification_channels(requested: list[str] | None = None) -> list[str]:
    """Return active delivery channels based on config and environment."""
    configured = [str(item) for item in _notification_settings().get("channels", ["email"])]
    available: list[str] = []
    for channel in configured:
        if channel == "email" and _email_configured():
            available.append("email")
        elif channel == "wechat" and _wechat_configured():
            available.append("wechat")
    if requested:
        missing = [channel for channel in requested if channel not in available]
        if missing:
            raise RuntimeError(
                f"Requested channels not configured: {', '.join(missing)}. "
                "Check notifications settings and environment variables."
            )
        return requested
    if not available:
        raise RuntimeError(
            "No notification channel configured. Set SMTP_HOST/EMAIL_FROM/EMAIL_TO "
            "for email, or SERVERCHAN_SENDKEY for WeChat."
        )
    return available


def _inline_html(text: str) -> str:
    """Escape HTML then render the markdown bold/link syntax we emit."""
    escaped = html.escape(text)
    escaped = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" style="color:#3b5bdb;text-decoration:none;" target="_blank">\1</a>',
        escaped,
    )
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


_HTML_STYLES = {
    "h1": "font-size:20px;margin:0 0 4px;color:#1a1a2e;",
    "h2": "font-size:16px;margin:24px 0 8px;padding-bottom:6px;border-bottom:2px solid #e8e8ef;color:#1a1a2e;",
    "h3": "font-size:14px;margin:18px 0 6px;color:#2c2c44;",
    "p": "margin:4px 0;line-height:1.6;",
    "blockquote": "margin:8px 0;padding:8px 12px;background:#f6f7fb;border-left:3px solid #8a8fb8;color:#555;font-size:13px;border-radius:0 6px 6px 0;",
    "ul": "margin:6px 0;padding-left:20px;line-height:1.7;",
    "table": "border-collapse:collapse;margin:8px 0;width:100%;font-size:13px;",
    "th": "background:#f0f1f7;border:1px solid #dcdce6;padding:6px 10px;text-align:left;white-space:nowrap;",
    "td": "border:1px solid #e4e4ec;padding:6px 10px;",
    "hr": "border:none;border-top:1px solid #e0e0e8;margin:20px 0;",
}


def _table_html(rows: list[str]) -> str:
    parsed = [
        [cell.strip() for cell in row.strip().strip("|").split("|")]
        for row in rows
        if not re.fullmatch(r"\|?[\s:|-]+\|?", row.strip())
    ]
    if not parsed:
        return ""
    header, *body = parsed
    parts = [f'<table style="{_HTML_STYLES["table"]}">']
    parts.append(
        "<tr>"
        + "".join(f'<th style="{_HTML_STYLES["th"]}">{_inline_html(cell)}</th>' for cell in header)
        + "</tr>"
    )
    for row in body:
        parts.append(
            "<tr>"
            + "".join(f'<td style="{_HTML_STYLES["td"]}">{_inline_html(cell)}</td>' for cell in row)
            + "</tr>"
        )
    parts.append("</table>")
    return "".join(parts)


def _report_html(text: str) -> str:
    """Render the bot's markdown subset into styled email HTML."""
    blocks: list[str] = []
    list_items: list[str] = []
    table_rows: list[str] = []

    def flush_list() -> None:
        if list_items:
            items = "".join(f"<li>{item}</li>" for item in list_items)
            blocks.append(f'<ul style="{_HTML_STYLES["ul"]}">{items}</ul>')
            list_items.clear()

    def flush_table() -> None:
        if table_rows:
            blocks.append(_table_html(table_rows))
            table_rows.clear()

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("|"):
            flush_list()
            table_rows.append(stripped)
            continue
        flush_table()
        if not stripped:
            flush_list()
            continue
        if stripped.startswith("- "):
            list_items.append(_inline_html(stripped[2:]))
            continue
        flush_list()
        if stripped == "---":
            blocks.append(f'<hr style="{_HTML_STYLES["hr"]}">')
        elif stripped.startswith("### "):
            blocks.append(f'<h3 style="{_HTML_STYLES["h3"]}">{_inline_html(stripped[4:])}</h3>')
        elif stripped.startswith("## "):
            blocks.append(f'<h2 style="{_HTML_STYLES["h2"]}">{_inline_html(stripped[3:])}</h2>')
        elif stripped.startswith("# "):
            blocks.append(f'<h1 style="{_HTML_STYLES["h1"]}">{_inline_html(stripped[2:])}</h1>')
        elif stripped.startswith("> "):
            blocks.append(
                f'<blockquote style="{_HTML_STYLES["blockquote"]}">{_inline_html(stripped[2:])}</blockquote>'
            )
        else:
            blocks.append(f'<p style="{_HTML_STYLES["p"]}">{_inline_html(stripped)}</p>')
    flush_list()
    flush_table()

    body = "".join(blocks)
    return (
        "<html><body style=\"margin:0;padding:16px;background:#fafafa;\">"
        '<div style="max-width:680px;margin:0 auto;background:#ffffff;border-radius:10px;'
        "padding:24px;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;"
        'font-size:14px;color:#333;">'
        f"{body}"
        "</div></body></html>"
    )


def send_email(title: str, text: str) -> None:
    """Deliver the report through SMTP."""
    settings = _email_settings()
    host = _env(str(settings.get("smtp_host_env", "SMTP_HOST")))
    port_env = str(settings.get("smtp_port_env", "SMTP_PORT"))
    port = int(_env(port_env) or str(settings.get("smtp_port_default", 587)))
    user = _env(str(settings.get("smtp_user_env", "SMTP_USER")))
    password = _env(str(settings.get("smtp_password_env", "SMTP_PASSWORD")))
    from_addr = _env(str(settings.get("from_env", "EMAIL_FROM")))
    to_addrs = _split_recipients(_env(str(settings.get("to_env", "EMAIL_TO"))))
    if port == 465:
        use_ssl, use_tls = True, False
    else:
        use_ssl = False
        use_tls = bool(settings.get("use_tls", True))

    if not host or not from_addr or not to_addrs:
        raise RuntimeError("Email is not configured: SMTP_HOST, EMAIL_FROM, EMAIL_TO are required.")
    if not password or "授权码" in password:
        raise RuntimeError(
            "SMTP_PASSWORD is missing or still a placeholder. "
            "Edit .env and set your QQ mail authorization code."
        )
    try:
        password.encode("ascii")
    except UnicodeEncodeError as exc:
        raise RuntimeError(
            "SMTP_PASSWORD must be the QQ mail authorization code (ASCII only), "
            "not your Chinese placeholder text."
        ) from exc

    message = EmailMessage()
    message["Subject"] = title
    message["From"] = from_addr
    message["To"] = ", ".join(to_addrs)
    message.set_content(text)
    message.add_alternative(_report_html(text), subtype="html")

    if use_ssl:
        server_factory = smtplib.SMTP_SSL
    else:
        server_factory = smtplib.SMTP

    with server_factory(host, port, timeout=30) as server:
        if not use_ssl and use_tls:
            server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(message, from_addr=from_addr, to_addrs=to_addrs)


def send_wechat(title: str, text: str, sendkey: str) -> None:
    """Push the report to personal WeChat through ServerChan Turbo."""
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    response = requests.post(
        url,
        data={
            "title": title,
            "desp": text,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"ServerChan rejected the message: {payload}")


def send_report(title: str, text: str, channels: list[str] | None = None) -> list[str]:
    """Send a report through all configured notification channels."""
    active_channels = resolve_notification_channels(channels)
    delivered: list[str] = []
    for channel in active_channels:
        if channel == "email":
            send_email(title, text)
            delivered.append("email")
            continue
        if channel == "wechat":
            sendkey = _env(str(_wechat_settings().get("sendkey_env", "SERVERCHAN_SENDKEY")))
            send_wechat(title, text, sendkey)
            delivered.append("wechat")
    return delivered


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print reports without sending email or WeChat notifications.",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Review past predictions and score accuracy.",
    )
    parser.add_argument(
        "--iterate",
        action="store_true",
        help="Analyze accuracy and auto-tune thresholds / A-share alphasift strategy.",
    )
    parser.add_argument(
        "--holdings",
        action="store_true",
        help="Analyze configured holdings only and suggest buy/sell levels.",
    )
    parser.add_argument(
        "--social",
        action="store_true",
        help="Fetch Reddit/X social buzz and sentiment only.",
    )
    parser.add_argument(
        "--serenity",
        action="store_true",
        help="Summarize @aleabitoreddit (Serenity) posts from N days ago.",
    )
    parser.add_argument(
        "--potential",
        action="store_true",
        help="Scan for early-stage high-potential stocks (pre-parabolic phase).",
    )
    parser.add_argument(
        "--research",
        action="store_true",
        help="Link potential radar picks with Serenity supply-chain research.",
    )
    parser.add_argument(
        "--market",
        choices=["all", *MARKET_ORDER],
        default="all",
        help="Limit output to one market.",
    )
    parser.add_argument(
        "--channel",
        choices=["email", "wechat", "all"],
        default="all",
        help="Notification channel override (default: use portfolio_config.json).",
    )
    return parser.parse_args()


def _channel_override(args: argparse.Namespace) -> list[str] | None:
    if args.channel == "all":
        return None
    if args.channel == "email":
        return ["email"]
    return ["wechat"]


def main() -> int:
    load_dotenv()
    args = parse_args()

    if args.review:
        report, _ = review_predictions()
        print(report)
        if args.dry_run:
            return 0
        delivered = send_report("推荐复盘打分", report, channels=_channel_override(args))
        print(f"Review report sent via: {', '.join(delivered)}.")
        return 0

    if args.iterate:
        from iterate_accuracy import iterate_accuracy

        report, _ = iterate_accuracy(apply=not args.dry_run)
        print(report)
        if args.dry_run:
            return 0
        delivered = send_report("准确率自迭代报告", report, channels=_channel_override(args))
        print(f"Iteration report sent via: {', '.join(delivered)}.")
        return 0

    if args.holdings:
        report = build_holdings_report()
        print(report)
        if args.dry_run:
            return 0
        delivered = send_report("持仓今日操作指南", report, channels=_channel_override(args))
        print(f"Holdings report sent via: {', '.join(delivered)}.")
        return 0

    if args.social:
        from social_sentiment import build_social_report, format_social_section

        social = build_social_report()
        report = "\n".join(format_social_section(social))
        print(report)
        if args.dry_run:
            return 0
        delivered = send_report("社交热议情绪简报", report, channels=_channel_override(args))
        print(f"Social report sent via: {', '.join(delivered)}.")
        return 0

    if args.serenity:
        from serenity_digest import build_serenity_digest, format_serenity_section

        digest = build_serenity_digest()
        report = "\n".join(format_serenity_section(digest))
        print(report)
        if args.dry_run:
            return 0
        delivered = send_report("Serenity 言论摘要", report, channels=_channel_override(args))
        print(f"Serenity digest sent via: {', '.join(delivered)}.")
        return 0

    if args.potential:
        from potential_screener import format_potential_radar_section, scan_potential_radar

        markets = [args.market] if args.market != "all" else None
        picks, errors = scan_potential_radar(markets=markets)
        report = "\n".join(format_potential_radar_section(picks, errors))
        print(report)
        if args.dry_run:
            return 0
        delivered = send_report("潜力雷达", report, channels=_channel_override(args))
        print(f"Potential radar sent via: {', '.join(delivered)}.")
        return 0

    if args.research:
        from potential_screener import scan_potential_radar
        from research_agent import build_research_briefs, format_research_agent_section
        from serenity_digest import build_serenity_digest

        markets = [args.market] if args.market != "all" else None
        picks, errors = scan_potential_radar(markets=markets)
        serenity = build_serenity_digest()
        briefs = build_research_briefs(picks, serenity)
        lines = format_research_agent_section(briefs)
        if errors:
            lines.extend(["", f"_扫描异常 {len(errors)} 只。_", ""])
        report = "\n".join(lines)
        print(report)
        if args.dry_run:
            return 0
        delivered = send_report("研究 Agent 简报", report, channels=_channel_override(args))
        print(f"Research agent report sent via: {', '.join(delivered)}.")
        return 0

    markets = [args.market] if args.market != "all" else list(MARKET_ORDER)
    market_reports: dict[
        str, tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]
    ] = {}
    any_success = False
    regimes = fetch_all_regimes()

    for market_key in markets:
        picks, others, errors, extras = scan_market(market_key, regimes.get(market_key))
        if picks or others:
            any_success = True
        market_reports[market_key] = (picks, others, errors, extras)

    if not any_success:
        return 1

    holdings_scan = scan_holdings(regimes=regimes)
    social_report = None
    serenity_digest = None
    social_cfg = load_config().get("social_sentiment", {})
    if social_cfg.get("enabled", False) and social_cfg.get("include_in_combined_report", True):
        from social_sentiment import build_social_report

        social_report = build_social_report(social_cfg)
    serenity_cfg = social_cfg.get("serenity", {})
    if serenity_cfg.get("enabled", False) and serenity_cfg.get("include_in_combined_report", True):
        from serenity_digest import build_serenity_digest

        serenity_digest = build_serenity_digest(days_ago=int(serenity_cfg.get("days_ago", 2)))

    potential_scan = None
    potential_cfg = load_config().get("potential_radar", {})
    if potential_cfg.get("enabled", False) and potential_cfg.get("include_in_combined_report", True):
        from potential_screener import scan_potential_radar

        potential_scan = scan_potential_radar()

    research_briefs = None
    research_cfg = load_config().get("research_agent", {})
    if (
        research_cfg.get("enabled", True)
        and research_cfg.get("include_in_combined_report", True)
        and potential_scan is not None
    ):
        from research_agent import build_research_briefs

        potential_picks, _ = potential_scan
        research_briefs = build_research_briefs(potential_picks, serenity_digest)

    merge_reports = len(markets) > 1 and _merge_markets_enabled()
    if merge_reports:
        combined = build_combined_report(
            market_reports,
            regimes=regimes,
            holdings=holdings_scan,
            social=social_report,
            serenity=serenity_digest,
            potential=potential_scan,
            research=research_briefs,
        )
        print(combined)
    else:
        for market_key in markets:
            picks, others, errors, extras = market_reports[market_key]
            notes = [_regime_section_note(extras), _market_section_note(market_key, extras)]
            section_note = " ".join(note for note in notes if note)
            report = build_market_report(market_key, picks, others, errors, section_note=section_note)
            print(report)
            print("\n" + "=" * 60 + "\n")

    if not args.dry_run:
        if merge_reports:
            title = _combined_report_title()
            delivered = send_report(title, combined, channels=_channel_override(args))
            print(f"{title} sent via: {', '.join(delivered)}.")
        else:
            config = load_config()
            for market_key in markets:
                picks, others, errors, extras = market_reports[market_key]
                notes = [_regime_section_note(extras), _market_section_note(market_key, extras)]
                section_note = " ".join(note for note in notes if note)
                report = build_market_report(
                    market_key, picks, others, errors, section_note=section_note
                )
                title = config["markets"][market_key]["push_title"]
                delivered = send_report(title, report, channels=_channel_override(args))
                print(f"{title} sent via: {', '.join(delivered)}.")

    save_predictions(
        {
            key: (picks, others, extras)
            for key, (picks, others, _, extras) in market_reports.items()
        },
        holdings=_holdings_prediction_records(holdings_scan[0]) if holdings_scan[0] else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
