import unittest

from domain.portfolio import _fallback_holding_item
from domain.tickers import normalize_ticker, validate_ticker
from stock_bot import Recommendation, StockSnapshot


class TickerTests(unittest.TestCase):
    def test_normalize_us(self) -> None:
        self.assertEqual(normalize_ticker("rklb"), "RKLB")

    def test_normalize_cn(self) -> None:
        self.assertEqual(normalize_ticker("002402.sz"), "002402.SZ")

    def test_reject_exchange_code(self) -> None:
        from domain.tickers import validate_ticker

        with self.assertRaises(ValueError):
            validate_ticker("NASDAQ")


class PortfolioFallbackTests(unittest.TestCase):
    def test_fallback_item_has_ticker(self) -> None:
        item = _fallback_holding_item(
            "TEST",
            {"market": "US", "name": "Test", "shares": 10},
            "fetch failed",
        )
        self.assertEqual(item["ticker"], "TEST")
        self.assertEqual(item["error"], "fetch failed")


class DynamicLevelsTests(unittest.TestCase):
    def test_weak_regime_tightens_stop(self) -> None:
        from domain.dynamic_levels import compute_dynamic_levels
        from market_regime import MarketRegime

        snap = StockSnapshot(
            ticker="NVDA",
            price=100.0,
            currency="USD",
            change_pct=0.0,
            week_52_low=80.0,
            week_52_high=120.0,
            week_52_position=50.0,
            rsi_14=50.0,
            sma_50=98.0,
            sma_200=90.0,
            atr_14=5.0,
            headlines=(),
        )
        rec = Recommendation(
            ticker="NVDA",
            action="观望",
            score=60.0,
            stars=3,
            buy_low=95.0,
            buy_high=100.0,
            target_price=110.0,
            stop_loss=88.0,
            reasons=(),
            snapshot=snap,
            name="NVDA",
        )
        regime = MarketRegime(
            market_key="US",
            index_name="SPY",
            ticker="SPY",
            price=500.0,
            change_pct=-1.0,
            trend="空头排列",
            rsi_14=40.0,
            label="弱势",
            stance="谨慎",
            buy_threshold_bonus=4.0,
            top_n_multiplier=0.67,
            summary="test",
        )
        levels = compute_dynamic_levels(rec, regime)
        self.assertGreater(levels.stop_loss, rec.stop_loss)
        self.assertLess(levels.target_price, rec.target_price)


if __name__ == "__main__":
    unittest.main()
