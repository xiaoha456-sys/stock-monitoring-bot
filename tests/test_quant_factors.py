import unittest

from quant_factors import cross_sectional_scores, factor_value, strategy_factor_weights
from stock_bot import StockSnapshot


def make_snapshot(ticker: str, **overrides) -> StockSnapshot:
    defaults = dict(
        ticker=ticker,
        price=100.0,
        currency="USD",
        change_pct=0.0,
        week_52_low=70.0,
        week_52_high=130.0,
        week_52_position=50.0,
        rsi_14=50.0,
        sma_50=95.0,
        sma_200=90.0,
        atr_14=2.0,
        headlines=(),
    )
    defaults.update(overrides)
    return StockSnapshot(**defaults)


WEIGHTS = {
    "momentum_20d": 1.0,
    "momentum_60d": 0.8,
    "trend_strength": 1.0,
    "volume_ratio": 0.5,
    "volatility_20d": -0.6,
}


class QuantFactorTests(unittest.TestCase):
    def test_trend_strength_derived_from_price_vs_sma(self):
        snap = make_snapshot("AAA", price=110.0, sma_50=100.0)
        self.assertAlmostEqual(factor_value(snap, "trend_strength"), 10.0)

    def test_small_pool_returns_empty(self):
        snapshots = [make_snapshot("AAA"), make_snapshot("BBB")]
        self.assertEqual(cross_sectional_scores(snapshots, WEIGHTS), {})

    def test_strong_momentum_ranks_above_weak(self):
        snapshots = [
            make_snapshot("STRONG", momentum_20d=12.0, momentum_60d=25.0, volume_ratio=1.4),
            make_snapshot("MID", momentum_20d=2.0, momentum_60d=5.0),
            make_snapshot("WEAK", momentum_20d=-8.0, momentum_60d=-15.0, volume_ratio=0.7),
        ]
        scores = cross_sectional_scores(snapshots, WEIGHTS)
        self.assertGreater(scores["STRONG"][0], scores["MID"][0])
        self.assertGreater(scores["MID"][0], scores["WEAK"][0])
        self.assertTrue(all(0 <= score <= 100 for score, _ in scores.values()))

    def test_strategy_factor_weights_prefers_volume_for_breakout(self):
        weights = strategy_factor_weights("volume_breakout")
        self.assertGreater(weights["volume_ratio"], weights["momentum_60d"])

    def test_high_volatility_penalized(self):
        snapshots = [
            make_snapshot("CALM", volatility_20d=1.0),
            make_snapshot("MID2", volatility_20d=2.5),
            make_snapshot("WILD", volatility_20d=6.0),
        ]
        scores = cross_sectional_scores(snapshots, {"volatility_20d": -1.0})
        self.assertGreater(scores["CALM"][0], scores["WILD"][0])


if __name__ == "__main__":
    unittest.main()
