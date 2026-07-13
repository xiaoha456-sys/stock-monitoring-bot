from __future__ import annotations

import os
import time
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    BriefOut,
    BriefSectionOut,
    HoldingCreate,
    HoldingOrderOut,
    HoldingOut,
    HoldingUpdate,
    MarketCashOut,
    MarketCashUpdate,
    OrderLegOut,
)
from domain.brief import build_today_brief
from domain.cash_repo import seed_if_empty as seed_cash_if_empty
from domain.cash_repo import update_market_cash
from domain.db import init_db
from domain.holdings import update_holding
from domain.holdings_repo import delete_holding, get_holding_record, seed_if_empty, upsert_holding
from domain.paths import ROOT
from domain.portfolio import build_holdings_list
from domain.predictions_repo import import_files_if_empty
from domain.review_repo import import_file_if_empty

load_dotenv(ROOT / ".env")

_extra_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]
_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "capacitor://localhost",
    "ionic://localhost",
    *_extra_origins,
]

_HOLDINGS_CACHE: tuple[float, list[dict[str, Any]], dict[str, str]] | None = None
_HOLDINGS_CACHE_TTL = 120.0


def _invalidate_holdings_cache() -> None:
    global _HOLDINGS_CACHE
    _HOLDINGS_CACHE = None


def _cached_holdings_list() -> tuple[list[dict[str, Any]], dict[str, str]]:
    global _HOLDINGS_CACHE
    now = time.time()
    if _HOLDINGS_CACHE and now - _HOLDINGS_CACHE[0] < _HOLDINGS_CACHE_TTL:
        return _HOLDINGS_CACHE[1], _HOLDINGS_CACHE[2]
    items, errors = build_holdings_list()
    _HOLDINGS_CACHE = (now, items, errors)
    return items, errors


def _holding_out_from_record(record: dict[str, Any]) -> HoldingOut:
    market = str(record.get("market") or "US")
    currency = {"US": "USD", "CN": "CNY", "AU": "AUD"}.get(market, "USD")
    return HoldingOut(
        ticker=record["ticker"],
        name=str(record.get("name") or record["ticker"]),
        market=market,
        shares=record.get("shares"),
        cost_basis=record.get("cost_basis"),
        target_price=record.get("target_price"),
        stop_loss=record.get("stop_loss"),
        currency=currency,
        portfolio_action="继续观察",
        action_reasons=["已保存，等待行情刷新"],
        order=HoldingOrderOut(side="观望", legs=[], note=""),
        error=None,
    )


