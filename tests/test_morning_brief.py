import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from morning_brief import (
    compose_email_report,
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
        report = compose_email_report(
            {"US": ([buy_rec], [], {}, {})},
            now=now,
            holdings=([], {}),
        )
        holdings_pos = report.index("# 一、持仓")
        cash_pos = report.index("# 二、资金")
        brief_pos = report.index("# 三、简报")
        conclusion_pos = report.index("## 📌 今日结论")
        appendix_pos = report.index("## 附录：技术详情")
        self.assertLess(holdings_pos, cash_pos)
        self.assertLess(cash_pos, brief_pos)
        self.assertLess(brief_pos, conclusion_pos)
        self.assertLess(conclusion_pos, appendix_pos)
        self.assertNotIn("## 📊 持仓管家", report)
        self.assertIn("# 一、持仓", report)
        self.assertIn("## 💰 候选价格参考", report)
        self.assertIn("减仓置换", report)

    def test_holdings_orders_in_email_holdings_section(self):
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
        now = datetime(2026, 6, 13, 10, tzinfo=ZoneInfo("Australia/Sydney"))
        report = compose_morning_brief({}, now=now, holdings=([add_rec, observe], {}))
        self.assertNotIn("## 💼 持仓事件", report)
        self.assertNotIn("### 今日挂单", report)
        self.assertNotIn("# 一、持仓", report)
        self.assertNotIn("持仓关注", report)
        email = compose_email_report({}, now=now, holdings=([add_rec, observe], {}))
        self.assertIn("# 一、持仓", email)
        self.assertIn("建议操作", email)
        self.assertNotIn("### 今日挂单", email)
        from domain.brief_display import build_display_sections

        sections = build_display_sections(verdict, analysis)
        self.assertFalse(any(section["title"] == "持仓关注" for section in sections))
        self.assertFalse(any(section["title"] == "今日挂单" for section in sections))

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
