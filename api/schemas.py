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
    buy_low: Optional[float] = None
    buy_high: Optional[float] = None
    levels_note: Optional[str] = None
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


class BriefRowOut(BaseModel):
    primary: str
    secondary: str = ""
    badge: str = ""
    badge_tone: str = "neutral"
    detail: str = ""
    subdetail: str = ""


class BriefSectionOut(BaseModel):
    title: str
    subtitle: str = ""
    kind: str = "text"
    rows: list[BriefRowOut] = Field(default_factory=list)
    lines: list[str] = Field(default_factory=list)


class BriefOut(BaseModel):
    generated_at: str
    title: str
    conclusion: str
    conclusion_items: list[str] = Field(default_factory=list)
    sections: list[BriefSectionOut] = Field(default_factory=list)
    markdown: str = ""


class MarketCashOut(BaseModel):
    market: str
    label: str
    available: float
    currency: str
    mode: str
    mode_label: str
    can_add_capital: bool
    display_amount: str
    note: str = ""


class MarketCashUpdate(BaseModel):
    available: Optional[float] = None
    mode: Optional[str] = None
    note: Optional[str] = None
