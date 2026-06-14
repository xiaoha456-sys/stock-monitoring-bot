#!/usr/bin/env python3
"""Portfolio manager: cost basis, weights, concentration, and holding actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from stock_bot import MARKET_ORDER, Recommendation, _display_ticker, _holding_market, _money, load_config

SYSTEM_PORTFOLIO_ACTION = {
    "买入": "允许加仓",
    "逢低关注": "允许加仓",
    "观望": "继续观察",
    "减仓": "降低风险",
    "回避": "降低风险",
}

MARKET_LABELS = {"US": "美股", "CN": "A股", "AU": "澳股"}


@dataclass(frozen=True)
class EnrichedHolding:
    recommendation: Recommendation
    shares: float | None
    cost_basis: float | None
    user_target: float | None
    user_stop: float | None
    thesis: str
    market_value: float | None
    pnl_amount: float | None
    pnl_pct: float | None
    weight_pct: float | None
    portfolio_action: str
    action_reasons: tuple[str, ...]


@dataclass(frozen=True)
class PortfolioAnalysis:
    holdings: tuple[EnrichedHolding, ...]
    market_values: dict[str, float]
    market_weights: dict[str, float]
    alerts: tuple[str, ...]
    earnings_events: tuple[str, ...]


def _portfolio_settings() -> dict[str, Any]:
    return load_config().get("portfolio", {})


def _parse_holding_config(info: dict[str, Any]) -> dict[str, Any]:
    cost = info.get("cost_basis")
    if cost is None:
        cost = info.get("buy_price")
    target = info.get("target_price")
    if target is None:
        target = info.get("take_profit_price")
    shares = info.get("shares")
    return {
        "shares": float(shares) if shares not in (None, "") else None,
        "cost_basis": float(cost) if cost not in (None, "") else None,
        "user_target": float(target) if target not in (None, "") else None,
        "user_stop": float(info["stop_loss"]) if info.get("stop_loss") not in (None, "") else None,
        "thesis": str(info.get("thesis", "") or "").strip(),
        "max_weight_pct": float(info["max_weight_pct"])
        if info.get("max_weight_pct") not in (None, "")
        else None,
    }


def _resolve_portfolio_action(
    rec: Recommendation,
    *,
    cost_basis: float | None,
    user_target: float | None,
    user_stop: float | None,
    weight_pct: float | None,
    max_weight_pct: float | None,
    global_max_weight: float,
) -> tuple[str, tuple[str, ...]]:
    price = rec.snapshot.price
    reasons: list[str] = []
    action = SYSTEM_PORTFOLIO_ACTION.get(rec.action, "继续观察")

    if user_stop is not None and price <= user_stop:
        action = "降低风险"
        reasons.append(f"现价已触及/跌破自设止损 {_money(user_stop, rec.snapshot.currency)}")
    elif user_target is not None and price >= user_target:
        action = "降低风险"
        reasons.append(f"现价已达自设目标 {_money(user_target, rec.snapshot.currency)}，可考虑止盈")
    elif cost_basis is not None and price < cost_basis * 0.92:
        if action == "继续观察":
            action = "降低风险"
        reasons.append(f"浮亏超过 8%（成本 {_money(cost_basis, rec.snapshot.currency)}）")

    limit = max_weight_pct if max_weight_pct is not None else global_max_weight
    if weight_pct is not None and weight_pct > limit:
        action = "降低风险"
        reasons.append(f"仓位 {weight_pct:.1f}% 超过上限 {limit:.0f}%")

    if not reasons and action == "允许加仓":
        reasons.append("技术面与量化评分支持回调加仓")
    elif not reasons and action == "降低风险":
        reasons.append("系统评分偏弱或风控触发")
    elif not reasons:
        reasons.append("暂无明确调仓信号")

    return action, tuple(reasons)


def _fetch_upcoming_earnings(ticker: str, within_days: int = 14) -> str | None:
    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        earnings = getattr(stock, "earnings_dates", None)
        if earnings is None or earnings.empty:
            return None
        now = datetime.now().date()
        for index in earnings.index[:6]:
            event_day = index.date() if hasattr(index, "date") else index
            delta = (event_day - now).days
            if 0 <= delta <= within_days:
                return f"{ticker} 财报约 {event_day}（{delta} 天后）"
    except Exception:
        return None
    return None


def analyze_portfolio(
    recommendations: list[Recommendation],
    holdings_config: dict[str, Any] | None = None,
) -> PortfolioAnalysis:
    config = holdings_config if holdings_config is not None else load_config().get("holdings", {})
    settings = _portfolio_settings()
    global_max_weight = float(settings.get("max_position_weight_pct", 25))
    global_max_market = float(settings.get("max_market_weight_pct", 55))
    earnings_days = int(settings.get("earnings_alert_days", 14))

    enriched: list[EnrichedHolding] = []
    market_values: dict[str, float] = {key: 0.0 for key in MARKET_ORDER}
    total_value = 0.0

    for rec in recommendations:
        info = config.get(rec.ticker, {}) or {}
        parsed = _parse_holding_config(info)
        shares = parsed["shares"]
        price = rec.snapshot.price
        market_value = shares * price if shares is not None else None
        if market_value is not None:
            market_key = _holding_market(rec.ticker)
            market_values[market_key] += market_value
            total_value += market_value

        cost_basis = parsed["cost_basis"]
        pnl_amount = None
        pnl_pct = None
        if shares is not None and cost_basis is not None and cost_basis > 0:
            pnl_amount = (price - cost_basis) * shares
            pnl_pct = (price / cost_basis - 1) * 100

        enriched.append(
            EnrichedHolding(
                recommendation=rec,
                shares=shares,
                cost_basis=cost_basis,
                user_target=parsed["user_target"],
                user_stop=parsed["user_stop"],
                thesis=parsed["thesis"],
                market_value=market_value,
                pnl_amount=pnl_amount,
                pnl_pct=pnl_pct,
                weight_pct=None,
                portfolio_action="继续观察",
                action_reasons=(),
            )
        )

    if total_value > 0:
        updated: list[EnrichedHolding] = []
        for item in enriched:
            weight = (item.market_value / total_value * 100) if item.market_value is not None else None
            parsed = _parse_holding_config(config.get(item.recommendation.ticker, {}) or {})
            action, reasons = _resolve_portfolio_action(
                item.recommendation,
                cost_basis=item.cost_basis,
                user_target=item.user_target,
                user_stop=item.user_stop,
                weight_pct=weight,
                max_weight_pct=parsed.get("max_weight_pct"),
                global_max_weight=global_max_weight,
            )
            updated.append(
                EnrichedHolding(
                    recommendation=item.recommendation,
                    shares=item.shares,
                    cost_basis=item.cost_basis,
                    user_target=item.user_target,
                    user_stop=item.user_stop,
                    thesis=item.thesis,
                    market_value=item.market_value,
                    pnl_amount=item.pnl_amount,
                    pnl_pct=item.pnl_pct,
                    weight_pct=weight,
                    portfolio_action=action,
                    action_reasons=reasons,
                )
            )
        enriched = updated
    else:
        updated = []
        for item in enriched:
            parsed = _parse_holding_config(config.get(item.recommendation.ticker, {}) or {})
            action, reasons = _resolve_portfolio_action(
                item.recommendation,
                cost_basis=item.cost_basis,
                user_target=item.user_target,
                user_stop=item.user_stop,
                weight_pct=None,
                max_weight_pct=parsed.get("max_weight_pct"),
                global_max_weight=global_max_weight,
            )
            updated.append(
                EnrichedHolding(
                    recommendation=item.recommendation,
                    shares=item.shares,
                    cost_basis=item.cost_basis,
                    user_target=item.user_target,
                    user_stop=item.user_stop,
                    thesis=item.thesis,
                    market_value=item.market_value,
                    pnl_amount=item.pnl_amount,
                    pnl_pct=item.pnl_pct,
                    weight_pct=None,
                    portfolio_action=action,
                    action_reasons=reasons,
                )
            )
        enriched = updated

    alerts: list[str] = []
    if total_value > 0:
        for market_key, value in market_values.items():
            weight = value / total_value * 100
            if weight > global_max_market:
                alerts.append(
                    f"{MARKET_LABELS.get(market_key, market_key)}仓位 {weight:.1f}% "
                    f"超过市场上限 {global_max_market:.0f}%"
                )
        for item in enriched:
            if item.weight_pct is not None and item.weight_pct > global_max_weight:
                alerts.append(
                    f"{_display_ticker(item.recommendation)} 仓位 {item.weight_pct:.1f}% 偏高"
                )
    else:
        alerts.append("未录入 shares，暂无法计算组合集中度（请在 portfolio_config.json 填写股数）")

    earnings_events: list[str] = []
    for rec in recommendations:
        event = _fetch_upcoming_earnings(rec.ticker, within_days=earnings_days)
        if event:
            earnings_events.append(event)

    return PortfolioAnalysis(
        holdings=tuple(enriched),
        market_values=market_values,
        market_weights={
            key: (market_values[key] / total_value * 100 if total_value > 0 else 0.0)
            for key in MARKET_ORDER
        },
        alerts=tuple(alerts),
        earnings_events=tuple(earnings_events),
    )


def format_portfolio_overview_section(analysis: PortfolioAnalysis) -> list[str]:
    lines = [
        "## 📊 持仓管家",
        "",
        "> 基于成本、仓位与自设目标/止损的风险视图。",
        "",
    ]

    valued = [item for item in analysis.holdings if item.market_value is not None]
    if valued:
        lines.extend(
            [
                "| 标的 | 仓位 | 浮盈亏 | 自设目标 | 自设止损 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for item in valued:
            rec = item.recommendation
            snap = rec.snapshot
            weight = f"{item.weight_pct:.1f}%" if item.weight_pct is not None else "—"
            if item.pnl_pct is not None and item.pnl_amount is not None:
                sign = "+" if item.pnl_pct >= 0 else ""
                pnl = (
                    f"{sign}{item.pnl_pct:.1f}% "
                    f"({sign}{_money(abs(item.pnl_amount), snap.currency)})"
                )
            else:
                pnl = "未录入成本"
            user_target = (
                _money(item.user_target, snap.currency) if item.user_target is not None else "—"
            )
            user_stop = _money(item.user_stop, snap.currency) if item.user_stop is not None else "—"
            lines.append(
                f"| {_display_ticker(rec)} | {weight} | {pnl} | {user_target} | {user_stop} |"
            )
        lines.append("")

        market_parts = [
            f"{MARKET_LABELS.get(key, key)} {analysis.market_weights.get(key, 0):.0f}%"
            for key in MARKET_ORDER
            if analysis.market_values.get(key, 0) > 0
        ]
        if market_parts:
            lines.append(f"**市场分布**：{' · '.join(market_parts)}")
            lines.append("")

    if analysis.alerts:
        lines.append("**集中度提示**")
        lines.append("")
        for alert in analysis.alerts:
            lines.append(f"- {alert}")
        lines.append("")

    if analysis.earnings_events:
        lines.append("**近期财报**")
        lines.append("")
        for event in analysis.earnings_events:
            lines.append(f"- {event}")
        lines.append("")

    return lines