def _holding_out_from_item(item: dict[str, Any]) -> HoldingOut:
    order_data = item.get("order") or {}
    legs = [OrderLegOut(**leg) for leg in order_data.get("legs", [])]
    order = HoldingOrderOut(
        side=order_data.get("side", "观望"),
        legs=legs,
        note=order_data.get("note", ""),
    )
    return HoldingOut(
        ticker=item["ticker"],
        name=item["name"],
        market=item["market"],
        shares=item.get("shares"),
        cost_basis=item.get("cost_basis"),
        target_price=item.get("target_price"),
        stop_loss=item.get("stop_loss"),
        buy_low=item.get("buy_low"),
        buy_high=item.get("buy_high"),
        levels_note=item.get("levels_note"),
        price=item.get("price"),
        change_pct=item.get("change_pct"),
        currency=item.get("currency"),
        market_value=item.get("market_value"),
        pnl_pct=item.get("pnl_pct"),
        pnl_amount=item.get("pnl_amount"),
        weight_pct=item.get("weight_pct"),
        portfolio_action=item.get("portfolio_action", ""),
        action_reasons=item.get("action_reasons", []),
        order=order,
        error=item.get("error"),
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    seed_if_empty()
    seed_cash_if_empty()
    import_files_if_empty()
    import_file_if_empty()
    yield


app = FastAPI(title="Portfolio Brief API", version="0.4.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins,
    allow_origin_regex=r"https?://((localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+)(:\d+)?|capacitor://localhost|ionic://localhost)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/holdings", response_model=list[HoldingOut])
def list_holdings() -> list[HoldingOut]:
    items, _ = _cached_holdings_list()
    return [_holding_out_from_item(item) for item in items]


@app.post("/api/holdings", response_model=HoldingOut, status_code=201)
def create_holding(payload: HoldingCreate) -> HoldingOut:
    ticker = normalize_ticker(payload.ticker)
    fields = payload.model_dump(exclude={"ticker"}, exclude_none=True)
    try:
        record = upsert_holding(ticker, fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _invalidate_holdings_cache()
    try:
        return get_holding(ticker)
    except HTTPException:
        return _holding_out_from_record(record)


@app.get("/api/holdings/{ticker}", response_model=HoldingOut)
def get_holding(ticker: str) -> HoldingOut:
    ticker = normalize_ticker(ticker)
    for item in list_holdings():
        if normalize_ticker(item.ticker) == ticker:
            return item
    record = get_holding_record(ticker)
    if record:
        return _holding_out_from_record(record)
    raise HTTPException(status_code=404, detail="holding not found")


@app.put("/api/holdings/{ticker}", response_model=HoldingOut)
def patch_holding(ticker: str, payload: HoldingUpdate) -> HoldingOut:
    ticker = normalize_ticker(ticker)
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")
    try:
        record = update_holding(ticker, fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _invalidate_holdings_cache()
    try:
        return get_holding(ticker)
    except HTTPException:
        return _holding_out_from_record(record)


@app.delete("/api/holdings/{ticker}", status_code=204)
def delete_holding_route(ticker: str) -> None:
    if not delete_holding(normalize_ticker(ticker)):
        raise HTTPException(status_code=404, detail="holding not found")
    _invalidate_holdings_cache()


def _market_cash_out(market: str, entry: dict[str, Any]) -> MarketCashOut:
    from portfolio_manager import CASH_MODE_LABELS, MARKET_LABELS, format_market_cash_amount

    mode = str(entry.get("mode", "rotate_only"))
    return MarketCashOut(
        market=market,
        label=MARKET_LABELS.get(market, market),
        available=float(entry.get("available", 0) or 0),
        currency=str(entry.get("currency", "USD")).upper(),
        mode=mode,
        mode_label=CASH_MODE_LABELS.get(mode, mode),
        can_add_capital=bool(entry.get("can_add_capital", False)),
        display_amount=format_market_cash_amount(market),
        note=str(entry.get("note") or ""),
    )


@app.get("/api/cash", response_model=list[MarketCashOut])
def list_market_cash_api() -> list[MarketCashOut]:
    from portfolio_manager import MARKET_ORDER, get_market_cash_config

    cfg = get_market_cash_config()
    return [_market_cash_out(market, cfg.get(market, {})) for market in MARKET_ORDER if market in cfg]


@app.put("/api/cash/{market}", response_model=MarketCashOut)
def patch_market_cash(market: str, payload: MarketCashUpdate) -> MarketCashOut:
    market_key = market.upper()
    fields = payload.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")
    if "mode" in fields and fields["mode"] not in ("deploy", "rotate_only"):
        raise HTTPException(status_code=400, detail="mode must be deploy or rotate_only")
    try:
        if "mode" in fields:
            fields["can_add_capital"] = fields["mode"] == "deploy"
        updated = update_market_cash(market_key, fields)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _invalidate_holdings_cache()
    return _market_cash_out(market_key, updated)


@app.get("/api/brief/today", response_model=BriefOut)
def today_brief() -> BriefOut:
    try:
        data = build_today_brief()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return BriefOut(
        generated_at=data["generated_at"],
        title=data["title"],
        conclusion=data["conclusion"],
        conclusion_items=data.get("conclusion_items", []),
        sections=[BriefSectionOut(**section) for section in data.get("sections", [])],
        markdown=data.get("markdown", ""),
    )
