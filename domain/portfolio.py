"""Portfolio scan and holdings list for API / app clients."""

from __future__ import annotations

from typing import Any

from domain.config import load_config
from domain.orders import format_order_legs, suggest_holding_order
from market_regime import fetch_all_regimes
from portfolio_manager import analyze_portfolio
from stock_bot import _display_ticker, _holding_market, scan_holdings


def build_holdings_list() -> tuple[list[dict[str, Any]], dict[str, str]]:
    regimes = fetch_all_regimes()
    recommendations, errors = scan_holdings(regimes=regimes)
    analysis = analyze_portfolio(recommendations)
    config = load_config()
    holdings_cfg = config.get("holdings", {})

    items: list[dict[str, Any]] = []
    for row in analysis.holdings:
        rec = row.recommendation
        snap = rec.snapshot
        market_key = _holding_market(rec.ticker)
        regime = regimes.get(market_key)
        order = suggest_holding_order(row, regime=regime, analysis=analysis)
        cfg = holdings_cfg.get(rec.ticker, {})
        items.append(
            {
                "ticker": rec.ticker,
                "name": _display_ticker(rec),
                "market": str(cfg.get("market") or market_key),
                "shares": row.shares,
                "cost_basis": row.cost_basis or cfg.get("cost_basis"),
                "target_price": cfg.get("target_price"),
                "stop_loss": cfg.get("stop_loss"),
                "price": snap.price,
                "change_pct": snap.change_pct,
                "currency": snap.currency,
                "market_value": row.market_value,
                "pnl_pct": row.pnl_pct,
                "pnl_amount": row.pnl_amount,
                "weight_pct": row.weight_pct,
                "portfolio_action": row.portfolio_action,
                "action_reasons": list(row.action_reasons),
                "order": {
                    "side": order.side,
                    "legs": [{"price": leg.price, "shares": leg.shares} for leg in order.legs],
                    "note": order.note,
                    "display": format_order_legs(order, snap.currency),
                },
                "error": errors.get(rec.ticker),
            }
        )

    items.sort(key=lambda item: -(item.get("weight_pct") or 0))
    return items, errors
