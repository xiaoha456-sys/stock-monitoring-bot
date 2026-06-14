#!/usr/bin/env python3
"""Compose the P0 morning brief: conclusion-first, appendix-last."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from market_regime import MarketRegime, format_regime_overview
from tuning import get_thresholds

from stock_bot import (
    MARKET_ORDER,
    Recommendation,
    _combined_report_title,
    _display_ticker,
    _holding_market,
    _holding_today_action,
    _market_section_lines,
    _market_section_note,
    _money,
    _regime_section_note,
    format_holdings_section,
)

PORTFOLIO_ACTION = {
    "买入": "允许加仓",
    "逢低关注": "允许加仓",
    "观望": "继续观察",
    "减仓": "降低风险",
    "回避": "降低风险",
}

_HOLDING_STATUS_ICON = {
    "买入": "🟢",
    "逢低关注": "🟢",
    "观望": "🟡",
    "减仓": "🔴",
    "回避": "🔴",
}

_MAX_RESEARCH_CANDIDATES = 5


def _portfolio_action(rec: Recommendation) -> str:
    return PORTFOLIO_ACTION.get(rec.action, "继续观察")


def _is_quality_pick(rec: Recommendation) -> bool:
    thresholds = get_thresholds()
    return rec.action in ("买入", "逢低关注") and rec.score >= thresholds["watch"]


def derive_verdict(
    holdings: list[Recommendation] | None,
    market_reports: dict[str, tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]],
) -> dict[str, Any]:
    holding_recs = list(holdings or [])
    add_holdings = [rec for rec in holding_recs if _portfolio_action(rec) == "允许加仓"]
    reduce_holdings = [rec for rec in holding_recs if _portfolio_action(rec) == "降低风险"]
    observe_holdings = [rec for rec in holding_recs if _portfolio_action(rec) == "继续观察"]

    quality_picks: list[Recommendation] = []
    for market_key in MARKET_ORDER:
        block = market_reports.get(market_key)
        if not block:
            continue
        picks, _, _, _ = block
        for rec in picks:
            if _is_quality_pick(rec):
                quality_picks.append(rec)
    quality_picks.sort(key=lambda item: item.score, reverse=True)
    quality_picks = quality_picks[:_MAX_RESEARCH_CANDIDATES]

    no_action = not add_holdings and not reduce_holdings and not quality_picks
    return {
        "no_action_today": no_action,
        "add_holdings": add_holdings,
        "reduce_holdings": reduce_holdings,
        "observe_holdings": observe_holdings,
        "quality_picks": quality_picks,
    }


def format_conclusion_section(verdict: dict[str, Any]) -> list[str]:
    lines = ["## 📌 今日结论", ""]
    if verdict["no_action_today"]:
        lines.append("> **今日不操作** — 持仓无需调整，观察池暂无达标候选。")
        lines.append("")
        return lines

    parts: list[str] = []
    if verdict["add_holdings"]:
        names = "、".join(_display_ticker(rec) for rec in verdict["add_holdings"][:3])
        parts.append(f"持仓允许加仓 {len(verdict['add_holdings'])} 只（{names}）")
    if verdict["reduce_holdings"]:
        names = "、".join(_display_ticker(rec) for rec in verdict["reduce_holdings"][:3])
        parts.append(f"持仓降低风险 {len(verdict['reduce_holdings'])} 只（{names}）")
    if verdict["quality_picks"]:
        parts.append(f"观察池 {len(verdict['quality_picks'])} 个候选值得进一步研究")

    lines.append(f"> **{'；'.join(parts)}**")
    lines.append("")
    return lines


def format_brief_holdings_section(
    recommendations: list[Recommendation],
    regimes: dict[str, MarketRegime] | None = None,
) -> list[str]:
    if not recommendations:
        return []

    lines = [
        "## 💼 持仓事件",
        "",
        "> 建议为「继续观察 / 允许加仓 / 降低风险」，不构成交易指令。",
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
            action = _portfolio_action(rec)
            today_action = _holding_today_action(rec, regime)
            lines.append(
                f"- {icon} **{_display_ticker(rec)}** "
                f"{_money(snap.price, snap.currency)} ({sign}{snap.change_pct:.2f}%) · "
                f"**{action}**"
            )
            lines.append(f"  　{today_action}")
        lines.append("")
    return lines


def format_research_candidates_section(candidates: list[Recommendation]) -> list[str]:
    if not candidates:
        return [
            "## 🔍 值得研究",
            "",
            "_观察池今日无达标候选。_",
            "",
        ]

    lines = [
        "## 🔍 值得研究",
        "",
        f"> 从三市场观察池筛选的 Top {len(candidates)}，供进一步研究，非买入建议。",
        "",
    ]
    for index, rec in enumerate(candidates, start=1):
        snap = rec.snapshot
        sign = "+" if snap.change_pct >= 0 else ""
        strategy = f" · {rec.strategy}" if rec.strategy else ""
        lines.append(
            f"{index}. **{_display_ticker(rec)}** · {rec.score:.0f}分{strategy} · "
            f"{_money(snap.price, snap.currency)} ({sign}{snap.change_pct:.2f}%)"
        )
    lines.append("")
    return lines


def format_risk_section(
    verdict: dict[str, Any],
    regimes: dict[str, MarketRegime] | None,
    market_reports: dict[str, tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]],
    social: Any | None,
) -> list[str]:
    risks: list[str] = []

    for market_key, regime in (regimes or {}).items():
        if regime.label == "弱势":
            risks.append(f"{regime.index_name} 环境偏弱（{regime.label}），轻仓为宜")

    for rec in verdict.get("reduce_holdings", []):
        risks.append(f"持仓 {_display_ticker(rec)} 建议降低风险")

    for market_key in MARKET_ORDER:
        block = market_reports.get(market_key)
        if not block:
            continue
        _, _, errors, _ = block
        for ticker, error in errors.items():
            if ticker == "alphasift":
                risks.append(f"A股全市场筛选异常：{error}")
            else:
                risks.append(f"{ticker} 数据异常：{error}")

    if social is not None:
        label = str(getattr(social, "sentiment_label", "") or "")
        if "看跌" in label:
            risks.append(f"社交情绪偏谨慎（{label}）")
        for item in getattr(social, "reddit_top", ())[:3]:
            if getattr(item, "sentiment_label", "") == "看跌" and getattr(item, "mentions", 0) >= 100:
                risks.append(f"Reddit 热议 {item.ticker} 情绪偏空（{item.mentions} 次提及）")

    lines = ["## ⚠️ 关键风险", ""]
    if not risks:
        lines.append("_暂无突出风险事件。_")
    else:
        for risk in risks[:6]:
            lines.append(f"- {risk}")
    lines.append("")
    return lines


def format_price_table_section(
    holdings: list[Recommendation] | None,
    candidates: list[Recommendation],
) -> list[str]:
    rows: list[Recommendation] = []
    seen: set[str] = set()
    for rec in (holdings or []) + candidates:
        if rec.ticker in seen:
            continue
        seen.add(rec.ticker)
        rows.append(rec)

    if not rows:
        return []

    lines = [
        "## 💰 价格区间",
        "",
        "| 标的 | 类型 | 现价 | 买入区间 | 目标 | 止损 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    holding_tickers = {rec.ticker for rec in (holdings or [])}
    for rec in rows:
        snap = rec.snapshot
        kind = "持仓" if rec.ticker in holding_tickers else "候选"
        lines.append(
            f"| {_display_ticker(rec)} | {kind} | "
            f"{_money(snap.price, snap.currency)} | "
            f"{_money(rec.buy_low, snap.currency)}~{_money(rec.buy_high, snap.currency)} | "
            f"{_money(rec.target_price, snap.currency)} | "
            f"{_money(rec.stop_loss, snap.currency)} |"
        )
    lines.append("")
    return lines


def format_appendix_section(
    market_reports: dict[str, tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]],
    holdings: tuple[list[Recommendation], dict[str, str]] | None,
    regimes: dict[str, MarketRegime] | None,
    social: Any | None,
    serenity: Any | None,
) -> list[str]:
    lines = ["---", "", "## 附录：技术详情", ""]

    if regimes:
        lines.append(format_regime_overview(regimes))
        lines.append("")

    if holdings is not None:
        holding_recs, holding_errors = holdings
        if holding_recs or holding_errors:
            lines.extend(format_holdings_section(holding_recs, holding_errors, regimes=regimes))
            lines.append("---")
            lines.append("")

    if serenity is not None:
        from serenity_digest import format_serenity_section

        lines.extend(format_serenity_section(serenity))
        lines.extend(["---", ""])

    if social is not None:
        from social_sentiment import format_social_section

        lines.extend(format_social_section(social))
        lines.extend(["---", ""])

    included = [key for key in MARKET_ORDER if key in market_reports]
    if included:
        lines.extend(
            [
                "### 观察池完整列表",
                "",
                "> 含技术面、新闻与量化评分，供深度参考。",
                "",
            ]
        )
    for index, market_key in enumerate(included):
        picks, others, errors, extras = market_reports[market_key]
        notes = [_regime_section_note(extras), _market_section_note(market_key, extras)]
        section_note = " ".join(note for note in notes if note)
        lines.extend(_market_section_lines(market_key, picks, others, errors, section_note))
        if index < len(included) - 1:
            lines.extend(["", "---", ""])

    return lines


def compose_morning_brief(
    market_reports: dict[str, tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]],
    now: datetime | None = None,
    regimes: dict[str, MarketRegime] | None = None,
    holdings: tuple[list[Recommendation], dict[str, str]] | None = None,
    social: Any | None = None,
    serenity: Any | None = None,
) -> str:
    from zoneinfo import ZoneInfo

    sydney = ZoneInfo("Australia/Sydney")
    report_time = (now or datetime.now(sydney)).astimezone(sydney)
    holding_recs = holdings[0] if holdings else []

    verdict = derive_verdict(holding_recs, market_reports)
    lines = [
        f"# {_combined_report_title()}",
        f"**{report_time:%Y-%m-%d %H:%M}** 悉尼时间",
        "",
        "> 结论前置、技术后置。仅供研究，不构成投资建议。",
        "",
    ]

    lines.extend(format_conclusion_section(verdict))
    lines.extend(["---", ""])
    lines.extend(format_brief_holdings_section(holding_recs, regimes=regimes))
    lines.extend(["---", ""])
    lines.extend(format_research_candidates_section(verdict["quality_picks"]))
    lines.extend(["---", ""])
    lines.extend(format_risk_section(verdict, regimes, market_reports, social))
    lines.extend(["---", ""])
    lines.extend(format_price_table_section(holding_recs, verdict["quality_picks"]))
    lines.extend(format_appendix_section(market_reports, holdings, regimes, social, serenity))

    lines.extend(
        [
            "",
            "**提示**：优先在建议买入区间内分批建仓；触及止损参考位需重新评估。",
        ]
    )
    return "\n".join(lines)
