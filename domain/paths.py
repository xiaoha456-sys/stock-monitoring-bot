"""Repository paths and timezone constants."""

from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "portfolio_config.json"
PREDICTIONS_DIR = ROOT / "data" / "predictions"
REVIEW_SCORES_PATH = ROOT / "data" / "review_scores.json"
DEFAULT_LIVE_HOLDINGS_PATH = ROOT / "data" / "holdings_live.json"
SYDNEY = ZoneInfo("Australia/Sydney")
