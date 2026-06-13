import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from iterate_accuracy import collect_market_stats, propose_adjustments
from tuning import DEFAULT_TUNING, load_tuning, save_tuning


class IterateAccuracyTests(unittest.TestCase):
    def test_propose_adjustments_tightens_when_hit_rate_low(self):
        stats = {
            "US": {
                "count": 8,
                "hit_rate": 0.25,
                "avg_score": 40,
                "stop_rate": 0.1,
            }
        }
        tuning = json.loads(json.dumps(DEFAULT_TUNING))
        config = {
            "target_hit_rate": 0.6,
            "target_avg_score": 65,
            "min_samples_per_market": 5,
            "max_adjustment_per_run": 2,
            "alphasift_strategy_rotation": [],
        }
        changes = propose_adjustments(stats, tuning, config)
        self.assertTrue(any(item.get("path") == "thresholds.buy" for item in changes))
        self.assertGreater(tuning["thresholds"]["buy"], 72)

    @patch("iterate_accuracy._fetch_price_range")
    def test_collect_market_stats_grades_saved_predictions(self, fetch_range):
        with tempfile.TemporaryDirectory() as tmp:
            pred_dir = Path(tmp) / "predictions"
            pred_dir.mkdir()
            signal_date = "2026-06-07"
            payload = {
                "date": signal_date,
                "markets": {
                    "US": {
                        "picks": [
                            {
                                "ticker": "NVDA",
                                "action": "买入",
                                "price_at_signal": 100,
                                "buy_high": 102,
                                "target_price": 110,
                                "stop_loss": 90,
                            }
                        ]
                    }
                },
                "holdings": {
                    "US": [
                        {
                            "ticker": "MU",
                            "name": "美光",
                            "action": "观望",
                            "price_at_signal": 200,
                            "buy_high": 195,
                            "target_price": 220,
                            "stop_loss": 180,
                        }
                    ]
                },
            }
            (pred_dir / f"{signal_date}.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            fetch_range.return_value = (105.0, 99.0, 108.0)
            now = datetime(2026, 6, 12, 10, tzinfo=ZoneInfo("Australia/Sydney"))
            with patch("iterate_accuracy.PREDICTIONS_DIR", pred_dir):
                stats = collect_market_stats(horizon=5, now=now)
            self.assertIn("US", stats["picks"])
            self.assertEqual(stats["picks"]["US"]["count"], 1)
            self.assertGreaterEqual(stats["picks"]["US"]["avg_score"], 60)
            self.assertIn("US", stats["holdings"])
            self.assertEqual(stats["holdings"]["US"]["count"], 1)

    def test_save_and_load_tuning_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tuning_path = Path(tmp) / "tuning.json"
            with patch("tuning.TUNING_PATH", tuning_path):
                save_tuning(load_tuning())
                loaded = load_tuning()
            self.assertEqual(loaded["thresholds"]["buy"], 72)


if __name__ == "__main__":
    unittest.main()
