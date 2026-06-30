"""Daily morning brief assembly for API / app clients."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from domain.brief_display import build_display_sections
from domain.paths import SYDNEY
from market_regime import fetch_all_regimes
from morning_brief import compose_email_report, derive_verdict, format_conclusion_items
from portfolio_manager import analyze_portfolio
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
    analysis = analyze_portfolio(holding_recs, regimes=regimes)
    verdict = derive_verdict(analysis, market_reports)

    markdown = compose_email_report(
        market_reports,
        now=now,
        regimes=regimes,
        holdings=holdings_scan,
        radar=None,
        cn_funds=None,
    )

    conclusion_items = format_conclusion_items(verdict)
    conclusion = "；".join(conclusion_items)

    return {
        "generated_at": now.isoformat(),
        "title": "每日持仓操作简报",
        "conclusion": conclusion,
        "conclusion_items": conclusion_items,
        "sections": build_display_sections(verdict, analysis, regimes=regimes),
        "markdown": markdown,
        "holding_errors": holding_errors,
    }
