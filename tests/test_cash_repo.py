import os
import tempfile
import unittest
from pathlib import Path

from domain import db
from domain.cash_repo import count_market_cash, seed_if_empty, update_market_cash


class CashRepoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._db_path = Path(self._tmpdir.name) / "test.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self._db_path}"
        db.configure_engine(os.environ["DATABASE_URL"])
        db.init_db()

    def tearDown(self) -> None:
        os.environ.pop("DATABASE_URL", None)
        db.configure_engine()
        self._tmpdir.cleanup()

    def test_seed_and_update(self) -> None:
        self.assertGreater(seed_if_empty(), 0)
        self.assertGreater(count_market_cash(), 0)
        updated = update_market_cash("US", {"available": 25000, "mode": "deploy"})
        self.assertEqual(updated["available"], 25000)
        self.assertTrue(updated["can_add_capital"])


if __name__ == "__main__":
    unittest.main()
