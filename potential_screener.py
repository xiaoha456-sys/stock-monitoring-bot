#!/usr/bin/env python3
"""Screen for early-stage high-potential setups (pre-parabolic phase).

Targets profiles similar to MU ~1y ago or NVDA ~3y ago:
- Industry/theme tailwind + volume inflection
- 52-week position still has room (not chasing ATH)
- Momentum turning up without being overextended
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from stock_bot import (
    MARKET_ORDER,
    StockSnapshot,
    _display_ticker,
    _money,
    fetch_snapshot,
    load_config,
)


@dataclass(frozen=True)
class PotentialPick:
    ticker: str
    name: str
    market: str
    score: float
    phase: str
    reasons: tuple[str, ...]
    snapshot: StockSnapshot


def _potential_config() -> dict[str, Any]:
    return load_config().get("potential_radar", {})


def _market_from_ticker(ticker: str) -> str:
    if ticker.endswith(".SS") or ticker.endswith(".SZ"):
        return "CN"
    if ticker.endswith(".AX"):
        return "AU"
    return "US"


def _ticker_name(ticker: str, holdings: dict[str, Any]) -> str:
    from stock_bot import _ticker_display_name

    return _ticker_display_name(ticker) or ticker


def score_growth_potential(snapshot: StockSnapshot) -> tuple[float, str, tuple[str, ...]]:
    """Score 0-100 for early-growth potential; higher = better risk/reward setup."""
    cfg = _potential_config().get("scoring", {})
    pos_low = float(cfg.get("week_52_position_low", 22))
    pos_high = float(cfg.get("week_52_position_high", 68))
    pos_late = float(cfg.get("week_52_position_late", 88))
    vol_min = float(cfg.get("min_volume_ratio", 1.1))
    mom_20_min = float(cfg.get("min_momentum_20d", 3.0))
    mom_20_max = float(cfg.get("max_momentum_20d", 35.0))
    rsi_hot = float(cfg.get("rsi_overbought", 72))

    score = 48.0
    reasons: list[str] = []

    pos = snapshot.week_52_position
    if pos_low <= pos <= pos_high:
        score += 18
        reasons.append(f"52周位置 {pos:.0f}% 适中，仍有上行空间")
    elif pos < pos_low:
        score += 6
        reasons.append(f"52周位置 {pos:.0f}% 偏低，需确认基本面拐点")
    elif pos < pos_late:
        score += 4
        reasons.append(f"52周位置 {pos:.0f}% 偏强，动量已启动")
    else:
        score -= 14
        reasons.append(f"52周位置 {pos:.0f}% 接近高位，可能已过早期阶段")

    if snapshot.volume_ratio >= vol_min:
        score += 14
        reasons.append(f"量能放大 {snapshot.volume_ratio:.1f}x，资金关注度上升")
    elif snapshot.volume_ratio >= 0.9:
        score += 4

    if mom_20_min <= snapshot.momentum_20d <= mom_20_max:
        score += 12
        reasons.append(f"20日动量 +{snapshot.momentum_20d:.1f}%，趋势刚启动")
    elif snapshot.momentum_20d > mom_20_max:
        score -= 8
        reasons.append("短期涨幅过大，追高风险上升")
    elif snapshot.momentum_20d > 0:
        score += 5

    if snapshot.momentum_60d > 0:
        score += 6
        reasons.append(f"60日动量 +{snapshot.momentum_60d:.1f}%，中期趋势配合")
    elif snapshot.momentum_60d > -8:
        score += 2
        reasons.append("中期仍处筑底/扭转阶段")

    if snapshot.price > snapshot.sma_50 > snapshot.sma_200:
        score += 12
        reasons.append("均线多头排列，趋势质量佳")
    elif snapshot.price > snapshot.sma_50:
        score += 8
        reasons.append("站上50日均线，趋势转强")
    elif snapshot.price > snapshot.sma_200 and snapshot.sma_50 > snapshot.sma_200 * 0.97:
        score += 5
        reasons.append("长期趋势企稳，等待突破确认")

    if snapshot.rsi_14 < rsi_hot:
        score += 5
    else:
        score -= 10
        reasons.append(f"RSI {snapshot.rsi_14:.0f} 偏热")

    if 0 < snapshot.change_pct <= 4:
        score += 4
    elif snapshot.change_pct > 6:
        score -= 5

    score = max(0.0, min(score, 100.0))

    if score >= 72:
        phase = "潜力启动"
    elif score >= 58:
        phase = "蓄势待发"
    elif score >= 45:
        phase = "观察筑底"
    else:
        phase = "暂不符合"

    return score, phase, tuple(reasons[:4])


def _universe_for_market(market_key: str) -> list[str]:
    cfg = _potential_config()
    extra = list(cfg.get("universes", {}).get(market_key, []))
    base = list(load_config().get("markets", {}).get(market_key, {}).get("watchlist", []))
    holdings = list(load_config().get("holdings", {}).keys())
    merged: list[str] = []
    for ticker in extra + base + holdings:
        if _market_from_ticker(ticker) != market_key:
            continue
        if ticker not in merged:
            merged.append(ticker)
    return merged


def scan_potential_radar(
    markets: list[str] | None = None,
) -> tuple[list[PotentialPick], dict[str, str]]:
    cfg = _potential_config()
    if not cfg.get("enabled", True):
        return [], {}

    min_score = float(cfg.get("min_score", 58))
    top_n = int(cfg.get("top_n", 5))
    market_keys = markets or [key for key in MARKET_ORDER if cfg.get("markets", {}).get(key, True)]
    holdings = load_config().get("holdings", {})

    picks: list[PotentialPick] = []
    errors: dict[str, str] = {}

    for market_key in market_keys:
        for ticker in _universe_for_market(market_key):
            try:
                snapshot = fetch_snapshot(ticker)
                score, phase, reasons = score_growth_potential(snapshot)
                if score < min_score or phase == "暂不符合":
                    continue
                picks.append(
                    PotentialPick(
                        ticker=ticker,
                        name=_ticker_name(ticker, holdings),
                        market=market_key,
                        score=round(score, 1),
                        phase=phase,
                        reasons=reasons,
                        snapshot=snapshot,
                    )
                )
            except Exception as exc:
                errors[ticker] = str(exc)
                print(f"Warning: potential scan failed for {ticker}: {exc}", file=sys.stderr)

    picks.sort(key=lambda item: (-item.score, -item.snapshot.volume_ratio))
    per_market_cap = int(cfg.get("max_per_market", 2))
    if per_market_cap > 0:
        selected: list[PotentialPick] = []
        counts: dict[str, int] = {}
        for pick in picks:
            if counts.get(pick.market, 0) >= per_market_cap:
                continue
            selected.append(pick)
            counts[pick.market] = counts.get(pick.market, 0) + 1
            if len(selected) >= top_n:
                break
        picks = selected
    else:
        picks = picks[:top_n]

    return picks, errors


def format_potential_radar_section(
    picks: list[PotentialPick],
    errors: dict[str, str] | None = None,
) -> list[str]:
    cfg = _potential_config()
    lines = [
        "## 🚀 潜力雷达",
        "",
        "> 寻找类似「一年前 MU / 三年前 NVDA」的早期阶段：趋势刚启动、量能放大、",
        "> 52周位置仍有空间。与「放量突破」互补，偏中长期研究候选。",
        "",
    ]

    if not picks:
        lines.append("_今日暂无达到潜力评分的标的。_")
        lines.append("")
        if errors:
            lines.append(f"_扫描异常 {len(errors)} 只，详见附录。_")
            lines.append("")
        return lines

    for index, pick in enumerate(picks, start=1):
        snap = pick.snapshot
        sign = "+" if snap.change_pct >= 0 else ""
        reason = " · ".join(pick.reasons[:2])
        lines.append(
            f"{index}. **{_display_ticker_from_pick(pick)}** · {pick.phase} · "
            f"{pick.score:.0f}分 · {_money(snap.price, snap.currency)} ({sign}{snap.change_pct:.2f}%)"
        )
        lines.append(f"  　{reason}")
    lines.append("")

    note = str(cfg.get("disclaimer", "") or "").strip()
    if note:
        lines.append(f"_{note}_")
        lines.append("")
    return lines


def _display_ticker_from_pick(pick: PotentialPick) -> str:
    if pick.name and pick.name != pick.ticker:
        return f"{pick.name} ({pick.ticker})"
    return pick.ticker
