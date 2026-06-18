#!/usr/bin/env python3
"""Market radar: multi-lens scan across US/CN/AU, daily top research candidates."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from stock_bot import (
    MARKET_ORDER,
    Recommendation,
    StockSnapshot,
    _display_ticker,
    _holding_market,
    _money,
    _ticker_display_name,
    build_recommendation,
    fetch_snapshot,
    load_config,
    scan_market,
)

SYDNEY = ZoneInfo("Australia/Sydney")
ROOT = Path(__file__).resolve().parent
RADAR_DIR = ROOT / "data" / "radar"

_CATALYST_KEYWORDS = (
    "earnings",
    "guidance",
    "beat",
    "upgrade",
    "contract",
    "approval",
    "policy",
    "财报",
    "业绩",
    "中标",
    "获批",
    "回购",
    "增持",
    "降息",
    "利好",
)


@dataclass(frozen=True)
class RadarPick:
    ticker: str
    name: str
    market: str
    composite_score: float
    trend_score: float
    valuation_score: float
    catalyst_score: float
    risk_score: float
    reasons: tuple[str, ...]
    snapshot: StockSnapshot
    recommendation: Recommendation


def _radar_config() -> dict[str, Any]:
    return load_config().get("market_radar", {})


def _lens_weights() -> dict[str, float]:
    defaults = {"trend": 0.35, "valuation": 0.25, "catalyst": 0.20, "risk": 0.20}
    cfg = _radar_config().get("lens_weights", {})
    merged = dict(defaults)
    merged.update({str(k): float(v) for k, v in cfg.items()})
    total = sum(merged.values()) or 1.0
    return {key: value / total for key, value in merged.items()}


def score_trend(snapshot: StockSnapshot, rec: Recommendation) -> tuple[float, str]:
    score = rec.score
    if snapshot.price > snapshot.sma_50 > snapshot.sma_200:
        note = "趋势向上"
    elif snapshot.price < snapshot.sma_50 < snapshot.sma_200:
        note = "趋势偏弱"
    else:
        note = "趋势待确认"
    return score, note


def score_valuation(snapshot: StockSnapshot) -> tuple[float, str]:
    pos = snapshot.week_52_position
    if pos <= 25:
        return 82.0, f"52周低位区 {pos:.0f}%"
    if pos <= 45:
        return 72.0, f"估值位置偏低 {pos:.0f}%"
    if pos <= 65:
        return 58.0, f"估值中性 {pos:.0f}%"
    if pos <= 85:
        return 42.0, f"估值偏贵 {pos:.0f}%"
    return 28.0, f"接近52周高位 {pos:.0f}%"


def score_catalyst(snapshot: StockSnapshot) -> tuple[float, str]:
    if not snapshot.headlines:
        return 35.0, "暂无新闻催化"
    headline = " ".join(snapshot.headlines[:2]).lower()
    hits = [word for word in _CATALYST_KEYWORDS if word in headline]
    if hits:
        return 78.0, f"新闻催化：{snapshot.headlines[0][:48]}"
    return 62.0, f"有新闻关注：{snapshot.headlines[0][:48]}"


def score_risk(snapshot: StockSnapshot) -> tuple[float, str]:
    """Higher score = lower risk."""
    penalty = 0.0
    notes: list[str] = []
    if snapshot.rsi_14 > 75:
        penalty += 22
        notes.append(f"RSI过热 {snapshot.rsi_14:.0f}")
    elif snapshot.rsi_14 > 68:
        penalty += 10
        notes.append(f"RSI偏热 {snapshot.rsi_14:.0f}")
    if snapshot.week_52_position > 90:
        penalty += 15
        notes.append("接近年内高点")
    if snapshot.change_pct > 5:
        penalty += 12
        notes.append(f"单日大涨 {snapshot.change_pct:+.1f}%")
    elif snapshot.change_pct < -5:
        penalty += 8
        notes.append(f"单日大跌 {snapshot.change_pct:+.1f}%")
    if snapshot.volatility_20d and snapshot.volatility_20d > 4:
        penalty += 8
        notes.append("波动率偏高")
    risk_score = max(20.0, 100.0 - penalty)
    note = "；".join(notes) if notes else "风险可控"
    return risk_score, note


def score_radar_candidate(rec: Recommendation) -> RadarPick:
    snap = rec.snapshot
    trend, trend_note = score_trend(snap, rec)
    valuation, valuation_note = score_valuation(snap)
    catalyst, catalyst_note = score_catalyst(snap)
    risk, risk_note = score_risk(snap)
    weights = _lens_weights()
    composite = (
        weights["trend"] * trend
        + weights["valuation"] * valuation
        + weights["catalyst"] * catalyst
        + weights["risk"] * risk
    )
    return RadarPick(
        ticker=rec.ticker,
        name=rec.name or _ticker_display_name(rec.ticker) or rec.ticker,
        market=_holding_market(rec.ticker),
        composite_score=round(composite, 1),
        trend_score=round(trend, 1),
        valuation_score=round(valuation, 1),
        catalyst_score=round(catalyst, 1),
        risk_score=round(risk, 1),
        reasons=(trend_note, valuation_note, catalyst_note, risk_note),
        snapshot=snap,
        recommendation=rec,
    )


def _candidate_recommendations(
    market_key: str,
    regimes: dict[str, Any] | None = None,
) -> list[Recommendation]:
    regime = (regimes or {}).get(market_key)
    picks, others, _, _ = scan_market(market_key, regime)
    seen: set[str] = set()
    merged: list[Recommendation] = []
    for rec in picks + others:
        if rec.ticker in seen:
            continue
        seen.add(rec.ticker)
        merged.append(rec)
    return merged


def scan_market_radar(
    regimes: dict[str, Any] | None = None,
) -> tuple[list[RadarPick], dict[str, str]]:
    cfg = _radar_config()
    if not cfg.get("enabled", True):
        return [], {}

    top_n = int(cfg.get("top_n", 5))
    max_per_market = int(cfg.get("max_per_market", 2))
    min_score = float(cfg.get("min_composite_score", 58))
    market_keys = [
        key for key in MARKET_ORDER if cfg.get("markets", {}).get(key, True)
    ]

    candidates: list[RadarPick] = []
    errors: dict[str, str] = {}

    holdings = load_config().get("holdings", {})
    extra_tickers: dict[str, set[str]] = {key: set() for key in MARKET_ORDER}
    for ticker, info in holdings.items():
        market = str(info.get("market") or _holding_market(ticker))
        if market in extra_tickers:
            extra_tickers[market].add(ticker)

    for market_key in market_keys:
        try:
            recs = _candidate_recommendations(market_key, regimes)
            rec_by_ticker = {rec.ticker: rec for rec in recs}
            for ticker in extra_tickers.get(market_key, set()):
                if ticker in rec_by_ticker:
                    continue
                try:
                    rec_by_ticker[ticker] = build_recommendation(fetch_snapshot(ticker))
                except Exception as exc:
                    errors[ticker] = str(exc)
            for rec in rec_by_ticker.values():
                if market_key == "CN":
                    from cn_tradable import is_cn_restricted_board

                    if is_cn_restricted_board(rec.ticker):
                        continue
                pick = score_radar_candidate(rec)
                if pick.composite_score >= min_score:
                    candidates.append(pick)
        except Exception as exc:
            errors[market_key] = str(exc)
            print(f"Warning: market radar failed for {market_key}: {exc}", file=sys.stderr)

    candidates.sort(key=lambda item: item.composite_score, reverse=True)
    selected: list[RadarPick] = []
    per_market: dict[str, int] = {}
    for pick in candidates:
        count = per_market.get(pick.market, 0)
        if count >= max_per_market:
            continue
        selected.append(pick)
        per_market[pick.market] = count + 1
        if len(selected) >= top_n:
            break
    return selected, errors


def save_radar_snapshot(
    picks: list[RadarPick],
    *,
    now: datetime | None = None,
    errors: dict[str, str] | None = None,
) -> Path:
    report_time = (now or datetime.now(SYDNEY)).astimezone(SYDNEY)
    payload = {
        "generated_at": report_time.isoformat(),
        "pick_count": len(picks),
        "errors": errors or {},
        "picks": [
            {
                "ticker": pick.ticker,
                "name": pick.name,
                "market": pick.market,
                "composite_score": pick.composite_score,
                "trend_score": pick.trend_score,
                "valuation_score": pick.valuation_score,
                "catalyst_score": pick.catalyst_score,
                "risk_score": pick.risk_score,
                "reasons": list(pick.reasons),
                "price": pick.snapshot.price,
                "change_pct": pick.snapshot.change_pct,
                "action": pick.recommendation.action,
            }
            for pick in picks
        ],
    }
    RADAR_DIR.mkdir(parents=True, exist_ok=True)
    path = RADAR_DIR / f"{report_time:%Y-%m-%d}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _held_tickers() -> set[str]:
    holdings = load_config().get("holdings", {})
    held: set[str] = set()
    for ticker, info in holdings.items():
        shares = info.get("shares")
        if shares not in (None, ""):
            held.add(ticker)
    return held


def _holding_status_label(ticker: str, held: set[str]) -> str:
    return "已持仓" if ticker in held else "未持仓"


def format_market_radar_section(
    picks: list[RadarPick],
    errors: dict[str, str] | None = None,
) -> list[str]:
    cfg = _radar_config()
    held = _held_tickers()
    lines = [
        "## 📡 市场雷达",
        "",
        "> 趋势 / 估值 / 催化 / 风险 四维度评分，每日仅保留 "
        f"Top {int(cfg.get('top_n', 5))} 研究候选（非买入建议）。",
        "> **已持仓** = 可评估加仓/减仓；**未持仓** = 可评估新开仓或置换买入。",
        "",
    ]
    if not picks:
        lines.append("_今日暂无达标雷达候选。_")
        lines.append("")
    else:
        lines.extend(
            [
                "| 标的 | 状态 | 综合 | 趋势 | 估值 | 催化 | 风险 | 现价 |",
                "| --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for pick in picks:
            snap = pick.snapshot
            sign = "+" if snap.change_pct >= 0 else ""
            status = _holding_status_label(pick.ticker, held)
            lines.append(
                f"| {_display_ticker(pick.recommendation)} | {status} | {pick.composite_score:.0f} | "
                f"{pick.trend_score:.0f} | {pick.valuation_score:.0f} | "
                f"{pick.catalyst_score:.0f} | {pick.risk_score:.0f} | "
                f"{_money(snap.price, snap.currency)} ({sign}{snap.change_pct:.2f}%) |"
            )
        lines.append("")
        for index, pick in enumerate(picks, start=1):
            status = _holding_status_label(pick.ticker, held)
            lines.append(
                f"{index}. **{_display_ticker(pick.recommendation)}** · "
                f"{pick.composite_score:.0f}分 · **{status}**"
            )
            for reason in pick.reasons:
                lines.append(f"   - {reason}")
        lines.append("")

    if errors:
        lines.append("**扫描异常**")
        lines.append("")
        for key, error in list(errors.items())[:5]:
            lines.append(f"- {key}：{error}")
        lines.append("")

    disclaimer = str(cfg.get("disclaimer", "") or "").strip()
    if disclaimer:
        lines.append(f"_{disclaimer}_")
        lines.append("")
    return lines
