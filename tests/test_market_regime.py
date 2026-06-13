import unittest

from market_regime import _classify_regime, select_picks_with_regime
from stock_bot import Recommendation, StockSnapshot, build_recommendation


def _sample_snapshot(**overrides) -> StockSnapshot:
    base = dict(
        ticker="NVDA",
        price=150.0,
        currency="USD",
        change_pct=1.25,
        week_52_low=90.0,
        week_52_high=160.0,
        week_52_position=60.0,
        rsi_14=55.0,
        sma_50=145.0,
        sma_200=120.0,
        atr_14=4.5,
        headlines=(),
    )
    base.update(overrides)
    return StockSnapshot(**base)


class MarketRegimeTests(unittest.TestCase):
    def test_classify_strong_regime(self):
        regime = _classify_regime(
            market_key="US",
            index_name="标普500",
            ticker="SPY",
            price=500.0,
            change_pct=1.2,
            trend="多头排列",
            rsi_14=55.0,
        )
        self.assertEqual(regime.label, "强势")
        self.assertEqual(regime.buy_threshold_bonus, 0.0)

    def test_classify_weak_regime_tightens_picks(self):
        regime = _classify_regime(
            market_key="CN",
            index_name="上证指数",
            ticker="000001.SS",
            price=3000.0,
            change_pct=-2.0,
            trend="空头排列",
            rsi_14=40.0,
        )
        self.assertEqual(regime.label, "弱势")
        self.assertGreater(regime.buy_threshold_bonus, 0)

        rec = build_recommendation(_sample_snapshot())
        ranked = [rec]
        picks_strong, _ = select_picks_with_regime(ranked, top_n=3, regime=None)
        picks_weak, _ = select_picks_with_regime(ranked, top_n=3, regime=regime)
        self.assertGreaterEqual(len(picks_strong), len(picks_weak))


if __name__ == "__main__":
    unittest.main()
