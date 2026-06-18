#!/usr/bin/env python3
"""A-share tradability rules: boards the user cannot trade."""

from __future__ import annotations

from typing import Any

from stock_bot import load_config

_BOARD_PREFIXES = {
    "star": ("688",),
    "chinext": ("300",),
}


def _cn_tradable_config() -> dict[str, Any]:
    return dict(load_config().get("markets", {}).get("CN", {}).get("tradable", {}))


def cn_code_from_ticker(ticker: str) -> str:
    text = str(ticker).strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[-6:].zfill(6) if digits else ""


def excluded_prefixes() -> tuple[str, ...]:
    cfg = _cn_tradable_config()
    prefixes: list[str] = []
    for board in cfg.get("exclude_boards", ("star", "chinext")):
        prefixes.extend(_BOARD_PREFIXES.get(str(board), ()))
    for prefix in cfg.get("exclude_prefixes", ()):
        text = str(prefix).strip()
        if text and text not in prefixes:
            prefixes.append(text)
    return tuple(prefixes)


def is_cn_restricted_board(ticker_or_code: str) -> bool:
    code = cn_code_from_ticker(ticker_or_code)
    if not code:
        return False
    return any(code.startswith(prefix) for prefix in excluded_prefixes())


def filter_tradable_cn_tickers(tickers: list[str]) -> list[str]:
    return [ticker for ticker in tickers if not is_cn_restricted_board(ticker)]


def tradable_filter_note() -> str:
    prefixes = excluded_prefixes()
    if not prefixes:
        return ""
    labels = []
    if "688" in prefixes:
        labels.append("科创板")
    if "300" in prefixes:
        labels.append("创业板")
    extra = [p for p in prefixes if p not in ("688", "300")]
    if extra:
        labels.extend(extra)
    return f"已排除不可交易板块：{'、'.join(labels)}"
