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
    format_cash_constraints_section,
    market_cash_mode,
)
from tuning import get_thresholds
from domain.orders import format_merged_holdings_section, format_order_legs, suggest_holding_order
from cn_tradable import is_cn_restricted_board

from stock_bot import (
    MARKET_ORDER,
    Recommendation,
    _combined_report_title,
    _display_ticker,
    _holding_market,
    _market_section_lines,
    _market_section_note,
    _money,
    _regime_section_note,
)

_MAX_RESEARCH_CANDIDATES = 5


def _is_quality_pick(rec: Recommendation) -> bool:
    thresholds = get_thresholds()
    return rec.action in ("买入", "逢低关注") and rec.score >= thresholds["watch"]


def _holding_market_key(item: EnrichedHolding) -> str:
    return _holding_market(item.recommendation.ticker)


def _quality_picks_for_market(
    market_reports: dict[str, tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]],
    market_key: str,
    *,
    exclude_tickers: set[str] | None = None,
) -> list[Recommendation]:
    block = market_reports.get(market_key)
    if not block:
        return []
    picks, _, _, _ = block
    excluded = exclude_tickers or set()
    return [
        rec
        for rec in picks
        if _is_quality_pick(rec)
        and rec.ticker not in excluded
        and not (market_key == "CN" and is_cn_restricted_board(rec.ticker))
    ]


def derive_verdict(
    analysis: PortfolioAnalysis,
    market_reports: dict[str, tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]],
) -> dict[str, Any]:
    add_holdings = [item for item in analysis.holdings if item.portfolio_action == "允许加仓"]
    rotate_holdings = [item for item in analysis.holdings if item.portfolio_action == "置换加仓"]
    reduce_holdings = [item for item in analysis.holdings if item.portfolio_action == "降低风险"]
    observe_holdings = [item for item in analysis.holdings if item.portfolio_action == "继续观察"]

    holding_tickers = {item.recommendation.ticker for item in analysis.holdings}
    quality_picks: list[Recommendation] = []
    rotation_picks: list[Recommendation] = []
    deploy_picks: list[Recommendation] = []
    for market_key in MARKET_ORDER:
        picks = _quality_picks_for_market(
            market_reports,
            market_key,
            exclude_tickers=holding_tickers,
        )
        for rec in picks:
            quality_picks.append(rec)
            if market_cash_mode(market_key) == "rotate_only":
                rotation_picks.append(rec)
            else:
                deploy_picks.append(rec)
    quality_picks.sort(key=lambda item: item.score, reverse=True)
    quality_picks = quality_picks[:_MAX_RESEARCH_CANDIDATES]
    rotation_picks.sort(key=lambda item: item.score, reverse=True)
    deploy_picks.sort(key=lambda item: item.score, reverse=True)

    rotation_plans: list[dict[str, Any]] = []
    for market_key in MARKET_ORDER:
        if market_cash_mode(market_key) != "rotate_only":
            continue
        sellers = [
            item
            for item in reduce_holdings
            if _holding_market_key(item) == market_key
        ]
        buyers = [
            rec
            for rec in rotation_picks
            if _holding_market(rec.ticker) == market_key
        ][:2]
        if sellers and buyers:
            rotation_plans.append(
                {
                    "market_key": market_key,
                    "sellers": sellers[:3],
                    "buyers": buyers,
                    "analysis": analysis,
                }
            )

    no_action = (
        not add_holdings
        and not rotate_holdings
        and not reduce_holdings
        and not quality_picks
    )
    return {
        "no_action_today": no_action,
        "add_holdings": add_holdings,
        "rotate_holdings": rotate_holdings,
        "reduce_holdings": reduce_holdings,
        "observe_holdings": observe_holdings,
        "quality_picks": quality_picks,
        "rotation_picks": rotation_picks,
        "deploy_picks": deploy_picks,
        "rotation_plans": rotation_plans,
        "analysis": analysis,
    }


