"""Per-market available cash persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from domain.config import load_config_raw
from domain.db import get_session, init_db
from domain.models import MarketCashRow
from domain.paths import SYDNEY

MARKET_ORDER = ("US", "CN", "AU")
DEFAULT_CURRENCY = {"US": "USD", "CN": "CNY", "AU": "AUD"}


def _config_cash() -> dict[str, dict[str, Any]]:
    return dict(load_config_raw().get("portfolio", {}).get("cash", {}))


def count_market_cash() -> int:
    session = get_session()
    try:
        return session.query(MarketCashRow).count()
    finally:
        session.close()


def list_market_cash() -> dict[str, dict[str, Any]]:
    session = get_session()
    try:
        rows = session.query(MarketCashRow).order_by(MarketCashRow.market).all()
        return {row.market: row.to_dict() for row in rows}
    finally:
        session.close()


def get_market_cash(market: str) -> dict[str, Any] | None:
    market = market.upper()
    session = get_session()
    try:
        row = session.get(MarketCashRow, market)
        return row.to_dict() if row else None
    finally:
        session.close()


def seed_if_empty() -> int:
    init_db()
    if count_market_cash() > 0:
        return 0

    config_cash = _config_cash()
    session = get_session()
    try:
        count = 0
        for market in MARKET_ORDER:
            entry = dict(config_cash.get(market, {}))
            if not entry and market not in config_cash:
                continue
            row = MarketCashRow(
                market=market,
                available=float(entry.get("available", 0) or 0),
                currency=str(entry.get("currency", DEFAULT_CURRENCY[market])).upper(),
                mode=str(entry.get("mode", "rotate_only")),
                can_add_capital=bool(entry.get("can_add_capital", False)),
                note=entry.get("note"),
                updated_at=datetime.now(SYDNEY).replace(tzinfo=None),
            )
            session.add(row)
            count += 1
        session.commit()
        return count
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_market_cash(market: str, fields: dict[str, Any]) -> dict[str, Any]:
    market = market.upper()
    if market not in MARKET_ORDER:
        raise ValueError(f"unsupported market: {market}")

    session = get_session()
    try:
        row = session.get(MarketCashRow, market)
        if row is None:
            config_entry = _config_cash().get(market, {})
            row = MarketCashRow(
                market=market,
                available=float(config_entry.get("available", 0) or 0),
                currency=str(config_entry.get("currency", DEFAULT_CURRENCY[market])).upper(),
                mode=str(config_entry.get("mode", "rotate_only")),
                can_add_capital=bool(config_entry.get("can_add_capital", False)),
                note=config_entry.get("note"),
            )
            session.add(row)

        if "available" in fields and fields["available"] is not None:
            row.available = float(fields["available"])
        if "mode" in fields and fields["mode"] is not None:
            row.mode = str(fields["mode"])
            row.can_add_capital = row.mode == "deploy"
        if "note" in fields and fields["note"] is not None:
            row.note = str(fields["note"])
        if "can_add_capital" in fields and fields["can_add_capital"] is not None:
            row.can_add_capital = bool(fields["can_add_capital"])

        row.updated_at = datetime.now(SYDNEY).replace(tzinfo=None)
        session.commit()
        session.refresh(row)
        return row.to_dict()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
