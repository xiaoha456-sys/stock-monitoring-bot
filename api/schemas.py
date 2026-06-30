from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class HoldingUpdate(BaseModel):
    shares: Optional[float] = None
    cost_basis: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    name: Optional[str] = None
    market: Optional[str] = None
    thesis: Optional[str] = None


class HoldingCreate(BaseModel):
    ticker: str
    market: str
    name: Optional[str] = None
    shares: Optional[float] = None
    cost_basis: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    thesis: Optional[str] = None


class OrderLegOut(BaseModel):
    price: float
    shares: int


class HoldingOrderOut(BaseModel):
    side: str
    legs: list[OrderLegOut] = Field(default_factory=list)
    note: str = ""


class HoldingOut(BaseModel):
    ticker: str
    name: str
    market: str
    shares: Optional[float] = None
    cost_basis: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    price: Optional[float] = None
    change_pct: Optional[float] = None
    currency: Optional[str] = None
    market_value: Optional[float] = None
    pnl_pct: Optional[float] = None
    pnl_amount: Optional[float] = None
    weight_pct: Optional[float] = None
    portfolio_action: str = ""
    action_reasons: list[str] = Field(default_factory=list)
    order: Optional[HoldingOrderOut] = None
    error: Optional[str] = None


class BriefSectionOut(BaseModel):
    title: str
    lines: list[str] = Field(default_factory=list)


class BriefOut(BaseModel):
    generated_at: str
    title: str
    conclusion: str
    sections: list[BriefSectionOut] = Field(default_factory=list)
    markdown: str = ""