def format_conclusion_items(verdict: dict[str, Any]) -> list[str]:
    if verdict["no_action_today"]:
        return ["今日不操作 — 持仓无需调整，观察池暂无达标候选。"]

    parts: list[str] = []
    if verdict["add_holdings"]:
        names = "、".join(
            _display_ticker(item.recommendation) for item in verdict["add_holdings"][:3]
        )
        parts.append(f"可加仓 {len(verdict['add_holdings'])} 只：{names}")
    if verdict["rotate_holdings"]:
        names = "、".join(
            _display_ticker(item.recommendation) for item in verdict["rotate_holdings"][:3]
        )
        parts.append(f"置换加仓 {len(verdict['rotate_holdings'])} 只：{names}（需先减仓）")
    if verdict["reduce_holdings"]:
        names = "、".join(
            _display_ticker(item.recommendation) for item in verdict["reduce_holdings"][:3]
        )
        parts.append(f"降低风险 {len(verdict['reduce_holdings'])} 只：{names}")
    if verdict["deploy_picks"]:
        parts.append(f"美股观察池 {len(verdict['deploy_picks'])} 个候选可新开仓")
    if verdict["rotation_picks"]:
        parts.append(f"A股/澳股 {len(verdict['rotation_picks'])} 个置换候选")
    return parts


def format_conclusion_section(verdict: dict[str, Any]) -> list[str]:
    lines = ["## 📌 今日结论", ""]
    items = format_conclusion_items(verdict)
    if verdict["no_action_today"]:
        lines.append(f"> **{items[0]}**")
    else:
        lines.append("**今日要事**")
        lines.append("")
        for item in items:
            lines.append(f"- {item}")
    lines.append("")
    return lines


