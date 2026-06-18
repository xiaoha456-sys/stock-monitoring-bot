#!/usr/bin/env python3
"""A-share ETF / fund picks for long-term holding when individual stocks are limited."""

from __future__ import annotations

import sys
from dataclasses import replace
from typing import Any

from market_regime import MarketRegime
from stock_bot import Recommendation, _display_ticker, _money, build_recommendation, fetch_snapshot, load_config


def _funds_config() -> dict[str, Any]:
    return dict(load_config().get("markets", {}).get("CN", {}).get("funds", {}))


def default_fund_universe() -> list[dict[str, str]]:
    return [
        {"ticker": "510300.SS", "name": "沪深300ETF", "theme": "宽基"},
        {"ticker": "510500.SS", "name": "中证500ETF", "theme": "宽基"},
        {"ticker": "510880.SS", "name": "红利ETF", "theme": "红利"},
        {"ticker": "515450.SS", "name": "红利低波50ETF", "theme": "红利"},
        {"ticker": "512010.SS", "name": "医药ETF", "theme": "医药"},
        {"ticker": "159928.SZ", "name": "消费ETF", "theme": "消费"},
    ]


def fund_universe() -> list[dict[str, str]]:
    cfg = _funds_config()
    configured = cfg.get("watchlist")
    if not configured:
        return default_fund_universe()
    items: list[dict[str, str]] = []
    for entry in configured:
        if isinstance(entry, str):
            items.append({"ticker": entry, "name": "", "theme": ""})
        elif isinstance(entry, dict):
            items.append(
                {
                    "ticker": str(entry.get("ticker", "")),
                    "name": str(entry.get("name", "") or ""),
                    "theme": str(entry.get("theme", "") or ""),
                }
            )
    return [item for item in items if item.get("ticker")]


def _fund_hold_score(rec: Recommendation, regime: MarketRegime | None = None) -> float:
    snap = rec.snapshot
    score = rec.score
    if snap.week_52_position > 85:
        score -= 12
    elif snap.week_52_position < 35:
        score += 4
    if snap.rsi_14 > 72:
        score -= 8
    if snap.price >= snap.sma_200:
        score += 3
    if regime and regime.label == "弱势":
        score -= 4
    return score


def scan_cn_funds(
    regime: MarketRegime | None = None,
) -> tuple[list[Recommendation], dict[str, str]]:
    cfg = _funds_config()
    if not cfg.get("enabled", True):
        return [], {}

    top_n = int(cfg.get("top_n", 2))
    errors: dict[str, str] = {}
    recommendations: list[Recommendation] = []
    for entry in fund_universe():
        ticker = entry["ticker"]
        try:
            rec = build_recommendation(fetch_snapshot(ticker))
            if entry.get("name"):
                rec = replace(rec, name=entry["name"])
            recommendations.append(rec)
        except Exception as exc:
            print(f"Warning: CN fund fetch failed for {ticker}: {exc}", file=sys.stderr)
            errors[ticker] = str(exc)

    ranked = sorted(
        recommendations,
        key=lambda item: _fund_hold_score(item, regime),
        reverse=True,
    )
    return ranked[:top_n], errors


def format_cn_funds_section(
    picks: list[Recommendation],
    errors: dict[str, str] | None = None,
) -> list[str]:
    cfg = _funds_config()
    if not cfg.get("enabled", True):
        return []
    if not picks:
        return []

    lines = [
        "## 📊 A股长期基金参考",
        "",
        "> 无法交易科创板/创业板个股时，可用宽基/红利等场内 ETF 长期定投或置换配置。",
        "",
        "| 基金 | 现价 | 评分 | 买入参考 | 目标 | 说明 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for rec in picks:
        snap = rec.snapshot
        sign = "+" if snap.change_pct >= 0 else ""
        theme = ""
        for entry in fund_universe():
            if entry["ticker"] == rec.ticker and entry.get("theme"):
                theme = entry["theme"]
                break
        note = f"{theme} · {rec.action}" if theme else rec.action
        lines.append(
            f"| {_display_ticker(rec)} | "
            f"{_money(snap.price, snap.currency)} ({sign}{snap.change_pct:.2f}%) | "
            f"{rec.score:.0f} | "
            f"{_money(rec.buy_low, snap.currency)}~{_money(rec.buy_high, snap.currency)} | "
            f"{_money(rec.target_price, snap.currency)} | {note} |"
        )
    lines.append("")
    lines.append(
        "**定投参考**：单笔可按 ¥5,000~10,000 分批挂买入区间下沿；"
        "置换场景先卖弱仓，再用同等资金买入 ETF（100 股整数倍）。"
    )
    if errors:
        lines.append("")
        lines.append(f"_数据异常 {len(errors)} 只。_")
    lines.append("")
    return lines
