"""Holdings persistence in SQLite/Postgres."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from domain.config import load_config_raw
from domain.db import get_session, init_db
from domain.models import HoldingRow
from domain.paths import ROOT, SYDNEY

_HOLDING_FIELDS = (
    "name",
    "market",
    "shares",
    "cost_basis",
    "target_price",
    "stop_loss",
    "thesis",
    "max_weight_pct",
)


def _normalize_entry(ticker: str, entry: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
    merged = dict(base or {})
    merged.update({key: entry[key] for key in entry if entry[key] is not None})
    merged["ticker"] = ticker
    if not merged.get("market"):
        raise ValueError(f"{ticker}: market is required for new holdings")
    return merged


def _row_from_dict(ticker: str, data: dict[str, Any]) -> HoldingRow:
    normalized = _normalize_entry(ticker, data)
    return HoldingRow(
        ticker=ticker,
        name=normalized.get("name"),
        market=str(normalized["market"]).upper(),
        shares=normalized.get("shares"),
        cost_basis=normalized.get("cost_basis"),
        target_price=normalized.get("target_price"),
        stop_loss=normalized.get("stop_loss"),
        thesis=normalized.get("thesis"),
        max_weight_pct=normalized.get("max_weight_pct"),
        updated_at=datetime.now(SYDNEY).replace(tzinfo=None),
    )


def list_holdings_dict() -> dict[str, Any]:
    session = get_session()
    try:
        rows = session.query(HoldingRow).order_by(HoldingRow.ticker).all()
        return {row.ticker: row.to_dict() for row in rows}
    finally:
        session.close()


def count_holdings() -> int:
    session = get_session()
    try:
        return session.query(HoldingRow).count()
    finally:
        session.close()


def upsert_holding(ticker: str, fields: dict[str, Any], *, base: dict[str, Any] | None = None) -> dict[str, Any]:
    session = get_session()
    try:
        existing = session.get(HoldingRow, ticker)
        patch = dict(fields)
        if existing:
            current = existing.to_dict()
            merged = _normalize_entry(ticker, {**current, **patch}, base)
            for key in _HOLDING_FIELDS:
                if key in merged:
                    setattr(existing, key, merged[key])
            existing.updated_at = datetime.now(SYDNEY).replace(tzinfo=None)
            row = existing
        else:
            row = _row_from_dict(ticker, {**(base or {}), **patch})
            session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_dict()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def delete_holding(ticker: str) -> bool:
    session = get_session()
    try:
        row = session.get(HoldingRow, ticker)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _live_json_path(config: dict[str, Any]) -> Path:
    rel = str(config.get("holdings_source", {}).get("live_file", "data/holdings_live.json"))
    return ROOT / rel


def _load_live_json(config: dict[str, Any]) -> dict[str, Any]:
    path = _live_json_path(config)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    holdings = payload.get("holdings", {})
    return dict(holdings) if isinstance(holdings, dict) else {}


def seed_if_empty() -> int:
    """Import portfolio_config + holdings_live.json into DB when empty."""
    init_db()
    if count_holdings() > 0:
        return 0

    config = load_config_raw()
    base_holdings = dict(config.get("holdings", {}))
    live_holdings = _load_live_json(config)

    merged: dict[str, dict[str, Any]] = {}
    for ticker, info in base_holdings.items():
        merged[ticker] = dict(info)
    for ticker, patch in live_holdings.items():
        if not isinstance(patch, dict):
            continue
        current = merged.get(ticker, {})
        merged[ticker] = _normalize_entry(ticker, {**current, **patch}, current if current else None)

    for ticker, info in merged.items():
        upsert_holding(ticker, info)

    return len(merged)
