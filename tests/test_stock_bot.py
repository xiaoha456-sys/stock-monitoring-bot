import unittest
from datetime import datetime
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pandas as pd

from stock_bot import StockSnapshot, build_report, calculate_rsi, send_wechat


class StockBotTests(unittest.TestCase):
    def test_rsi_for_rising_prices_is_overbought(self):
        close = pd.Series(range(1, 40), dtype=float)
        self.assertEqual(calculate_rsi(close).iloc[-1], 100)

    @patch("stock_bot.requests.post")
    def test_send_wechat_uses_serverchan(self, post: Mock):
        response = post.return_value
        response.json.return_value = {"code": 0, "message": ""}

        send_wechat("测试报告", "SCT_TEST")

        post.assert_called_once_with(
            "https://sctapi.ftqq.com/SCT_TEST.send",
            data={"title": "每日持仓监控", "desp": "测试报告"},
            timeout=30,
        )
        response.raise_for_status.assert_called_once()

    def test_report_contains_required_metrics(self):
        snapshot = StockSnapshot(
            ticker="NVDA",
            price=150,
            currency="USD",
            change_pct=1.25,
            week_52_low=90,
            week_52_high=160,
            week_52_position=85.7,
            rsi_14=61.2,
            sma_50=145,
            sma_200=120,
            headlines=("Example headline (https://example.com)",),
        )
        now = datetime(2026, 6, 12, 8, tzinfo=ZoneInfo("Australia/Sydney"))
        report = build_report([snapshot], {}, now=now)

        self.assertIn("NVDA", report)
        self.assertIn("+1.25%", report)
        self.assertIn("52周", report)
        self.assertIn("RSI(14)", report)
        self.assertIn("SMA50", report)
        self.assertIn("Example headline", report)


if __name__ == "__main__":
    unittest.main()
