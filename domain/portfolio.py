"""Portfolio scan and holdings list for API / app clients."""

from __future__ import annotations

from typing import Any

from domain.dynamic_levels import compute_dynamic_levels
from domain.config import load_config
from domain.orders import format_order_legs, suggest_holding_order
from domain.tickers import normalize_ticker
from market_regime import fetch_all_regimes
from portfolio_manager import analyze_portfolio
from stock_bot import _display_ticker, _holding_market, scan_holdings


def _fallback_holding_item(ticker: str, cfg: dict, error: str | None) -> dict:
    market_key = str(cfg.get("market") or _holding_market(ticker))
    return {
        "ticker": ticker,
        "name": str(cfg.get("name") or ticker),
        "market": market_key,
        "shares": cfg.get("shares"),
        "cost_basis": cfg.get("cost_basis"),
        "target_price": cfg.get("target_price"),
        "stop_loss": cfg.get("stop_loss"),
        "price": None,
        "change_pct": None,
        "currency": {"US": "USD", "CN": "CNY", "AU": "AUD"}.get(market_key, "USD"),
        "market_value": None,
        "pnl_pct": None,
        "pnl_amount": None,
        "weight_pct": None,
        "portfolio_action": "继续观察",
        "action_reasons": ["行情暂不可用，已保存持仓"],
        "order": {
            "side": "观望",
            "legs": [],
            "note": "行情拉取失败，请检查代码格式",
            "display": "—",
        },
        "error": error or "行情暂不可用",
    }


def build_holdings_list() -> tuple[list[dict[str, Any]], dict[str, str]]:
    regimes = fetch_all_regimes()
    recommendations, errors = scan_holdings(regimes=regimes)
    analysis = analyze_portfolio(recommendations, regimes=regimes)
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
        levels = compute_dynamic_levels(rec, regime)
        items.append(
            {
                "ticker": rec.ticker,
                "name": _display_ticker(rec),
                "market": str(cfg.get("market") or market_key),
                "shares": row.shares,
                "cost_basis": row.cost_basis or cfg.get("cost_basis"),
                "target_price": levels.target_price,
                "stop_loss": levels.stop_loss,
                "buy_low": levels.buy_low,
                "buy_high": levels.buy_high,
                "levels_note": levels.note,
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

    seen = {normalize_ticker(item["ticker"]) for item in items}
    for ticker, cfg in holdings_cfg.items():
        norm = normalize_ticker(ticker)
        if norm in seen:
            continue
        items.append(_fallback_holding_item(norm, cfg, errors.get(ticker) or errors.get(norm)))

    items.sort(key=lambda item: -(item.get("weight_pct") or 0))
    return items, errors
