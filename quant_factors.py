#!/usr/bin/env python3
"""Cross-sectional multi-factor quant scoring.

Each candidate pool (per market) is ranked cross-sectionally: every factor is
z-scored across the pool, combined with signed weights, then mapped onto a
0-100 quant score. The quant score is blended with the rule-based technical
score in stock_bot; weights live in data/tuning.json so the accuracy
iteration loop can adjust them.
"""

from __future__ import annotations

from statistics import mean, stdev
from typing import Any

FACTOR_LABELS = {
    "momentum_20d": "20日动量",
    "momentum_60d": "60日动量",
    "trend_strength": "趋势强度",
    "volume_ratio": "量能",
    "volatility_20d": "波动率",
}

STRATEGY_PROFILES: dict[str, dict[str, float]] = {
    "volume_breakout": {
        "momentum_20d": 1.2,
        "volume_ratio": 1.5,
        "trend_strength": 1.0,
        "momentum_60d": 0.5,
        "volatility_20d": -0.4,
    },
    "capital_heat": {
        "momentum_20d": 1.0,
        "volume_ratio": 1.3,
        "trend_strength": 0.8,
        "momentum_60d": 0.6,
        "volatility_20d": -0.5,
    },
    "momentum_quality": {
        "momentum_20d": 0.9,
        "momentum_60d": 1.0,
        "trend_strength": 1.2,
        "volume_ratio": 0.6,
        "volatility_20d": -0.5,
    },
    "balanced_alpha": {
        "momentum_20d": 1.0,
        "momentum_60d": 0.8,
        "trend_strength": 1.0,
        "volume_ratio": 0.5,
        "volatility_20d": -0.6,
    },
}


def strategy_factor_weights(strategy: str) -> dict[str, float]:
    profile = STRATEGY_PROFILES.get(strategy, STRATEGY_PROFILES["volume_breakout"])
    return {key: float(value) for key, value in profile.items()}


def factor_value(snapshot: Any, factor: str) -> float:
    if factor == "trend_strength":
        sma = getattr(snapshot, "sma_50", 0.0)
        price = getattr(snapshot, "price", 0.0)
        return (price / sma - 1) * 100 if sma else 0.0
    return float(getattr(snapshot, factor, 0.0))


def cross_sectional_scores(
    snapshots: list[Any],
    factor_weights: dict[str, float],
) -> dict[str, tuple[float, str]]:
    """Return {ticker: (quant_score_0_100, dominant_factor_label)}.

    Pools smaller than 3 names lack a meaningful cross-section and return {}.
    """
    if len(snapshots) < 3:
        return {}

    z_by_factor: dict[str, dict[str, float]] = {}
    for factor in factor_weights:
        values = {snap.ticker: factor_value(snap, factor) for snap in snapshots}
        series = list(values.values())
        center = mean(series)
        spread = stdev(series) if len(series) > 1 else 0.0
        if spread <= 1e-9:
            z_by_factor[factor] = {ticker: 0.0 for ticker in values}
        else:
            z_by_factor[factor] = {
                ticker: max(-3.0, min((value - center) / spread, 3.0))
                for ticker, value in values.items()
            }

    total_weight = sum(abs(weight) for weight in factor_weights.values()) or 1.0
    results: dict[str, tuple[float, str]] = {}
    for snap in snapshots:
        contributions = {
            factor: weight * z_by_factor[factor][snap.ticker]
            for factor, weight in factor_weights.items()
        }
        combined = sum(contributions.values()) / total_weight
        score = max(0.0, min(50.0 + combined * 25.0, 100.0))
        dominant = max(contributions, key=lambda key: abs(contributions[key]))
        label = FACTOR_LABELS.get(dominant, dominant)
        direction = "强" if contributions[dominant] >= 0 else "弱"
        results[snap.ticker] = (score, f"{label}{direction}")
    return results
