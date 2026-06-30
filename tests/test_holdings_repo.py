import os
import tempfile
import unittest
from pathlib import Path

from domain import db
from domain.holdings_repo import count_holdings, delete_holding, seed_if_empty, upsert_holding


class HoldingsRepoTests(unittest.TestCase):
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

    def test_upsert_and_delete(self) -> None:
        self.assertEqual(count_holdings(), 0)
        upsert_holding("RKLB", {"market": "US", "shares": 60, "cost_basis": 103, "name": "Rocket Lab"})
        self.assertEqual(count_holdings(), 1)
        upsert_holding("RKLB", {"shares": 70})
        delete_holding("RKLB")
        self.assertEqual(count_holdings(), 0)

    def test_seed_if_empty(self) -> None:
        imported = seed_if_empty()
        self.assertGreater(imported, 0)
        self.assertGreater(count_holdings(), 0)
        self.assertEqual(seed_if_empty(), 0)


if __name__ == "__main__":
    unittest.main()
