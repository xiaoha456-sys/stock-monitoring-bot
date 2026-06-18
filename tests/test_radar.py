import unittest
from unittest.mock import patch

from radar import _holding_status_label, format_market_radar_section
from stock_bot import Recommendation, StockSnapshot


def _sample_pick(ticker: str = "NVDA") -> "RadarPick":
    from radar import RadarPick

    snap = StockSnapshot(
        ticker=ticker,
        price=200.0,
        currency="USD",
        change_pct=1.0,
        week_52_low=100.0,
        week_52_high=220.0,
        week_52_position=50.0,
        rsi_14=55.0,
        sma_50=190.0,
        sma_200=170.0,
        atr_14=5.0,
        headlines=("Test headline",),
    )
    rec = Recommendation(
        ticker=ticker,
        action="买入",
        score=75.0,
        stars=4,
        buy_low=190.0,
        buy_high=200.0,
        target_price=220.0,
        stop_loss=180.0,
        reasons=("test",),
        snapshot=snap,
        name="英伟达",
    )
    return RadarPick(
        ticker=ticker,
        name="英伟达",
        market="US",
        composite_score=72.0,
        trend_score=75.0,
        valuation_score=58.0,
        catalyst_score=62.0,
        risk_score=80.0,
        reasons=("趋势向上", "估值中性", "有新闻", "风险可控"),
        snapshot=snap,
        recommendation=rec,
    )


class RadarTests(unittest.TestCase):
    def test_holding_status_label(self):
        self.assertEqual(_holding_status_label("NVDA", {"NVDA"}), "已持仓")
        self.assertEqual(_holding_status_label("MU", {"NVDA"}), "未持仓")

    @patch("radar._held_tickers", return_value={"NVDA"})
    def test_format_section_shows_holding_status(self, _mock_held):
        text = "\n".join(format_market_radar_section([_sample_pick("NVDA"), _sample_pick("MU")]))
        self.assertIn("状态", text)
        self.assertIn("已持仓", text)
        self.assertIn("未持仓", text)
        self.assertIn("可评估加仓/减仓", text)


if __name__ == "__main__":
    unittest.main()
