"""Ticker symbol normalization."""

from __future__ import annotations

_INVALID_TICKERS = frozenset(
    {
        "NASDAQ",
        "NYSE",
        "AMEX",
        "US",
        "CN",
        "AU",
        "HK",
        "LSE",
    }
)


def normalize_ticker(ticker: str) -> str:
    text = ticker.strip()
    if not text:
        return text
    if "." in text:
        base, suffix = text.rsplit(".", 1)
        return f"{base.upper()}.{suffix.upper()}"
    return text.upper()


def validate_ticker(ticker: str) -> str:
    normalized = normalize_ticker(ticker)
    if not normalized:
        raise ValueError("股票代码不能为空")
    if normalized in _INVALID_TICKERS:
        raise ValueError(f"{normalized} 是交易所代码，请填写具体股票代码（如 SPCX、NVDA）")
    return normalized
