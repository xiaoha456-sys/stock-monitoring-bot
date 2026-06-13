#!/usr/bin/env python3
"""Load and persist auto-tuned scoring parameters."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
TUNING_PATH = ROOT / "data" / "tuning.json"
TUNING_HISTORY_PATH = ROOT / "data" / "tuning_history.jsonl"
SYDNEY = ZoneInfo("Australia/Sydney")

DEFAULT_TUNING: dict[str, Any] = {
    "version": 1,
    "updated_at": "",
    "thresholds": {
        "buy": 72,
        "watch": 58,
        "hold": 45,
        "reduce": 32,
    },
    "price_levels": {
        "buy_low_atr": 0.6,
        "buy_high_atr": 0.2,
        "target_atr": 2.5,
        "target_atr_neutral": 1.2,
        "stop_atr": 2.0,
        "stop_max_drawdown_pct": 0.08,
    },
    "quant": {
        "enabled": True,
        "rule_weight": 0.6,
        "quant_weight": 0.4,
        "factor_weights": {
            "momentum_20d": 1.2,
            "volume_ratio": 1.5,
            "trend_strength": 1.0,
            "momentum_60d": 0.5,
            "volatility_20d": -0.4
        },
    },
    "markets": {
        "US": {
            "quant_strategy": "volume_breakout"
        },
        "AU": {
            "quant_strategy": "volume_breakout"
        },
        "CN": {
            "score_blend": {"screen": 0.55, "technical": 0.45},
            "alphasift_strategy": "volume_breakout",
        }
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_tuning() -> dict[str, Any]:
    if not TUNING_PATH.exists():
        return deepcopy(DEFAULT_TUNING)
    stored = json.loads(TUNING_PATH.read_text(encoding="utf-8"))
    return _deep_merge(DEFAULT_TUNING, stored)


def save_tuning(tuning: dict[str, Any]) -> Path:
    TUNING_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = deepcopy(tuning)
    payload["updated_at"] = datetime.now(SYDNEY).isoformat()
    TUNING_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return TUNING_PATH


def append_tuning_history(entry: dict[str, Any]) -> None:
    TUNING_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {"at": datetime.now(SYDNEY).isoformat(), **entry}
    with TUNING_HISTORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def get_thresholds() -> dict[str, float]:
    tuning = load_tuning()
    defaults = DEFAULT_TUNING["thresholds"]
    current = tuning.get("thresholds", {})
    return {key: float(current.get(key, defaults[key])) for key in defaults}


def get_price_level_params() -> dict[str, float]:
    tuning = load_tuning()
    defaults = DEFAULT_TUNING["price_levels"]
    current = tuning.get("price_levels", {})
    return {key: float(current.get(key, defaults[key])) for key in defaults}


def get_quant_params() -> dict[str, Any]:
    tuning = load_tuning()
    defaults = DEFAULT_TUNING["quant"]
    current = tuning.get("quant", {})
    if isinstance(current, dict):
        return _deep_merge(defaults, current)
    return deepcopy(defaults)


def get_market_tuning(market_key: str) -> dict[str, Any]:
    tuning = load_tuning()
    defaults = DEFAULT_TUNING["markets"].get(market_key, {})
    current = tuning.get("markets", {}).get(market_key, {})
    if isinstance(defaults, dict) and isinstance(current, dict):
        return _deep_merge(defaults, current)
    return deepcopy(defaults) if defaults else {}
