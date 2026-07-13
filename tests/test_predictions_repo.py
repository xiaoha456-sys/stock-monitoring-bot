import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from domain import db
from domain.predictions_repo import (
    import_files_if_empty,
    iter_prediction_snapshots,
    load_prediction_snapshot,
    save_prediction_snapshot,
)
from domain.review_repo import append_review_run, load_review_history


class PredictionsRepoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._root = Path(self._tmpdir.name)
        self._db_path = self._root / "portfolio.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self._db_path}"
        db.configure_engine(os.environ["DATABASE_URL"])
        db.init_db()

    def tearDown(self) -> None:
        os.environ.pop("DATABASE_URL", None)
        db.configure_engine()
        self._tmpdir.cleanup()

    def test_save_and_load_prediction(self) -> None:
        pred_dir = self._root / "predictions"
        payload = {"date": "2026-06-01", "generated_at": "2026-06-01T09:00:00", "markets": {}}
        with mock.patch("domain.predictions_repo.PREDICTIONS_DIR", pred_dir):
            save_prediction_snapshot("2026-06-01", payload)
            loaded = load_prediction_snapshot("2026-06-01")
            snapshots = list(iter_prediction_snapshots())
        self.assertEqual(loaded["date"], "2026-06-01")
        self.assertEqual(snapshots, [("2026-06-01", loaded)])

    def test_import_legacy_json_files(self) -> None:
        pred_dir = self._root / "predictions"
        pred_dir.mkdir()
        legacy = {"date": "2026-05-20", "markets": {"US": {"picks": [], "watchlist": []}}}
        (pred_dir / "2026-05-20.json").write_text(json.dumps(legacy), encoding="utf-8")

        with mock.patch("domain.predictions_repo.PREDICTIONS_DIR", pred_dir):
            imported = import_files_if_empty()
            self.assertEqual(imported, 1)
            loaded = load_prediction_snapshot("2026-05-20")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["date"], "2026-05-20")


class ReviewRepoTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._root = Path(self._tmpdir.name)
        self._db_path = self._root / "portfolio.db"
        os.environ["DATABASE_URL"] = f"sqlite:///{self._db_path}"
        db.configure_engine(os.environ["DATABASE_URL"])
        db.init_db()

    def tearDown(self) -> None:
        os.environ.pop("DATABASE_URL", None)
        db.configure_engine()
        self._tmpdir.cleanup()

    def test_append_review_run(self) -> None:
        review_file = self._root / "review_scores.json"
        run = {"reviewed_at": "2026-06-07T09:00:00", "horizons": {}}
        with mock.patch("domain.review_repo.REVIEW_SCORES_PATH", review_file):
            history = append_review_run(run)
        self.assertEqual(len(history["runs"]), 1)
        reloaded = load_review_history()
        self.assertEqual(reloaded["runs"][0]["reviewed_at"], run["reviewed_at"])
        self.assertTrue(review_file.exists())


if __name__ == "__main__":
    unittest.main()
