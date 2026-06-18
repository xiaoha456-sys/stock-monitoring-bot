import unittest
from typing import Optional

from cn_tradable import (
    filter_tradable_cn_tickers,
    is_cn_restricted_board,
    tradable_filter_note,
)
from holding_orders import (
    OrderLeg,
    format_order_legs,
    sell_shares_count,
    suggest_holding_order,
    _split_order_legs,
)
from portfolio_manager import EnrichedHolding, PortfolioAnalysis
from stock_bot import Recommendation, StockSnapshot


def _item(
    *,
    ticker: str = "NVDA",
    action: str = "观望",
    portfolio_action: str = "继续观察",
    price: float = 100.0,
    buy_low: float = 95.0,
    buy_high: float = 100.0,
    target: float = 110.0,
    stop: float = 90.0,
    shares: float = 100,
    weight: float = 10.0,
    pnl_pct: Optional[float] = 0.0,
    user_target: Optional[float] = None,
    currency: str = "USD",
) -> EnrichedHolding:
    snap = StockSnapshot(
        ticker=ticker,
        price=price,
        currency=currency,
        change_pct=1.0,
        week_52_low=80.0,
        week_52_high=120.0,
        week_52_position=50.0,
        rsi_14=55.0,
        sma_50=95.0,
        sma_200=90.0,
        atr_14=3.0,
        headlines=(),
    )
    rec = Recommendation(
        ticker=ticker,
        action=action,
        score=70.0,
        stars=3,
        buy_low=buy_low,
        buy_high=buy_high,
        target_price=target,
        stop_loss=stop,
        reasons=("test",),
        snapshot=snap,
        name="测试",
    )
    return EnrichedHolding(
        recommendation=rec,
        shares=shares,
        cost_basis=90.0,
        user_target=user_target,
        user_stop=stop,
        thesis="test",
        market_value=shares * price,
        pnl_amount=100.0,
        pnl_pct=pnl_pct,
        weight_pct=weight,
        portfolio_action=portfolio_action,
        action_reasons=(),
    )


class CnTradableTests(unittest.TestCase):
    def test_restricted_boards(self):
        self.assertTrue(is_cn_restricted_board("688981.SS"))
        self.assertTrue(is_cn_restricted_board("300750.SZ"))
        self.assertFalse(is_cn_restricted_board("600519.SS"))
        self.assertFalse(is_cn_restricted_board("002402.SZ"))

    def test_filter_watchlist(self):
        tickers = ["600519.SS", "688981.SS", "300750.SZ", "000858.SZ"]
        self.assertEqual(
            filter_tradable_cn_tickers(tickers),
            ["600519.SS", "000858.SZ"],
        )

    def test_filter_note(self):
        self.assertIn("科创板", tradable_filter_note())


class HoldingOrderTests(unittest.TestCase):
    def test_reduce_risk_suggests_sell_with_shares(self):
        order = suggest_holding_order(_item(portfolio_action="降低风险", action="减仓", shares=400))
        self.assertEqual(order.side, "卖出")
        self.assertEqual(len(order.legs), 1)
        self.assertEqual(order.legs[0].shares, 100)

    def test_allow_add_suggests_split_buy(self):
        order = suggest_holding_order(_item(portfolio_action="允许加仓", action="逢低关注"))
        self.assertEqual(order.side, "买入")
        self.assertGreaterEqual(len(order.legs), 1)
        self.assertGreater(order.legs[0].shares, 0)

    def test_cn_sell_rounds_to_hundred_lot(self):
        item = _item(
            ticker="002402.SZ",
            portfolio_action="降低风险",
            action="减仓",
            shares=3900,
            currency="CNY",
        )
        self.assertEqual(sell_shares_count(item, "CN"), 900)

    def test_rotate_add_without_proceeds_has_no_legs(self):
        order = suggest_holding_order(_item(portfolio_action="置换加仓", action="买入"))
        self.assertEqual(order.side, "买入")
        self.assertEqual(order.legs, ())

    def test_observe_no_order(self):
        order = suggest_holding_order(_item(portfolio_action="继续观察", action="观望"))
        self.assertEqual(order.side, "观望")
        self.assertEqual(order.legs, ())

    def test_format_order_legs(self):
        order_legs = (
            OrderLeg(price=188.6, shares=6),
            OrderLeg(price=187.7, shares=7),
        )
        from holding_orders import HoldingOrder

        text = format_order_legs(HoldingOrder("买入", order_legs, ""), "USD")
        self.assertIn("× 6股", text)
        self.assertIn("× 7股", text)

    def test_split_cn_buy_legs(self):
        legs = _split_order_legs(1000, 23.0, 23.5, "CN")
        self.assertEqual(sum(leg.shares for leg in legs), 1000)
        self.assertTrue(all(leg.shares % 100 == 0 for leg in legs))


if __name__ == "__main__":
    unittest.main()
