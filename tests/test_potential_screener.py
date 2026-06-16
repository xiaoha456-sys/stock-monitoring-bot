import unittest

from potential_screener import (
    PotentialPick,
    format_potential_radar_section,
    score_growth_potential,
)
from stock_bot import StockSnapshot


def _snap(**overrides) -> StockSnapshot:
    base = dict(
        ticker="MU",
        price=100.0,
        currency="USD",
        change_pct=2.0,
        week_52_low=60.0,
        week_52_high=120.0,
        week_52_position=45.0,
        rsi_14=58.0,
        sma_50=95.0,
        sma_200=85.0,
        atr_14=4.0,
        headlines=(),
        momentum_20d=12.0,
        momentum_60d=8.0,
        volume_ratio=1.4,
        volatility_20d=2.5,
        sma_20=98.0,
    )
    base.update(overrides)
    return StockSnapshot(**base)


class PotentialScreenerTests(unittest.TestCase):
    def test_early_growth_profile_scores_high(self):
        score, phase, reasons = score_growth_potential(_snap())
        self.assertGreaterEqual(score, 58)
        self.assertIn(phase, ("潜力启动", "蓄势待发"))
        self.assertTrue(any("52周" in reason for reason in reasons))

    def test_late_stage_scores_lower(self):
        score, _, _ = score_growth_potential(
            _snap(week_52_position=92.0, momentum_20d=40.0, rsi_14=78.0)
        )
        self.assertLess(score, 58)

    def test_format_section_renders_picks(self):
        snap = _snap()
        pick = PotentialPick(
            ticker="MU",
            name="美光",
            market="US",
            score=75.0,
            phase="潜力启动",
            reasons=("量能放大", "趋势转强"),
            snapshot=snap,
        )
        text = "\n".join(format_potential_radar_section([pick]))
        self.assertIn("潜力雷达", text)
        self.assertIn("美光 (MU)", text)
        self.assertIn("潜力启动", text)


if __name__ == "__main__":
    unittest.main()