def format_brief_holdings_section(
    verdict: dict[str, Any],
    regimes: dict[str, MarketRegime] | None = None,
) -> list[str]:
    analysis: PortfolioAnalysis = verdict["analysis"]
    if not analysis.holdings:
        return []

    actionable = (
        verdict["add_holdings"]
        + verdict["rotate_holdings"]
        + verdict["reduce_holdings"]
    )
    observe = verdict["observe_holdings"]

    lines = [
        "## 💼 持仓事件",
        "",
        "> 仅列出需关注的持仓。",
        "",
    ]

    if actionable:
        lines.extend(
            [
                "| 标的 | 现价 | 建议 | 原因 |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in actionable:
            rec = item.recommendation
            snap = rec.snapshot
            sign = "+" if snap.change_pct >= 0 else ""
            reason = item.action_reasons[0] if item.action_reasons else "—"
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


def format_research_candidates_section(
    candidates: list[Recommendation],
    *,
    deploy_picks: list[Recommendation] | None = None,
    rotation_picks: list[Recommendation] | None = None,
) -> list[str]:
    deploy_picks = deploy_picks or []
    rotation_picks = rotation_picks or []
    if not candidates and not deploy_picks and not rotation_picks:
        return [
            "## 🔍 值得研究",
            "",
            "_观察池今日无达标候选。_",
            "",
        ]

    lines = [
        "## 🔍 值得研究",
        "",
        "> 从三市场观察池筛选的候选；美股可用现金直接买入，A股/澳股需减仓置换。"
        " A股已排除科创板/创业板个股，亦可参考下方长期基金。",
        "",
    ]

    def _append_pick_group(title: str, picks: list[Recommendation]) -> None:
        if not picks:
            return
        lines.append(f"**{title}**")
        lines.append("")
        for index, rec in enumerate(picks[:_MAX_RESEARCH_CANDIDATES], start=1):
            snap = rec.snapshot
            sign = "+" if snap.change_pct >= 0 else ""
            strategy = f" · {rec.strategy}" if rec.strategy else ""
            lines.append(
                f"{index}. **{_display_ticker(rec)}** · {rec.score:.0f}分{strategy} · "
                f"{_money(snap.price, snap.currency)} ({sign}{snap.change_pct:.2f}%) · "
                f"买 {_money(rec.buy_low, snap.currency)}~{_money(rec.buy_high, snap.currency)}"
            )
        lines.append("")

    _append_pick_group("美股可新开仓", deploy_picks)
    _append_pick_group("A股/澳股置换候选（需先减仓）", rotation_picks)

    if not deploy_picks and not rotation_picks:
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


def format_rotation_plan_section(rotation_plans: list[dict[str, Any]]) -> list[str]:
    if not rotation_plans:
        return []

    from portfolio_manager import MARKET_LABELS

    lines = [
        "## 🔄 减仓置换建议",
        "",
        "> A股/澳股无闲置资金：先挂卖单释放资金，再挂买单（A股100股整数倍）。",
        "",
    ]
    for plan in rotation_plans:
        market_key = plan["market_key"]
        label = MARKET_LABELS.get(market_key, market_key)
        sellers = plan["sellers"]
        buyers = plan["buyers"]
        sell_names = "、".join(_display_ticker(item.recommendation) for item in sellers)
        buy_names = "、".join(_display_ticker(rec) for rec in buyers)
        lines.append(f"**{label}**：减 {sell_names} → 换 {buy_names}")
        for item in sellers:
            rec = item.recommendation
            snap = rec.snapshot
            order = suggest_holding_order(item, analysis=plan.get("analysis"))
            lines.append(
                f"- 卖 {_display_ticker(rec)}：{format_order_legs(order, snap.currency)}"
            )
        for rec in buyers:
            snap = rec.snapshot
            lines.append(
                f"- 买 {_display_ticker(rec)}：挂 "
                f"{_money(rec.buy_low, snap.currency)}~{_money(rec.buy_high, snap.currency)}"
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


def format_holdings_email_section(
    analysis: PortfolioAnalysis,
    regimes: dict[str, MarketRegime] | None = None,
) -> list[str]:
    lines = [
        "# 一、持仓",
        "",
    ]
    merged = format_merged_holdings_section(analysis, regimes=regimes)
    if merged:
        lines.extend(merged)
    else:
        lines.append("_暂无持仓记录。_")
        lines.append("")
    return lines


def format_cash_email_section() -> list[str]:
    body = format_cash_constraints_section()
    if not body:
        return []
    lines = [
        "# 二、资金",
        "",
        "> 各市场可用资金与操作模式。",
        "",
    ]
    for line in body:
        if line.startswith("## 💵") or line.startswith("> 各市场可用资金与操作模式"):
            continue
        lines.append(line)
    return lines


def compose_brief_sections(
    verdict: dict[str, Any],
    analysis: PortfolioAnalysis,
    market_reports: dict[str, tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]],
    regimes: dict[str, MarketRegime] | None = None,
    holdings: tuple[list[Recommendation], dict[str, str]] | None = None,
    social: Any | None = None,
    serenity: Any | None = None,
    potential: tuple[list[Any], dict[str, str]] | None = None,
    research: list[Any] | None = None,
    radar: tuple[list[Any], dict[str, str]] | None = None,
    cn_funds: tuple[list[Recommendation], dict[str, str]] | None = None,
) -> list[str]:
    lines: list[str] = [
        "# 三、简报",
        "",
        "> 市场结论、候选研究与技术附录。",
        "",
    ]
    lines.extend(format_conclusion_section(verdict))
    lines.append("")
    if radar is not None:
        from radar import format_market_radar_section

        picks, errors = radar
        lines.extend(format_market_radar_section(picks, errors))
        lines.append("")
    lines.extend(
        format_research_candidates_section(
            verdict["quality_picks"],
            deploy_picks=verdict["deploy_picks"],
            rotation_picks=verdict["rotation_picks"],
        )
    )
    lines.append("")
    lines.extend(format_rotation_plan_section(verdict["rotation_plans"]))
    if verdict["rotation_plans"]:
        lines.append("")
    if cn_funds is not None:
        from cn_funds import format_cn_funds_section

        fund_picks, fund_errors = cn_funds
        lines.extend(format_cn_funds_section(fund_picks, fund_errors))
        if fund_picks:
            lines.append("")
    if potential is not None:
        from potential_screener import format_potential_radar_section

        picks, errors = potential
        lines.extend(format_potential_radar_section(picks, errors))
        lines.append("")
    if research:
        from research_agent import format_research_agent_section

        lines.extend(format_research_agent_section(research))
        lines.append("")
    lines.extend(format_risk_section(verdict, regimes, market_reports, social))
    lines.append("")
    lines.extend(format_price_table_section(analysis, verdict["quality_picks"]))
    lines.extend(format_appendix_section(market_reports, holdings, regimes, social, serenity))
    lines.extend(
        [
            "",
            "**提示**：优先在建议买入区间内分批建仓；触及止损参考位需重新评估。",
        ]
    )
    return lines


def compose_email_report(
    market_reports: dict[str, tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]],
    now: datetime | None = None,
    regimes: dict[str, MarketRegime] | None = None,
    holdings: tuple[list[Recommendation], dict[str, str]] | None = None,
    social: Any | None = None,
    serenity: Any | None = None,
    potential: tuple[list[Any], dict[str, str]] | None = None,
    research: list[Any] | None = None,
    radar: tuple[list[Any], dict[str, str]] | None = None,
    cn_funds: tuple[list[Recommendation], dict[str, str]] | None = None,
) -> str:
    from zoneinfo import ZoneInfo

    sydney = ZoneInfo("Australia/Sydney")
    report_time = (now or datetime.now(sydney)).astimezone(sydney)
    holding_recs = holdings[0] if holdings else []
    analysis = analyze_portfolio(holding_recs, regimes=regimes)
    verdict = derive_verdict(analysis, market_reports)

    lines = [
        f"# {_combined_report_title()}",
        f"**{report_time:%Y-%m-%d %H:%M}** 悉尼时间",
        "",
        "> 持仓 + 资金 + 简报。仅供研究，不构成投资建议。",
        "",
    ]
    lines.extend(format_holdings_email_section(analysis, regimes=regimes))
    lines.extend(["", "---", ""])
    cash_lines = format_cash_email_section()
    if cash_lines:
        lines.extend(cash_lines)
        lines.extend(["", "---", ""])
    lines.extend(
        compose_brief_sections(
            verdict,
            analysis,
            market_reports,
            regimes=regimes,
            holdings=holdings,
            social=social,
            serenity=serenity,
            potential=potential,
            research=research,
            radar=radar,
            cn_funds=cn_funds,
        )
    )
    return "\n".join(lines)


def compose_morning_brief(
    market_reports: dict[str, tuple[list[Recommendation], list[Recommendation], dict[str, str], dict[str, Any]]],
    now: datetime | None = None,
    regimes: dict[str, MarketRegime] | None = None,
    holdings: tuple[list[Recommendation], dict[str, str]] | None = None,
    social: Any | None = None,
    serenity: Any | None = None,
    potential: tuple[list[Any], dict[str, str]] | None = None,
    research: list[Any] | None = None,
    radar: tuple[list[Any], dict[str, str]] | None = None,
    cn_funds: tuple[list[Recommendation], dict[str, str]] | None = None,
) -> str:
    """Brief-only markdown (part 3); email push uses compose_email_report."""
    from zoneinfo import ZoneInfo

    sydney = ZoneInfo("Australia/Sydney")
    report_time = (now or datetime.now(sydney)).astimezone(sydney)
    holding_recs = holdings[0] if holdings else []
    analysis = analyze_portfolio(holding_recs, regimes=regimes)
    verdict = derive_verdict(analysis, market_reports)
    lines = [
        f"# {_combined_report_title()}",
        f"**{report_time:%Y-%m-%d %H:%M}** 悉尼时间",
        "",
        "> 结论前置、技术后置。仅供研究，不构成投资建议。",
        "",
    ]
    brief_body = compose_brief_sections(
        verdict,
        analysis,
        market_reports,
        regimes=regimes,
        holdings=holdings,
        social=social,
        serenity=serenity,
        potential=potential,
        research=research,
        radar=radar,
        cn_funds=cn_funds,
    )
    # Drop the part-3 heading; email report keeps it inside compose_brief_sections.
    lines.extend(line for line in brief_body if not line.startswith("# 三、简报"))
    return "\n".join(lines)
