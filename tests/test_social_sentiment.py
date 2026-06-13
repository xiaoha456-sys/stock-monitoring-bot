import unittest
from unittest.mock import Mock, patch

from social_sentiment import (
    build_social_report,
    enrich_buzz_with_prices,
    fetch_reddit_buzz,
    format_social_section,
    score_text_sentiment,
    _extract_discussed_prices,
)


class SocialSentimentTests(unittest.TestCase):
    def test_score_text_sentiment_bullish(self):
        score, label = score_text_sentiment("NVDA to the moon, buy calls, bullish breakout 🚀")
        self.assertGreater(score, 0)
        self.assertEqual(label, "看涨")

    def test_score_text_sentiment_bearish(self):
        score, label = score_text_sentiment("puts printing, crash incoming, sell everything")
        self.assertLess(score, 0)
        self.assertEqual(label, "看跌")

    @patch("social_sentiment.requests.get")
    def test_fetch_reddit_buzz_maps_apewisdom(self, get_mock: Mock):
        get_mock.return_value = Mock(
            status_code=200,
            json=lambda: {
                "results": [
                    {
                        "rank": 1,
                        "ticker": "NVDA",
                        "name": "NVIDIA",
                        "mentions": 300,
                        "mentions_24h_ago": 200,
                        "upvotes": 1800,
                        "rank_24h_ago": 3,
                    }
                ]
            },
            raise_for_status=Mock(),
        )
        items, meta = fetch_reddit_buzz(
            {"reddit": {"enabled": True, "top_n": 5, "apewisdom_filter": "all-stocks"}}
        )
        self.assertEqual(meta["status"], "ok")
        self.assertEqual(items[0].ticker, "NVDA")
        self.assertEqual(items[0].source, "Reddit")

    def test_extract_discussed_prices_from_tweet(self):
        prices = _extract_discussed_prices("NVDA looks good, target $220, could hit $250 this week")
        self.assertIn(220.0, prices)
        self.assertIn(250.0, prices)

    @patch("stock_bot.build_recommendation")
    @patch("stock_bot.fetch_snapshot")
    def test_enrich_buzz_with_prices(self, fetch_mock, build_mock):
        from social_sentiment import TickerBuzz
        from stock_bot import Recommendation, StockSnapshot

        snap = StockSnapshot(
            ticker="MU",
            price=980.0,
            currency="USD",
            change_pct=1.0,
            week_52_low=600.0,
            week_52_high=1000.0,
            week_52_position=80.0,
            rsi_14=60.0,
            sma_50=900.0,
            sma_200=700.0,
            atr_14=40.0,
            headlines=(),
        )
        fetch_mock.return_value = snap
        build_mock.return_value = Recommendation(
            ticker="MU",
            action="逢低关注",
            score=72.0,
            stars=4,
            buy_low=878.0,
            buy_high=923.0,
            target_price=1111.0,
            stop_loss=808.0,
            reasons=("test",),
            snapshot=snap,
        )
        item = TickerBuzz(
            ticker="MU",
            name="Micron",
            mentions=300,
            sentiment_score=20.0,
            sentiment_label="看涨",
            source="Reddit",
            rank=1,
        )
        enriched = enrich_buzz_with_prices([item])[0]
        self.assertEqual(enriched.price, 980.0)
        self.assertEqual(enriched.buy_low, 878.0)
        self.assertEqual(enriched.target_price, 1111.0)

    @patch("social_sentiment.fetch_x_buzz", return_value=([], {"status": "skipped", "reason": "no token"}))
    @patch("social_sentiment.fetch_reddit_buzz")
    def test_build_social_report_formats_section(self, reddit_mock: Mock, _x_mock: Mock):
        from social_sentiment import TickerBuzz

        reddit_mock.return_value = (
            [
                TickerBuzz(
                    ticker="MU",
                    name="Micron",
                    mentions=320,
                    sentiment_score=22.0,
                    sentiment_label="看涨",
                    source="Reddit",
                    rank=1,
                    detail="+100 mentions",
                )
            ],
            {"status": "ok", "source": "ApeWisdom"},
        )
        report = build_social_report({"reddit": {"enabled": True}, "x": {"enabled": True}})
        lines = format_social_section(report)
        text = "\n".join(lines)
        self.assertIn("MU", text)
        self.assertIn("Reddit 热议", text)
        self.assertIn("整体", text)


if __name__ == "__main__":
    unittest.main()
