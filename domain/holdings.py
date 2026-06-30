"""Holdings storage: database (default) or legacy JSON overlay."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from domain.config import load_config_raw
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


def _holdings_source_config(config: dict[str, Any]) -> dict[str, Any]:
    return dict(config.get("holdings_source", {}))


def _use_database(config: dict[str, Any] | None = None) -> bool:
    if config is None:
        config = load_config_raw()
    source = _holdings_source_config(config)
    if not source.get("enabled", True):
        return False
    return source.get("storage", "database") != "file"


def live_holdings_path(config: dict[str, Any] | None = None) -> Path:
    if config is None:
        config = load_config_raw()
    source = _holdings_source_config(config)
    rel = str(source.get("live_file", "data/holdings_live.json"))
    return ROOT / rel


def live_holdings_enabled(config: dict[str, Any] | None = None) -> bool:
    if config is None:
        config = load_config_raw()
    source = _holdings_source_config(config)
    return bool(source.get("enabled", True))


def _read_live_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_entry(ticker: str, entry: dict[str, Any], base: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base or {})
    merged.update({key: entry[key] for key in entry if entry[key] is not None})
    merged["ticker"] = ticker
    if not merged.get("market"):
        raise ValueError(f"{ticker}: market is required for new holdings")
    return merged


def merge_holdings(
    base_holdings: dict[str, Any],
    live_holdings: dict[str, Any],
) -> dict[str, Any]:
    merged = {ticker: dict(info) for ticker, info in base_holdings.items()}
    for ticker, patch in live_holdings.items():
        if not isinstance(patch, dict):
            continue
        current = merged.get(ticker, {})
        merged[ticker] = _normalize_entry(ticker, patch, current)
    return merged


def get_live_holdings(config: dict[str, Any] | None = None) -> dict[str, Any]:
    if config is None:
        config = load_config_raw()
    if not live_holdings_enabled(config):
        return {}
    if _use_database(config):
        from domain.holdings_repo import list_holdings_dict

        return list_holdings_dict()
    payload = _read_live_payload(live_holdings_path(config))
    holdings = payload.get("holdings", {})
    return dict(holdings) if isinstance(holdings, dict) else {}


def resolve_holdings(config: dict[str, Any]) -> dict[str, Any]:
    if _use_database(config):
        from domain.holdings_repo import list_holdings_dict, seed_if_empty

        seed_if_empty()
        holdings = list_holdings_dict()
        if holdings:
            return holdings

    base = dict(config.get("holdings", {}))
    live = get_live_holdings(config) if not _use_database(config) else {}
    if not live:
        return base
    return merge_holdings(base, live)


def save_live_holdings(
    holdings: dict[str, Any],
    *,
    path: Path | None = None,
    config: dict[str, Any] | None = None,
) -> Path:
    if config is None:
        config = load_config_raw()
    if _use_database(config):
        from domain.holdings_repo import upsert_holding

        for ticker, fields in holdings.items():
            upsert_holding(ticker, fields)
        return ROOT / "data" / "portfolio.db"
    target = path or live_holdings_path(config)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": datetime.now(SYDNEY).isoformat(),
        "holdings": holdings,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def update_holding(
    ticker: str,
    fields: dict[str, Any],
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if config is None:
        config = load_config_raw()
    if _use_database(config):
        from domain.holdings_repo import upsert_holding

        base = dict(config.get("holdings", {}).get(ticker, {}))
        return upsert_holding(ticker, fields, base=base)

    live = get_live_holdings(config)
    base = dict(config.get("holdings", {}).get(ticker, {}))
    patch = dict(live.get(ticker, {}))
    patch.update(fields)
    merged = _normalize_entry(ticker, patch, base)
    live[ticker] = {key: merged.get(key) for key in _HOLDING_FIELDS if key in merged}
    save_live_holdings(live, config=config)
    return merged


def remove_holding(ticker: str, *, config: dict[str, Any] | None = None) -> None:
    if config is None:
        config = load_config_raw()
    if _use_database(config):
        from domain.holdings_repo import delete_holding

        delete_holding(ticker)
        return
    live = get_live_holdings(config)
    if ticker in live:
        del live[ticker]
        save_live_holdings(live, config=config)


def import_holdings_csv(
    csv_path: Path,
    *,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if config is None:
        config = load_config_raw()
    live = get_live_holdings(config) if not _use_database(config) else {}
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            ticker = str(row.get("ticker", "") or "").strip().upper()
            if not ticker:
                continue
            patch: dict[str, Any] = {}
            if row.get("shares") not in (None, ""):
                patch["shares"] = float(row["shares"])
            if row.get("cost_basis") not in (None, ""):
                patch["cost_basis"] = float(row["cost_basis"])
            if row.get("market") not in (None, ""):
                patch["market"] = str(row["market"]).strip().upper()
            if row.get("name") not in (None, ""):
                patch["name"] = str(row["name"]).strip()
            if row.get("target_price") not in (None, ""):
                patch["target_price"] = float(row["target_price"])
            if row.get("stop_loss") not in (None, ""):
                patch["stop_loss"] = float(row["stop_loss"])
            if _use_database(config):
                base = dict(config.get("holdings", {}).get(ticker, {}))
                update_holding(ticker, patch, config=config)
            else:
                base = dict(config.get("holdings", {}).get(ticker, {}))
                existing = dict(live.get(ticker, {}))
                existing.update(patch)
                live[ticker] = {
                    key: _normalize_entry(ticker, existing, base).get(key)
                    for key in _HOLDING_FIELDS
                    if key in _normalize_entry(ticker, existing, base)
                }
    if not _use_database(config):
        save_live_holdings(live, config=config)
    return get_live_holdings(config)


def format_holdings_table(holdings: dict[str, Any]) -> str:
    lines = ["| 标的 | 市场 | 股数 | 成本 | 止损 | 目标 |", "| --- | --- | --- | --- | --- | --- |"]
    for ticker, info in sorted(holdings.items()):
        shares = info.get("shares")
        shares_text = "—" if shares in (None, "") else f"{float(shares):g}"
        cost = info.get("cost_basis")
        cost_text = "—" if cost in (None, "") else f"{float(cost):g}"
        stop = info.get("stop_loss")
        stop_text = "—" if stop in (None, "") else f"{float(stop):g}"
        target = info.get("target_price")
        target_text = "—" if target in (None, "") else f"{float(target):g}"
        lines.append(
            f"| {ticker} | {info.get('market', '—')} | {shares_text} | {cost_text} | {stop_text} | {target_text} |"
        )
    return "\n".join(lines)
