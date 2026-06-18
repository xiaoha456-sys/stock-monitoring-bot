#!/usr/bin/env python3
"""Today's limit-order suggestions for configured holdings."""

from __future__ import annotations

from dataclasses import dataclass

from market_regime import MarketRegime
from portfolio_manager import (
    EnrichedHolding,
    PortfolioAnalysis,
    MARKET_LABELS,
    format_market_cash_amount,
    get_market_cash_config,
    market_cash_mode,
)

from stock_bot import MARKET_ORDER, Recommendation, _display_ticker, _holding_market, _money, load_config


@dataclass(frozen=True)
class OrderLeg:
    price: float
    shares: int


@dataclass(frozen=True)
class HoldingOrder:
    side: str
    legs: tuple[OrderLeg, ...]
    note: str

    @property
    def primary_price(self) -> float | None:
        return self.legs[0].price if self.legs else None

    @property
    def secondary_price(self) -> float | None:
        if len(self.legs) < 2:
            return None
        return self.legs[1].price


def _round_price(price: float, currency: str) -> float:
    return round(price, 2)


def _lot_size(market_key: str) -> int:
    return 100 if market_key == "CN" else 1


def _round_shares(qty: float, market_key: str) -> int:
    lot = _lot_size(market_key)
    if qty <= 0:
        return 0
    rounded = int(qty // lot) * lot
    if rounded <= 0:
        return lot if market_key == "CN" else 1
    return rounded


def _us_cash_usd() -> float:
    entry = get_market_cash_config().get("US", {})
    amount = float(entry.get("available", 0) or 0)
    fx = float(load_config().get("portfolio", {}).get("fx", {}).get("AUD_USD", 0.65) or 0.65)
    currency = str(entry.get("currency", "USD")).upper()
    if currency == "AUD":
        return amount * fx
    return amount


def _buy_limit_prices(rec: Recommendation) -> tuple[float, float]:
    snap = rec.snapshot
    mid = (rec.buy_low + rec.buy_high) / 2
    if snap.price > rec.buy_high:
        return _round_price(rec.buy_low, snap.currency), _round_price(mid, snap.currency)
    return _round_price(mid, snap.currency), _round_price(rec.buy_high, snap.currency)


def _sell_limit_price(item: EnrichedHolding, rec: Recommendation) -> float:
    snap = rec.snapshot
    target = item.user_target if item.user_target is not None else rec.target_price
    if snap.price >= target * 0.98:
        return _round_price(snap.price * 0.998, snap.currency)
    rebound = min(target, snap.price * 1.015)
    return _round_price(rebound, snap.currency)


def _sell_ratio(item: EnrichedHolding, rec: Recommendation) -> float:
    ratio = 0.25
    if item.weight_pct is not None and item.weight_pct >= 30:
        ratio = 0.30
    if item.pnl_pct is not None and item.pnl_pct < -10:
        ratio = max(ratio, 0.30)
    if rec.action == "回避":
        ratio = 0.50
    return ratio


def sell_shares_count(
    item: EnrichedHolding,
    market_key: str | None = None,
) -> int:
    shares = int(item.shares or 0)
    if shares <= 0:
        return 0
    market_key = market_key or _holding_market(item.recommendation.ticker)
    return min(shares, _round_shares(shares * _sell_ratio(item, item.recommendation), market_key))


def _split_order_legs(
    total_shares: int,
    low: float,
    high: float,
    market_key: str,
) -> tuple[OrderLeg, ...]:
    if total_shares <= 0:
        return ()
    lot = _lot_size(market_key)
    if total_shares < 2 * lot or abs(low - high) < 1e-9:
        return (OrderLeg(price=low, shares=total_shares),)

    first = _round_shares(total_shares * 0.55, market_key)
    second = total_shares - first
    if second < lot:
        first = total_shares - lot
        second = lot
    if market_key == "CN" and second % 100 != 0:
        second = (second // 100) * 100
        first = total_shares - second
    return (OrderLeg(price=low, shares=first), OrderLeg(price=high, shares=second))


def _rotation_proceeds(analysis: PortfolioAnalysis | None, market_key: str) -> float:
    if analysis is None:
        return 0.0
    total = 0.0
    for peer in analysis.holdings:
        if _holding_market(peer.recommendation.ticker) != market_key:
            continue
        if peer.portfolio_action != "降低风险":
            continue
        qty = sell_shares_count(peer, market_key)
        if qty <= 0:
            continue
        price = _sell_limit_price(peer, peer.recommendation)
        total += qty * price
    return total


def _buy_shares_count(
    item: EnrichedHolding,
    limit_price: float,
    market_key: str,
    analysis: PortfolioAnalysis | None = None,
) -> int:
    if limit_price <= 0:
        return 0

    if item.portfolio_action == "置换加仓":
        proceeds = _rotation_proceeds(analysis, market_key)
        if proceeds <= 0:
            return 0
        buyers = [
            peer
            for peer in (analysis.holdings if analysis else [])
            if _holding_market(peer.recommendation.ticker) == market_key
            and peer.portfolio_action in ("置换加仓", "允许加仓")
        ]
        if not buyers:
            buyers = [item]
        share = proceeds / max(len(buyers), 1)
        return _round_shares(share / limit_price, market_key)

    if market_key == "US" and market_cash_mode(market_key) == "deploy":
        budget = _us_cash_usd() * 0.12
        return max(1, int(budget // limit_price))

    return 0


def format_order_legs(order: HoldingOrder, currency: str) -> str:
    if not order.legs:
        return "—"
    return " + ".join(
        f"{_money(leg.price, currency)} × {leg.shares}股" for leg in order.legs
    )


def suggest_holding_order(
    item: EnrichedHolding,
    regime: MarketRegime | None = None,
    analysis: PortfolioAnalysis | None = None,
) -> HoldingOrder:
    rec = item.recommendation
    snap = rec.snapshot
    market_key = _holding_market(rec.ticker)
    regime_note = "；大盘偏弱，缩小仓位" if regime and regime.label == "弱势" else ""

    if item.portfolio_action == "降低风险":
        sell_price = _sell_limit_price(item, rec)
        qty = sell_shares_count(item, market_key)
        legs = (OrderLeg(price=sell_price, shares=qty),) if qty > 0 else ()
        if rec.action in ("减仓", "回避") or (item.pnl_pct is not None and item.pnl_pct < -10):
            note = f"反弹减仓；止损参考 {_money(item.user_stop or rec.stop_loss, snap.currency)}{regime_note}"
        elif item.user_target and snap.price >= item.user_target * 0.98:
            note = f"已达自设目标附近，可考虑止盈{regime_note}"
        else:
            note = f"降低集中度或技术偏弱，挂反弹卖单{regime_note}"
        return HoldingOrder(side="卖出", legs=legs, note=note)

    if item.portfolio_action in ("允许加仓", "置换加仓"):
        low, high = _buy_limit_prices(rec)
        total = _buy_shares_count(item, low, market_key, analysis=analysis)
        legs = _split_order_legs(total, low, high, market_key)
        if item.portfolio_action == "置换加仓":
            if total <= 0:
                note = f"无闲置资金，需先减仓释放资金后再挂买单{regime_note}"
            else:
                note = f"无闲置资金，按减仓回笼资金估算；需先卖后买{regime_note}"
        elif snap.price > rec.buy_high:
            note = f"现价偏高，等回踩成交{regime_note}"
        else:
            note = f"可在买入区间内分批挂单{regime_note}"
        return HoldingOrder(side="买入", legs=legs, note=note)

    return HoldingOrder(
        side="观望",
        legs=(),
        note=f"今日不挂单，持有观察{regime_note}",
    )


def format_holding_orders_section(
    analysis: PortfolioAnalysis,
    regimes: dict[str, MarketRegime] | None = None,
) -> list[str]:
    valued = [
        item
        for item in analysis.holdings
        if item.shares is not None and item.market_value is not None
    ]
    if not valued:
        return []

    lines = [
        "## 📋 持仓今日挂单",
        "",
        "> 给出今日可执行的限价与股数；美股可现金买入，A股/澳股仅减仓置换（A股100股整数倍）。",
        "",
        "| 标的 | 现价 | 操作 | 挂单明细 | 说明 |",
        "| --- | --- | --- | --- | --- |",
    ]

    for market_key in MARKET_ORDER:
        group = [item for item in valued if _holding_market(item.recommendation.ticker) == market_key]
        if not group:
            continue
        label = MARKET_LABELS.get(market_key, market_key)
        lines.append(f"| **{label}** | | | | |")
        for item in sorted(group, key=lambda h: -(h.weight_pct or 0)):
            rec = item.recommendation
            snap = rec.snapshot
            sign = "+" if snap.change_pct >= 0 else ""
            regime = (regimes or {}).get(market_key)
            order = suggest_holding_order(item, regime=regime, analysis=analysis)
            lines.append(
                f"| {_display_ticker(rec)} | "
                f"{_money(snap.price, snap.currency)} ({sign}{snap.change_pct:.2f}%) | "
                f"**{order.side}** | {format_order_legs(order, snap.currency)} | {order.note} |"
            )

    cash_note_parts = []
    us_cash = format_market_cash_amount("US")
    if float(get_market_cash_config().get("US", {}).get("available", 0) or 0) > 0:
        cash_note_parts.append(f"美股可用 {us_cash}")
    cash_note_parts.append("A股/澳股：先挂卖单，成交后再挂买单")
    lines.append("")
    lines.append(f"**资金提示**：{' · '.join(cash_note_parts)}")
    lines.append("")
    return lines
