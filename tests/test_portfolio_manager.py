import unittest
from unittest.mock import patch

from portfolio_manager import analyze_portfolio, format_portfolio_overview_section
from stock_bot import Recommendation, StockSnapshot, build_recommendation


def _rec(ticker: str = "NVDA", action: str = "观望", price: float = 200.0) -> Recommendation:
    snap = StockSnapshot(
        ticker=ticker,
        price=price,
        currency="USD",
        change_pct=1.0,
        week_52_low=100.0,
        week_52_high=220.0,
        week_52_position=50.0,
        rsi_14=50.0,
        sma_50=190.0,
        sma_200=170.0,
        atr_14=5.0,
        headlines=(),
    )
    return Recommendation(
        ticker=ticker,
        action=action,
        score=70.0,
        stars=3,
        buy_low=190.0,
        buy_high=200.0,
        target_price=220.0,
        stop_loss=180.0,
        reasons=("test",),
        snapshot=snap,
        name="英伟达",
    )


class PortfolioManagerTests(unittest.TestCase):
    def test_weight_and_pnl_when_shares_and_cost_present(self):
        config = {
            "NVDA": {
                "name": "英伟达",
                "market": "US",
                "shares": 100,
                "cost_basis": 150,
                "target_price": 250,
                "stop_loss": 140,
            },
            "MU": {
                "name": "美光",
                "market": "US",
                "shares": 50,
                "cost_basis": 900,
            },
        }
        analysis = analyze_portfolio([_rec("NVDA", price=200), _rec("MU", price=1000)], config)
        nvda = next(item for item in analysis.holdings if item.recommendation.ticker == "NVDA")
        self.assertAlmostEqual(nvda.pnl_pct, (200 / 150 - 1) * 100, places=1)
        self.assertAlmostEqual(nvda.weight_pct, 100 * 20000 / (20000 + 50000), places=1)
        self.assertGreater(analysis.market_weights["US"], 99)

    def test_dynamic_stop_triggers_reduce_risk(self):
        config = {
            "NVDA": {
                "shares": 10,
                "cost_basis": 180,
            }
        }
        analysis = analyze_portfolio([_rec("NVDA", price=175)], config)
        self.assertEqual(analysis.holdings[0].portfolio_action, "降低风险")
        self.assertIn("止损", analysis.holdings[0].action_reasons[0])

    def test_alerts_when_shares_missing(self):
        analysis = analyze_portfolio([_rec("NVDA")], {"NVDA": {}})
        self.assertTrue(any("shares" in alert for alert in analysis.alerts))

    def test_format_overview_renders_table(self):
        config = {"NVDA": {"shares": 10, "cost_basis": 150, "target_price": 250, "stop_loss": 140}}
        analysis = analyze_portfolio([_rec("NVDA", price=200)], config)
        text = "\n".join(format_portfolio_overview_section(analysis))
        self.assertIn("持仓管家", text)
        self.assertIn("英伟达 (NVDA)", text)

    @patch("portfolio_manager._fetch_upcoming_earnings", return_value="NVDA 财报约 2026-06-20（6 天后）")
    def test_earnings_events_surface_in_analysis(self, _mock_earnings):
        analysis = analyze_portfolio([_rec("NVDA")], {"NVDA": {}})
        self.assertEqual(len(analysis.earnings_events), 1)

    @patch("portfolio_manager.get_market_cash_config", return_value={"CN": {"mode": "rotate_only"}})
    @patch("portfolio_manager.market_cash_mode", return_value="rotate_only")
    def test_rotate_only_changes_allow_add_to_rotation(self, _mode, _cash):
        config = {
            "600406.SS": {
                "shares": 1000,
                "cost_basis": 20,
                "max_weight_pct": 100,
            }
        }
        snap = StockSnapshot(
            ticker="600406.SS",
            price=23.0,
            currency="CNY",
            change_pct=1.0,
            week_52_low=18.0,
            week_52_high=26.0,
            week_52_position=50.0,
            rsi_14=50.0,
            sma_50=22.0,
            sma_200=20.0,
            atr_14=0.8,
            headlines=(),
        )
        rec = Recommendation(
            ticker="600406.SS",
            action="买入",
            score=75.0,
            stars=4,
            buy_low=22.0,
            buy_high=23.0,
            target_price=25.0,
            stop_loss=20.0,
            reasons=("test",),
            snapshot=snap,
            name="国电南瑞",
        )
        analysis = analyze_portfolio([rec], config)
        self.assertEqual(analysis.holdings[0].portfolio_action, "置换加仓")
        self.assertIn("减仓", analysis.holdings[0].action_reasons[-1])

    def test_format_cash_constraints_section(self):
        from portfolio_manager import format_cash_constraints_section

        text = "\n".join(format_cash_constraints_section())
        self.assertIn("资金约束", text)
        self.assertIn("美股", text)
        self.assertIn("仅减仓置换", text)


if __name__ == "__main__":
    unittest.main()
