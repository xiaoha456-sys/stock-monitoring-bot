import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from morning_brief import (
    compose_morning_brief,
    derive_verdict,
    format_conclusion_section,
)
from portfolio_manager import analyze_portfolio
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
        analysis = analyze_portfolio([holding], {"NVDA": {}})
        verdict = derive_verdict(analysis, {"US": ([], [watch_rec], {}, {})})
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
        portfolio_pos = report.index("## 📊 持仓管家")
        self.assertLess(conclusion_pos, portfolio_pos)
        self.assertLess(portfolio_pos, appendix_pos)
        self.assertIn("## 💰 候选价格参考", report)

    def test_holdings_show_only_actionable_in_events(self):
        add_rec = build_recommendation(_sample_snapshot(ticker="MU"))
        add_rec = Recommendation(
            ticker=add_rec.ticker,
            action="买入",
            score=add_rec.score,
            stars=add_rec.stars,
            buy_low=add_rec.buy_low,
            buy_high=add_rec.buy_high,
            target_price=add_rec.target_price,
            stop_loss=add_rec.stop_loss,
            reasons=add_rec.reasons,
            snapshot=add_rec.snapshot,
            name="美光",
        )
        observe = build_recommendation(_sample_snapshot(ticker="NVDA"))
        observe = Recommendation(
            ticker=observe.ticker,
            action="观望",
            score=observe.score,
            stars=observe.stars,
            buy_low=observe.buy_low,
            buy_high=observe.buy_high,
            target_price=observe.target_price,
            stop_loss=observe.stop_loss,
            reasons=observe.reasons,
            snapshot=observe.snapshot,
            name="英伟达",
        )
        analysis = analyze_portfolio([add_rec, observe], {"MU": {}, "NVDA": {}})
        verdict = derive_verdict(analysis, {})
        from morning_brief import format_brief_holdings_section

        text = "\n".join(format_brief_holdings_section(verdict))
        self.assertIn("美光 (MU)", text)
        self.assertIn("继续观察", text)
        self.assertIn("英伟达 (NVDA)", text)
        self.assertNotIn("## 💼 持仓今日操作指南", text)

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
