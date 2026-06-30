"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from domain.db import Base


class HoldingRow(Base):
    __tablename__ = "holdings"

    ticker: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    market: Mapped[str] = mapped_column(String(8))
    shares: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_basis: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    thesis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    max_weight_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "market": self.market,
            "shares": self.shares,
            "cost_basis": self.cost_basis,
            "target_price": self.target_price,
            "stop_loss": self.stop_loss,
            "thesis": self.thesis,
            "max_weight_pct": self.max_weight_pct,
        }


class MarketCashRow(Base):
    __tablename__ = "market_cash"

    market: Mapped[str] = mapped_column(String(8), primary_key=True)
    available: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    mode: Mapped[str] = mapped_column(String(16), default="rotate_only")
    can_add_capital: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "currency": self.currency,
            "mode": self.mode,
            "can_add_capital": self.can_add_capital,
            "note": self.note,
        }
