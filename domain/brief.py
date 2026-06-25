"""Daily morning brief assembly for API / app clients."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from domain.orders import format_holding_orders_section
from domain.paths import SYDNEY
from market_regime import fetch_all_regimes
from morning_brief import compose_morning_brief, derive_verdict, format_conclusion_section
from portfolio_manager import (
    analyze_portfolio,
    format_cash_constraints_section,
    format_portfolio_overview_section,
)
from stock_bot import MARKET_ORDER, scan_holdings, scan_market


def build_today_brief() -> dict[str, Any]:
    now = datetime.now(SYDNEY)
    regimes = fetch_all_regimes()
    market_reports: dict[str, Any] = {}
    for market_key in MARKET_ORDER:
        picks, others, errors, extras = scan_market(market_key, regimes.get(market_key))
        market_reports[market_key] = (picks, others, errors, extras)

    holdings_scan = scan_holdings(regimes=regimes)
    holding_recs, holding_errors = holdings_scan
    analysis = analyze_portfolio(holding_recs)
    verdict = derive_verdict(analysis, market_reports)

    markdown = compose_morning_brief(
        market_reports,
        now=now,
        regimes=regimes,
        holdings=holdings_scan,
        radar=None,
        cn_funds=None,
    )

    conclusion_lines = format_conclusion_section(verdict)
    conclusion = ""
    for line in conclusion_lines:
        if line.startswith("> **"):
            conclusion = line.replace("> **", "").replace("**", "").strip()
            break

    sections: list[dict[str, Any]] = []

    order_lines = format_holding_orders_section(analysis, regimes=regimes)
    if order_lines:
        sections.append({"title": "今日挂单", "lines": [l for l in order_lines if l and not l.startswith("|---")]})

    cash_lines = format_cash_constraints_section()
    if cash_lines:
        sections.append({"title": "资金约束", "lines": cash_lines[2:8]})

    overview_lines = format_portfolio_overview_section(analysis)
    if overview_lines:
        sections.append({"title": "持仓管家", "lines": overview_lines[3:12]})

    return {
        "generated_at": now.isoformat(),
        "title": "每日持仓操作简报",
        "conclusion": conclusion or "今日简报已生成",
        "sections": sections,
        "markdown": markdown,
        "holding_errors": holding_errors,
    }
