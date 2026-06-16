import unittest

from potential_screener import PotentialPick
from research_agent import build_research_briefs, format_research_agent_section
from serenity_digest import SerenityDigest, SerenityPost
from stock_bot import StockSnapshot


def _snap(ticker: str = "SMCI") -> StockSnapshot:
    return StockSnapshot(
        ticker=ticker,
        price=30.0,
        currency="USD",
        change_pct=4.0,
        week_52_low=20.0,
        week_52_high=50.0,
        week_52_position=35.0,
        rsi_14=55.0,
        sma_50=28.0,
        sma_200=25.0,
        atr_14=2.0,
        headlines=("AI server demand rises",),
        momentum_20d=10.0,
        momentum_60d=6.0,
        volume_ratio=1.5,
    )


def _pick(ticker: str = "SMCI", score: float = 80.0) -> PotentialPick:
    return PotentialPick(
        ticker=ticker,
        name="Super Micro",
        market="US",
        score=score,
        phase="潜力启动",
        reasons=("量能放大", "趋势转强"),
        snapshot=_snap(ticker),
    )


def _serenity_digest() -> SerenityDigest:
    return SerenityDigest(
        handle="aleabitoreddit",
        target_date="2026-06-11",
        posts=(
            SerenityPost(
                text="I expect FOCI (3363) to be a bottleneck for both $NVDA and $TSM optical programs.",
                created_at="2026-06-11",
            ),
        ),
        themes=(
            "FOCI (3363) 是 NVDA/TSM 光互连 CPO 放量瓶颈",
            "轮动至 $SIVE、FOCI 等 CPO 名字",
        ),
        tickers=("FOCI", "SIVE", "NVDA", "TSM", "LITE", "COHR"),
        sentiment_label="偏看涨",
        source="test",
        notes=(),
    )


class ResearchAgentTests(unittest.TestCase):
    def test_smci_links_to_ai_compute_theme_with_serenity(self):
        briefs = build_research_briefs([_pick("SMCI")], _serenity_digest())
        self.assertEqual(len(briefs), 1)
        self.assertEqual(briefs[0].chain_theme, "AI 算力 / 服务器")
        self.assertIn(briefs[0].link_type, ("Serenity 同主题", "产业链映射"))
        self.assertTrue(briefs[0].invalidation)

    def test_lite_direct_serenity_link(self):
        briefs = build_research_briefs([_pick("LITE", 85)], _serenity_digest())
        self.assertEqual(len(briefs), 1)
        self.assertEqual(briefs[0].link_type, "Serenity 直接提及")
        self.assertIn("CPO", briefs[0].chain_theme)

    def test_format_section_contains_evidence_and_invalidation(self):
        briefs = build_research_briefs([_pick("LITE", 85)], _serenity_digest())
        text = "\n".join(format_research_agent_section(briefs))
        self.assertIn("研究 Agent", text)
        self.assertIn("证据来源", text)
        self.assertIn("失效条件", text)
        self.assertIn("反方理由", text)


if __name__ == "__main__":
    unittest.main()
