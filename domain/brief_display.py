"""Structured brief sections for app / API rendering."""

from __future__ import annotations

from typing import Any

from market_regime import MarketRegime
from portfolio_manager import PortfolioAnalysis
from stock_bot import Recommendation, _display_ticker, _money


_ACTION_TONE = {
    "允许加仓": "positive",
    "置换加仓": "warn",
    "降低风险": "negative",
    "继续观察": "neutral",
    "买入": "positive",
    "卖出": "negative",
    "观望": "neutral",
}


def _tone(action: str) -> str:
    return _ACTION_TONE.get(action, "neutral")


def _row(
    *,
    primary: str,
    secondary: str = "",
    badge: str = "",
    badge_tone: str = "neutral",
    detail: str = "",
    subdetail: str = "",
) -> dict[str, str]:
    return {
        "primary": primary,
        "secondary": secondary,
        "badge": badge,
        "badge_tone": badge_tone,
        "detail": detail,
        "subdetail": subdetail,
    }


def build_display_sections(
    verdict: dict[str, Any],
    analysis: PortfolioAnalysis,
    regimes: dict[str, MarketRegime] | None = None,
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []

    observe = verdict["observe_holdings"]
    if observe:
        names = "、".join(_display_ticker(item.recommendation) for item in observe)
        sections.append(
            {
                "title": "继续观察",
                "subtitle": f"{len(observe)} 只暂无需操作",
                "kind": "text",
                "lines": [names],
            }
        )

    deploy = verdict.get("deploy_picks") or []
    rotation = verdict.get("rotation_picks") or []
    if deploy or rotation:
        pick_rows = []
        for rec in deploy[:5]:
            snap = rec.snapshot
            sign = "+" if snap.change_pct >= 0 else ""
            pick_rows.append(
                _row(
                    primary=_display_ticker(rec),
                    secondary=f"{rec.score:.0f}分 · {_money(snap.price, snap.currency)} ({sign}{snap.change_pct:.2f}%)",
                    badge="可新开仓",
                    badge_tone="positive",
                    detail=f"买 {_money(rec.buy_low, snap.currency)}~{_money(rec.buy_high, snap.currency)}",
                )
            )
        for rec in rotation[:5]:
            snap = rec.snapshot
            sign = "+" if snap.change_pct >= 0 else ""
            pick_rows.append(
                _row(
                    primary=_display_ticker(rec),
                    secondary=f"{rec.score:.0f}分 · {_money(snap.price, snap.currency)} ({sign}{snap.change_pct:.2f}%)",
                    badge="置换候选",
                    badge_tone="warn",
                    detail=f"买 {_money(rec.buy_low, snap.currency)}~{_money(rec.buy_high, snap.currency)}",
                )
            )
        sections.append(
            {
                "title": "值得研究",
                "subtitle": "观察池达标候选",
                "kind": "rows",
                "rows": pick_rows,
            }
        )

    risks: list[str] = []
    risks.extend(analysis.alerts)
    risks.extend(analysis.event_alerts[:3])
    for market_key, regime in (regimes or {}).items():
        if regime.label == "弱势":
            risks.append(f"{regime.index_name} 环境偏弱")
    if risks:
        seen: set[str] = set()
        risk_lines = []
        for risk in risks:
            if risk in seen:
                continue
            seen.add(risk)
            risk_lines.append(risk)
            if len(risk_lines) >= 5:
                break
        sections.append(
            {
                "title": "关键风险",
                "subtitle": "集中度、波动与大盘",
                "kind": "text",
                "lines": risk_lines,
            }
        )

    return sections
