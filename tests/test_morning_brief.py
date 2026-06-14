import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from morning_brief import (
    compose_morning_brief,
    derive_verdict,
    format_conclusion_section,
)
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
        headlines=("Example headline",),
    )
    base.update(overrides)
    return StockSnapshot(**base)


class MorningBriefTests(unittest.TestCase):
    def test_no_action_when_nothing_actionable(self):
        holding = build_recommendation(_sample_snapshot(ticker="NVDA"))
        holding = Recommendation(
            ticker=holding.ticker,
            action="观望",
            score=holding.score,
            stars=holding.stars,
            buy_low=holding.buy_low,
            buy_high=holding.buy_high,
            target_price=holding.target_price,
            stop_loss=holding.stop_loss,
            reasons=holding.reasons,
            snapshot=holding.snapshot,
        )
        watch_rec = build_recommendation(_sample_snapshot(ticker="MSFT", sma_50=160.0, sma_200=170.0))
        verdict = derive_verdict([holding], {"US": ([], [watch_rec], {}, {})})
        self.assertTrue(verdict["no_action_today"])
        conclusion = "\n".join(format_conclusion_section(verdict))
        self.assertIn("今日不操作", conclusion)

    def test_combined_report_puts_conclusion_first(self):
        buy_rec = build_recommendation(_sample_snapshot())
        now = datetime(2026, 6, 13, 10, tzinfo=ZoneInfo("Australia/Sydney"))
        report = compose_morning_brief(
            {"US": ([buy_rec], [], {}, {})},
            now=now,
            holdings=([], {}),
        )
        conclusion_pos = report.index("## 📌 今日结论")
        appendix_pos = report.index("## 附录：技术详情")
        self.assertLess(conclusion_pos, appendix_pos)
        self.assertIn("## 💰 价格区间", report)

    def test_appendix_keeps_full_market_section(self):
        rec = build_recommendation(_sample_snapshot())
        report = compose_morning_brief(
            {"US": ([rec], [], {}, {})},
            now=datetime(2026, 6, 13, 10, tzinfo=ZoneInfo("Australia/Sydney")),
        )
        self.assertIn("### 观察池完整列表", report)
        self.assertIn("## 🇺🇸 美股", report)


if __name__ == "__main__":
    unittest.main()
