import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from alphasift_cn import (
    AlphasiftCandidate,
    blend_scores,
    cn_code_to_yahoo,
    diversify_candidates,
    industry_bucket,
    normalize_cn_code,
    run_alphasift_screen,
)
from stock_bot import _enrich_with_alphasift, build_recommendation, scan_cn_market


def _sample_snapshot(**overrides):
    from stock_bot import StockSnapshot

    base = dict(
        ticker="688981.SS",
        price=120.0,
        currency="CNY",
        change_pct=-1.0,
        week_52_low=90.0,
        week_52_high=150.0,
        week_52_position=50.0,
        rsi_14=50.0,
        sma_50=115.0,
        sma_200=100.0,
        atr_14=5.0,
        headlines=(),
    )
    base.update(overrides)
    return StockSnapshot(**base)


class AlphasiftCnTests(unittest.TestCase):
    def test_cn_code_to_yahoo(self):
        self.assertEqual(cn_code_to_yahoo("600519"), "600519.SS")
        self.assertEqual(cn_code_to_yahoo("000858"), "000858.SZ")
        self.assertEqual(cn_code_to_yahoo("688981"), "688981.SS")
        self.assertEqual(normalize_cn_code("688981.SH"), "688981")

    def test_blend_scores(self):
        blended = blend_scores(80, 60, {"score_blend": {"screen": 0.55, "technical": 0.45}})
        self.assertAlmostEqual(blended, 71.0)

    def test_industry_bucket_detects_financials(self):
        bank = AlphasiftCandidate(
            rank=1,
            code="601328",
            name="交通银行",
            final_score=80.0,
            screen_score=80.0,
            ranking_reason="",
            industry="",
            change_pct=1.0,
            yahoo_ticker="601328.SS",
        )
        tech = AlphasiftCandidate(
            rank=2,
            code="300750",
            name="宁德时代",
            final_score=78.0,
            screen_score=78.0,
            ranking_reason="",
            industry="电池",
            change_pct=2.0,
            yahoo_ticker="300750.SZ",
        )
        self.assertEqual(industry_bucket(bank), "金融")
        self.assertEqual(industry_bucket(tech), "电池")

    def test_diversify_candidates_limits_financial_sector(self):
        candidates = [
            AlphasiftCandidate(1, "601328", "交通银行", 82.0, 80.0, "", "", 1.0, "601328.SS"),
            AlphasiftCandidate(2, "000001", "平安银行", 81.0, 79.0, "", "", 1.0, "000001.SZ"),
            AlphasiftCandidate(3, "300750", "宁德时代", 80.0, 78.0, "", "电池", 2.0, "300750.SZ"),
            AlphasiftCandidate(4, "002594", "比亚迪", 79.0, 77.0, "", "汽车", 1.5, "002594.SZ"),
        ]
        config = {
            "max_output": 12,
            "diversify": {"enabled": True, "max_per_bucket": 1, "buckets": {"金融": 1}},
        }
        selected, meta = diversify_candidates(candidates, config)
        self.assertEqual(len(selected), 3)
        self.assertEqual(meta["skipped_count"], 1)
        self.assertEqual(sum(1 for item in selected if industry_bucket(item) == "金融"), 1)

    @patch("alphasift_cn.alphasift_screen")
    def test_run_alphasift_screen_maps_picks(self, screen_mock: Mock):
        screen_mock.return_value = SimpleNamespace(
            strategy="balanced_alpha",
            run_id="abc123",
            strategy_version="1",
            snapshot_count=5000,
            after_filter_count=120,
            picks=[
                SimpleNamespace(
                    rank=1,
                    code="688981",
                    name="中芯国际",
                    final_score=88.0,
                    screen_score=85.0,
                    ranking_reason="放量突破",
                    industry="半导体",
                    change_pct=2.5,
                    llm_thesis="",
                )
            ],
            snapshot_source="akshare",
            llm_ranked=False,
            degradation=[],
            source_errors=[],
        )
        candidates, meta = run_alphasift_screen({"strategy": "balanced_alpha", "max_output": 5})
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].yahoo_ticker, "688981.SS")
        self.assertEqual(meta["pick_count"], 1)

    def test_enrich_with_alphasift_updates_score_and_name(self):
        technical = build_recommendation(_sample_snapshot())
        candidate = AlphasiftCandidate(
            rank=1,
            code="688981",
            name="中芯国际",
            final_score=90.0,
            screen_score=88.0,
            ranking_reason="资金回流",
            industry="半导体",
            change_pct=1.2,
            yahoo_ticker="688981.SS",
        )
        enriched = _enrich_with_alphasift(
            technical,
            candidate,
            {"strategy": "balanced_alpha", "score_blend": {"screen": 0.55, "technical": 0.45}},
        )
        self.assertEqual(enriched.name, "中芯国际")
        self.assertEqual(enriched.strategy, "balanced_alpha")
        self.assertAlmostEqual(enriched.score, blend_scores(90.0, technical.score, {"score_blend": {"screen": 0.55, "technical": 0.45}}))
        self.assertIn("alphasift #1", enriched.reasons[0])

    @patch("stock_bot.fetch_snapshot")
    @patch("alphasift_cn.run_alphasift_screen")
    @patch("alphasift_cn.is_alphasift_available", return_value=True)
    def test_scan_cn_market_uses_alphasift_candidates(
        self,
        _available: Mock,
        screen_mock: Mock,
        fetch_snapshot_mock: Mock,
    ):
        screen_mock.return_value = (
            [
                AlphasiftCandidate(
                    rank=1,
                    code="688981",
                    name="中芯国际",
                    final_score=90.0,
                    screen_score=88.0,
                    ranking_reason="放量",
                    industry="半导体",
                    change_pct=1.0,
                    yahoo_ticker="688981.SS",
                )
            ],
            {"strategy": "balanced_alpha", "snapshot_count": 100, "after_filter_count": 10, "pick_count": 1},
        )
        fetch_snapshot_mock.return_value = _sample_snapshot()
        picks, others, errors, extras = scan_cn_market()
        self.assertEqual(len(picks), 1)
        self.assertEqual(picks[0].name, "中芯国际")
        self.assertIn("alphasift", extras)
        self.assertEqual(errors, {})


if __name__ == "__main__":
    unittest.main()
