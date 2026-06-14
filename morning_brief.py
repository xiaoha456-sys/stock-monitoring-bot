#!/usr/bin/env python3
"""Compose the morning brief: conclusion-first, appendix-last."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from market_regime import MarketRegime, format_regime_overview
from portfolio_manager import (
    EnrichedHolding,
    PortfolioAnalysis,
    analyze_portfolio,
    format_portfolio_overview_section,
)
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
)

_MAX_RESEARCH_CANDIDATES = 5


def _is_quality_pick(rec: Recommendation) -> bool:
    thresholds = get_thresholds()
    return rec.action in ("买入", "逢低关注") and rec.score >= thresholds["watch"]


def derive_verdict(
    analysis: PortfolioAnalysis,
    market_reports: dict[str, tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]],
) -> dict[str, Any]:
    add_holdings = [item for item in analysis.holdings if item.portfolio_action == "允许加仓"]
    reduce_holdings = [item for item in analysis.holdings if item.portfolio_action == "降低风险"]
    observe_holdings = [item for item in analysis.holdings if item.portfolio_action == "继续观察"]

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
        "analysis": analysis,
    }


def format_conclusion_section(verdict: dict[str, Any]) -> list[str]:
    lines = ["## 📌 今日结论", ""]
    if verdict["no_action_today"]:
        lines.append("> **今日不操作** — 持仓无需调整，观察池暂无达标候选。")
        lines.append("")
        return lines

    parts: list[str] = []
    if verdict["add_holdings"]:
        names = "、".join(
            _display_ticker(item.recommendation) for item in verdict["add_holdings"][:3]
        )
        parts.append(f"持仓允许加仓 {len(verdict['add_holdings'])} 只（{names}）")
    if verdict["reduce_holdings"]:
        names = "、".join(
            _display_ticker(item.recommendation) for item in verdict["reduce_holdings"][:3]
        )
        parts.append(f"持仓降低风险 {len(verdict['reduce_holdings'])} 只（{names}）")
    if verdict["quality_picks"]:
        parts.append(f"观察池 {len(verdict['quality_picks'])} 个候选值得进一步研究")

    lines.append(f"> **{'；'.join(parts)}**")
    lines.append("")
    return lines


def format_brief_holdings_section(
    verdict: dict[str, Any],
    regimes: dict[str, MarketRegime] | None = None,
) -> list[str]:
    analysis: PortfolioAnalysis = verdict["analysis"]
    if not analysis.holdings:
        return []

    actionable = verdict["add_holdings"] + verdict["reduce_holdings"]
    observe = verdict["observe_holdings"]

    lines = [
        "## 💼 持仓事件",
        "",
        "> 仅列出需关注的持仓；完整仓位与盈亏见「持仓管家」。",
        "",
    ]

    if actionable:
        lines.extend(
            [
                "| 标的 | 现价 | 建议 | 操作要点 |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in actionable:
            rec = item.recommendation
            snap = rec.snapshot
            sign = "+" if snap.change_pct >= 0 else ""
            regime = (regimes or {}).get(_holding_market(rec.ticker))
            today_action = _holding_today_action(rec, regime)
            reason = item.action_reasons[0] if item.action_reasons else today_action
            lines.append(
                f"| {_display_ticker(rec)} | "
                f"{_money(snap.price, snap.currency)} ({sign}{snap.change_pct:.2f}%) | "
                f"**{item.portfolio_action}** | {reason} |"
            )
        lines.append("")

    if observe:
        names = "、".join(_display_ticker(item.recommendation) for item in observe)
        lines.append(f"**继续观察**（{len(observe)} 只）：{names}")
        lines.append("")

    if not actionable and observe:
        lines[2] = "> 今日持仓无需调整。"
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
    analysis: PortfolioAnalysis = verdict["analysis"]
    risks.extend(analysis.alerts)
    risks.extend(analysis.earnings_events)

    for market_key, regime in (regimes or {}).items():
        if regime.label == "弱势":
            risks.append(f"{regime.index_name} 环境偏弱（{regime.label}），轻仓为宜")

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

    lines = ["## ⚠️ 关键风险", ""]
    if not risks:
        lines.append("_暂无突出风险事件。_")
    else:
        seen: set[str] = set()
        for risk in risks:
            if risk in seen:
                continue
            seen.add(risk)
            lines.append(f"- {risk}")
            if len(seen) >= 8:
                break
    lines.append("")
    return lines


def format_price_table_section(
    analysis: PortfolioAnalysis,
    candidates: list[Recommendation],
) -> list[str]:
    holding_rows = list(analysis.holdings)
    candidate_rows: list[Recommendation] = []
    holding_tickers = {item.recommendation.ticker for item in holding_rows}
    for rec in candidates:
        if rec.ticker not in holding_tickers:
            candidate_rows.append(rec)

    if not holding_rows and not candidate_rows:
        return []

    lines: list[str] = []

    if holding_rows:
        lines.extend(
            [
                "## 💰 持仓价格参考",
                "",
                "| 标的 | 现价 | 系统买入 | 系统目标 | 自设目标 | 止损 |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in holding_rows:
            rec = item.recommendation
            snap = rec.snapshot
            user_target = (
                _money(item.user_target, snap.currency) if item.user_target is not None else "—"
            )
            stop = (
                _money(item.user_stop, snap.currency)
                if item.user_stop is not None
                else _money(rec.stop_loss, snap.currency)
            )
            lines.append(
                f"| {_display_ticker(rec)} | {_money(snap.price, snap.currency)} | "
                f"{_money(rec.buy_low, snap.currency)}~{_money(rec.buy_high, snap.currency)} | "
                f"{_money(rec.target_price, snap.currency)} | {user_target} | {stop} |"
            )
        lines.append("")

    if candidate_rows:
        lines.extend(
            [
                "## 💰 候选价格参考",
                "",
                "| 标的 | 现价 | 买入区间 | 目标 | 止损 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for rec in candidate_rows:
            snap = rec.snapshot
            lines.append(
                f"| {_display_ticker(rec)} | {_money(snap.price, snap.currency)} | "
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
        _, holding_errors = holdings
        if holding_errors:
            lines.append("### 持仓数据异常")
            lines.append("")
            for ticker, error in holding_errors.items():
                lines.append(f"- ⚠️ {ticker}：{error}")
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
    analysis = analyze_portfolio(holding_recs)

    verdict = derive_verdict(analysis, market_reports)
    lines = [
        f"# {_combined_report_title()}",
        f"**{report_time:%Y-%m-%d %H:%M}** 悉尼时间",
        "",
        "> 结论前置、技术后置。仅供研究，不构成投资建议。",
        "",
    ]

    lines.extend(format_conclusion_section(verdict))
    lines.extend(["---", ""])
    lines.extend(format_portfolio_overview_section(analysis))
    lines.extend(["---", ""])
    lines.extend(format_brief_holdings_section(verdict, regimes=regimes))
    lines.extend(["---", ""])
    lines.extend(format_research_candidates_section(verdict["quality_picks"]))
    lines.extend(["---", ""])
    lines.extend(format_risk_section(verdict, regimes, market_reports, social))
    lines.extend(["---", ""])
    lines.extend(format_price_table_section(analysis, verdict["quality_picks"]))
    lines.extend(format_appendix_section(market_reports, holdings, regimes, social, serenity))

    lines.extend(
        [
            "",
            "**提示**：优先在建议买入区间内分批建仓；触及止损参考位需重新评估。",
        ]
    )
    return "\n".join(lines)
