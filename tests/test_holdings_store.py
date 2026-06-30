import json
import tempfile
import unittest
from pathlib import Path

from holdings_store import merge_holdings, resolve_holdings, update_holding
from stock_bot import load_config_raw


class HoldingsStoreTests(unittest.TestCase):
    def test_merge_overrides_base(self):
        base = {
            "RKLB": {"market": "US", "shares": 30, "cost_basis": 103, "name": "Rocket Lab"},
        }
        live = {"RKLB": {"shares": 60}}
        merged = merge_holdings(base, live)
        self.assertEqual(merged["RKLB"]["shares"], 60)
        self.assertEqual(merged["RKLB"]["cost_basis"], 103)

    def test_resolve_holdings_from_config(self):
        config = load_config_raw()
        config["holdings_source"] = {"enabled": False}
        holdings = resolve_holdings(config)
        self.assertIn("NVDA", holdings)

    def test_save_live_holdings(self):
        with tempfile.TemporaryDirectory() as tmp:
            live_path = Path(tmp) / "holdings_live.json"
            from holdings_store import save_live_holdings

            save_live_holdings(
                {"MU": {"market": "US", "shares": 5, "cost_basis": 900}},
                path=live_path,
                config={"holdings_source": {"enabled": True, "storage": "file"}},
            )
            payload = json.loads(live_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["holdings"]["MU"]["shares"], 5)


if __name__ == "__main__":
    unittest.main()
