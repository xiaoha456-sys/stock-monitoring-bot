import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

import pandas as pd

from stock_bot import (
    Recommendation,
    StockSnapshot,
    _action_from_score,
    _grade_prediction,
    _holding_today_action,
    _report_html,
    _score_snapshot,
    _ticker_display_name,
    build_combined_report,
    build_market_report,
    build_recommendation,
    calculate_rsi,
    format_pick,
    load_dotenv,
    prediction_record,
    resolve_notification_channels,
    review_predictions,
    save_predictions,
    send_email,
    send_report,
    send_wechat,
)


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


class StockBotTests(unittest.TestCase):
    def test_rsi_for_rising_prices_is_overbought(self):
        close = pd.Series(range(1, 40), dtype=float)
        self.assertEqual(calculate_rsi(close).iloc[-1], 100)

    def test_report_html_renders_tables_and_headings(self):
        markdown = "\n".join(
            [
                "# 标题",
                "",
                "> 免责声明",
                "",
                "## 持仓",
                "",
                "- **NVDA** $204.87 · **可加仓**",
                "",
                "| 项目 | 数值 |",
                "| --- | --- |",
                "| 现价 | $204.87 |",
                "",
                "---",
            ]
        )
        rendered = _report_html(markdown)
        self.assertIn("<h1", rendered)
        self.assertIn("<h2", rendered)
        self.assertIn("<blockquote", rendered)
        self.assertIn("<table", rendered)
        self.assertIn("<th", rendered)
        self.assertIn("<td", rendered)
        self.assertIn("<strong>NVDA</strong>", rendered)
        self.assertNotIn("| --- |", rendered)

    def test_report_html_renders_news_links(self):
        markdown = "**新闻**：[NVDA hits record](https://example.com/nvda?a=1&b=2)"
        rendered = _report_html(markdown)
        self.assertIn('<a href="https://example.com/nvda?a=1&amp;b=2"', rendered)
        self.assertIn(">NVDA hits record</a>", rendered)

    def test_format_pick_links_headline(self):
        snapshot = _sample_snapshot(
            headlines=("Example headline",),
            headline_links=("https://example.com/article",),
        )
        rec = build_recommendation(snapshot)
        self.assertIn("[Example headline](https://example.com/article)", format_pick(1, rec))

    def test_cn_ticker_uses_chinese_display_name(self):
        self.assertEqual(_ticker_display_name("000333.SZ"), "美的集团")
        snapshot = _sample_snapshot(ticker="000333.SZ", currency="CNY")
        rec = build_recommendation(snapshot)
        self.assertEqual(rec.name, "美的集团")
        self.assertIn("美的集团 (000333.SZ)", format_pick(1, rec))

    def test_holding_today_action_suggests_buy_in_zone(self):
        snapshot = _sample_snapshot(price=150.0)
        rec = build_recommendation(snapshot)
        rec = Recommendation(
            ticker=rec.ticker,
            action="买入",
            score=rec.score,
            stars=rec.stars,
            buy_low=145.0,
            buy_high=150.0,
            target_price=160.0,
            stop_loss=140.0,
            reasons=rec.reasons,
            snapshot=snapshot,
        )
        action = _holding_today_action(rec)
        self.assertIn("今日可挂单买入", action)
        self.assertIn("$145.00", action)

    def test_load_dotenv_does_not_override_existing_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text("SMTP_HOST=from-dotenv\nEMAIL_FROM=dotenv@example.com\n", encoding="utf-8")
            with patch.dict("os.environ", {"SMTP_HOST": "existing"}, clear=False):
                load_dotenv(env_file)
                self.assertEqual(os.environ["SMTP_HOST"], "existing")
                self.assertEqual(os.environ["EMAIL_FROM"], "dotenv@example.com")
            os.environ.pop("EMAIL_FROM", None)

    @patch.dict(
        "os.environ",
        {
            "SMTP_HOST": "smtp.qq.com",
            "SMTP_PORT": "465",
            "SMTP_USER": "313265258@qq.com",
            "SMTP_PASSWORD": "secret",
            "EMAIL_FROM": "313265258@qq.com",
            "EMAIL_TO": "313265258@qq.com",
        },
        clear=False,
    )
    @patch("stock_bot.smtplib.SMTP_SSL")
    def test_send_email_uses_ssl_for_qq(self, smtp_ssl: Mock):
        server = smtp_ssl.return_value.__enter__.return_value

        send_email("A股每日投资简报", "测试报告")

        smtp_ssl.assert_called_once_with("smtp.qq.com", 465, timeout=30)
        server.login.assert_called_once_with("313265258@qq.com", "secret")
        server.send_message.assert_called_once()

    @patch.dict(
        "os.environ",
        {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "bot@example.com",
            "SMTP_PASSWORD": "secret",
            "EMAIL_FROM": "bot@example.com",
            "EMAIL_TO": "you@example.com",
        },
        clear=False,
    )
    @patch("stock_bot.smtplib.SMTP")
    def test_send_email_uses_smtp(self, smtp: Mock):
        server = smtp.return_value.__enter__.return_value
        with patch(
            "stock_bot._email_settings",
            return_value={"smtp_port_default": 587, "use_tls": True},
        ):
            send_email("美股每日投资简报", "测试报告")

        smtp.assert_called_once_with("smtp.example.com", 587, timeout=30)
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("bot@example.com", "secret")
        server.send_message.assert_called_once()
        message = server.send_message.call_args.args[0]
        self.assertEqual(message["Subject"], "美股每日投资简报")
        plain = message.get_body(preferencelist=("plain",))
        self.assertIsNotNone(plain)
        self.assertEqual(plain.get_content().strip(), "测试报告")

    @patch.dict(
        "os.environ",
        {
            "SMTP_HOST": "smtp.example.com",
            "EMAIL_FROM": "bot@example.com",
            "EMAIL_TO": "you@example.com",
            "SERVERCHAN_SENDKEY": "SCT_TEST",
        },
        clear=False,
    )
    @patch("stock_bot.send_wechat")
    @patch("stock_bot.send_email")
    def test_send_report_uses_configured_channels(self, send_email_mock: Mock, send_wechat_mock: Mock):
        with patch("stock_bot._notification_settings") as settings:
            settings.return_value = {"channels": ["email", "wechat"], "email": {}, "wechat": {}}
            delivered = send_report("简报", "正文", channels=["email", "wechat"])

        self.assertEqual(delivered, ["email", "wechat"])
        send_email_mock.assert_called_once_with("简报", "正文")
        send_wechat_mock.assert_called_once()

    @patch.dict(
        "os.environ",
        {
            "SMTP_HOST": "smtp.example.com",
            "EMAIL_FROM": "bot@example.com",
            "EMAIL_TO": "you@example.com",
        },
        clear=False,
    )
    def test_resolve_notification_channels_defaults_to_email(self):
        with patch("stock_bot._notification_settings") as settings:
            settings.return_value = {"channels": ["email"], "email": {}, "wechat": {}}
            channels = resolve_notification_channels()
        self.assertEqual(channels, ["email"])

    @patch("stock_bot.requests.post")
    def test_send_wechat_uses_serverchan(self, post: Mock):
        response = post.return_value
        response.json.return_value = {"code": 0, "message": ""}

        send_wechat("美股每日投资简报", "测试报告", "SCT_TEST")

        post.assert_called_once_with(
            "https://sctapi.ftqq.com/SCT_TEST.send",
            data={"title": "美股每日投资简报", "desp": "测试报告"},
            timeout=30,
        )
        response.raise_for_status.assert_called_once()

    def test_bullish_snapshot_scores_high_and_recommends_buy(self):
        snapshot = _sample_snapshot()
        score, _ = _score_snapshot(snapshot)
        self.assertGreaterEqual(score, 70)
        rec = build_recommendation(snapshot)
        self.assertIn(rec.action, ("买入", "逢低关注"))
        self.assertLess(rec.buy_low, rec.buy_high)
        self.assertGreater(rec.target_price, snapshot.price)
        self.assertLess(rec.stop_loss, snapshot.price)

    def test_buy_zone_is_executable_today(self):
        """Buy zone must hug the latest price, even for extended uptrends."""
        snapshot = _sample_snapshot(price=150.0, sma_20=148.0, sma_50=120.0, atr_14=4.5)
        rec = build_recommendation(snapshot)
        self.assertLessEqual(rec.buy_high, snapshot.price)
        self.assertGreaterEqual(rec.buy_low, snapshot.price - snapshot.atr_14 * 1.5)
        self.assertLess(rec.stop_loss, rec.buy_low)
        self.assertGreater(rec.target_price, rec.buy_high)

    def test_bearish_snapshot_scores_low(self):
        snapshot = _sample_snapshot(
            price=100.0,
            change_pct=-3.5,
            week_52_position=15.0,
            rsi_14=78.0,
            sma_50=120.0,
            sma_200=130.0,
        )
        score, _ = _score_snapshot(snapshot)
        self.assertLess(score, 50)
        self.assertIn(_action_from_score(score), ("观望", "减仓", "回避"))

    def test_market_report_contains_action_table(self):
        rec = build_recommendation(_sample_snapshot())
        now = datetime(2026, 6, 12, 10, tzinfo=ZoneInfo("Australia/Sydney"))
        report = build_market_report("US", [rec], [], {}, now=now)

        self.assertIn("美股每日投资简报", report)
        self.assertIn("建议买入", report)
        self.assertIn("目标卖出", report)
        self.assertIn("止损参考", report)
        self.assertIn("NVDA", report)

    def test_combined_report_includes_all_markets(self):
        rec = build_recommendation(_sample_snapshot())
        now = datetime(2026, 6, 12, 10, tzinfo=ZoneInfo("Australia/Sydney"))
        reports = {
            "US": ([rec], [], {}, {}),
            "CN": ([rec], [], {}, {}),
            "AU": ([rec], [], {}, {}),
        }
        combined = build_combined_report(reports, now=now)

        self.assertIn("每日持仓操作简报", combined)
        self.assertIn("## 📌 今日结论", combined)
        self.assertIn("## 附录：技术详情", combined)
        self.assertIn("## 📊 持仓管家", combined)
        self.assertNotIn("## 💼 持仓今日操作指南", combined)
        self.assertIn("## 🇺🇸 美股", combined)
        self.assertIn("## 🇨🇳 A股", combined)
        self.assertIn("## 🇦🇺 澳股", combined)
        self.assertEqual(combined.count("**提示**"), 1)

    def test_prediction_record_roundtrip(self):
        rec = build_recommendation(_sample_snapshot())
        record = prediction_record(rec)
        self.assertEqual(record["ticker"], "NVDA")
        self.assertIn("buy_low", record)
        self.assertIn("target_price", record)

    def test_grade_prediction_rewards_direction_and_target(self):
        record = {
            "ticker": "NVDA",
            "action": "买入",
            "price_at_signal": 100.0,
            "buy_high": 102.0,
            "target_price": 110.0,
            "stop_loss": 92.0,
        }
        result = _grade_prediction(record, last_close=108.0, low=99.0, high=111.0)
        self.assertGreaterEqual(result["score"], 60)
        self.assertTrue(result["target_hit"])

    @patch("stock_bot.PREDICTIONS_DIR")
    @patch("stock_bot.REVIEW_SCORES_PATH")
    @patch("stock_bot._fetch_price_range")
    def test_review_predictions_reads_saved_file(
        self,
        fetch_range: Mock,
        review_path: Mock,
        predictions_dir: Mock,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            pred_dir = Path(tmp) / "predictions"
            pred_dir.mkdir()
            signal_date = (datetime.now(ZoneInfo("Australia/Sydney")) - pd.Timedelta(days=1)).strftime(
                "%Y-%m-%d"
            )
            payload = {
                "date": signal_date,
                "markets": {
                    "US": {
                        "picks": [
                            {
                                "ticker": "NVDA",
                                "action": "买入",
                                "score": 80,
                                "price_at_signal": 100,
                                "currency": "USD",
                                "buy_low": 95,
                                "buy_high": 98,
                                "target_price": 110,
                                "stop_loss": 90,
                            }
                        ],
                        "watchlist": [],
                    }
                },
                "holdings": {
                    "US": [
                        {
                            "ticker": "MU",
                            "name": "美光",
                            "action": "观望",
                            "score": 55,
                            "price_at_signal": 200,
                            "currency": "USD",
                            "buy_low": 190,
                            "buy_high": 198,
                            "target_price": 220,
                            "stop_loss": 180,
                        }
                    ]
                },
            }
            (pred_dir / f"{signal_date}.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            review_file = Path(tmp) / "review_scores.json"

            predictions_dir.__truediv__ = lambda _self, name: pred_dir / name
            predictions_dir.mkdir = Mock()
            review_path.exists.return_value = False
            review_path.parent = review_file.parent
            review_path.__str__ = lambda _self: str(review_file)
            review_path.write_text = lambda content, encoding="utf-8": review_file.write_text(
                content, encoding=encoding
            )

            fetch_range.return_value = (105.0, 96.0, 108.0)
            report, payload_out = review_predictions(horizons=[1])
            self.assertIn("NVDA", report)
            self.assertIn("MU", report)
            self.assertIn("观察池推荐", report)
            self.assertIn("持仓操作", report)
            self.assertIn("T+1", report)
            self.assertIn("holdings", payload_out["horizons"]["T+1"])
            self.assertTrue(review_file.exists())


if __name__ == "__main__":
    unittest.main()
