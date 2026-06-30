"""Daily stop/target levels from market analysis + regime."""

from __future__ import annotations

from dataclasses import dataclass

from market_regime import MarketRegime
from stock_bot import Recommendation


@dataclass(frozen=True)
class DynamicLevels:
    buy_low: float
    buy_high: float
    target_price: float
    stop_loss: float
    note: str = ""


def compute_dynamic_levels(
    rec: Recommendation,
    regime: MarketRegime | None = None,
) -> DynamicLevels:
    """Adjust recommendation price bands using benchmark regime."""
    snap = rec.snapshot
    price = snap.price
    atr = max(snap.atr_14, price * 0.005)

    buy_low = rec.buy_low
    buy_high = rec.buy_high
    target = rec.target_price
    stop = rec.stop_loss
    notes: list[str] = ["基于当日技术面与 ATR"]

    if regime:
        if regime.label == "弱势":
            stop = max(stop, price - atr * 1.0)
            stop = min(stop, price * 0.985)
            target = min(target, price + atr * 1.8)
            notes.append(f"{regime.index_name}偏弱，收紧止损/目标")
        elif regime.label == "强势":
            target = max(target, price + atr * 2.2)
            stop = max(stop, price - atr * 2.2)
            notes.append(f"{regime.index_name}偏强，放宽目标")
        else:
            notes.append(f"{regime.index_name}震荡，按标准 ATR 带")

    return DynamicLevels(
        buy_low=round(buy_low, 2),
        buy_high=round(buy_high, 2),
        target_price=round(target, 2),
        stop_loss=round(stop, 2),
        note="；".join(notes),
    )
