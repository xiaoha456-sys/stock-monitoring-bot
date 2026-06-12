#!/usr/bin/env python3
"""Generate a Chinese stock report and deliver it to WeChat via ServerChan."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf


TICKERS = ("NVDA", "MU", "QCOM", "TSLA", "CBA.AX", "WTC.AX", "TLX.AX")
NEWS_QUERIES = {
    "NVDA": ("NVIDIA", ("nvidia", "nvda")),
    "MU": ("Micron Technology", ("micron", "mu stock")),
    "QCOM": ("Qualcomm", ("qualcomm", "qcom")),
    "TSLA": ("Tesla", ("tesla", "tsla")),
    "CBA.AX": (
        "Commonwealth Bank of Australia",
        ("commonwealth bank", "cba stock", "cba shares"),
    ),
    "WTC.AX": ("WiseTech Global", ("wisetech", "wtc stock", "wtc shares")),
    "TLX.AX": ("Telix Pharmaceuticals", ("telix", "tlx stock", "tlx shares")),
}
SYDNEY = ZoneInfo("Australia/Sydney")


@dataclass(frozen=True)
class StockSnapshot:
    ticker: str
    price: float
    currency: str
    change_pct: float
    week_52_low: float
    week_52_high: float
    week_52_position: float
    rsi_14: float
    sma_50: float
    sma_200: float
    headlines: tuple[str, ...]


def calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Return RSI using Wilder-style exponential smoothing."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    relative_strength = avg_gain / avg_loss.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + relative_strength))
    return rsi.mask((avg_loss == 0) & (avg_gain > 0), 100).fillna(50)


def _news_value(article: dict[str, Any], key: str) -> Any:
    content = article.get("content")
    if isinstance(content, dict) and key in content:
        return content[key]
    return article.get(key)


def _news_url(article: dict[str, Any]) -> str:
    for key in ("canonicalUrl", "clickThroughUrl"):
        value = _news_value(article, key)
        if isinstance(value, dict) and value.get("url"):
            return str(value["url"])
    return str(_news_value(article, "link") or "")


def fetch_headlines(ticker: str, limit: int = 2) -> tuple[str, ...]:
    """Fetch a small set of Yahoo Finance headlines without failing the report."""
    query, aliases = NEWS_QUERIES[ticker]
    try:
        articles = yf.Search(
            query,
            max_results=1,
            news_count=max(limit * 4, 8),
            lists_count=0,
            include_nav_links=False,
            include_research=False,
            raise_errors=False,
        ).news
    except Exception as exc:
        print(f"Warning: news fetch failed for {ticker}: {exc}", file=sys.stderr)
        return ()

    headlines: list[str] = []
    seen: set[str] = set()
    for article in articles or []:
        title = str(_news_value(article, "title") or "").strip()
        if not title or title.casefold() in seen:
            continue
        summary = str(_news_value(article, "summary") or "")
        searchable = f"{title} {summary}".casefold()
        if not any(alias in searchable for alias in aliases):
            continue
        seen.add(title.casefold())
        url = _news_url(article)
        headlines.append(f"{title} ({url})" if url else title)
        if len(headlines) == limit:
            break
    return tuple(headlines)


def fetch_snapshot(ticker: str) -> StockSnapshot:
    stock = yf.Ticker(ticker)
    history = stock.history(period="2y", interval="1d", auto_adjust=True)
    close = history.get("Close", pd.Series(dtype=float)).dropna()
    if len(close) < 200:
        raise ValueError(f"only {len(close)} daily closes available; 200 required")

    latest = float(close.iloc[-1])
    previous = float(close.iloc[-2])
    year = history.loc[close.tail(252).index]
    year_low = float(year["Low"].min())
    year_high = float(year["High"].max())
    range_size = year_high - year_low
    position = 50.0 if range_size == 0 else (latest - year_low) / range_size * 100

    try:
        currency = str(stock.fast_info.get("currency") or "")
    except Exception:
        currency = ""
    if not currency:
        currency = "AUD" if ticker.endswith(".AX") else "USD"

    return StockSnapshot(
        ticker=ticker,
        price=latest,
        currency=currency,
        change_pct=(latest / previous - 1) * 100,
        week_52_low=year_low,
        week_52_high=year_high,
        week_52_position=max(0.0, min(position, 100.0)),
        rsi_14=float(calculate_rsi(close).iloc[-1]),
        sma_50=float(close.tail(50).mean()),
        sma_200=float(close.tail(200).mean()),
        headlines=fetch_headlines(ticker),
    )


def _trend_text(snapshot: StockSnapshot) -> str:
    if snapshot.price > snapshot.sma_50 > snapshot.sma_200:
        return "多头排列"
    if snapshot.price < snapshot.sma_50 < snapshot.sma_200:
        return "空头排列"
    return "均线交错"


def format_stock(snapshot: StockSnapshot) -> str:
    sign = "+" if snapshot.change_pct >= 0 else ""
    news = "\n".join(f"  · {headline}" for headline in snapshot.headlines)
    if not news:
        news = "  · 暂无可用重要标题"
    return (
        f"\n【{snapshot.ticker}】{snapshot.currency} {snapshot.price:.2f} "
        f"({sign}{snapshot.change_pct:.2f}%)\n"
        f"52周：{snapshot.week_52_low:.2f}-{snapshot.week_52_high:.2f}，"
        f"位于区间 {snapshot.week_52_position:.0f}%\n"
        f"RSI(14)：{snapshot.rsi_14:.1f} | SMA50：{snapshot.sma_50:.2f} | "
        f"SMA200：{snapshot.sma_200:.2f} | {_trend_text(snapshot)}\n"
        f"新闻：\n{news}"
    )


def build_report(
    snapshots: list[StockSnapshot],
    errors: dict[str, str],
    now: datetime | None = None,
) -> str:
    report_time = (now or datetime.now(SYDNEY)).astimezone(SYDNEY)
    parts = [
        f"每日持仓监控 | {report_time:%Y-%m-%d %H:%M} 悉尼时间",
        "数据源：Yahoo Finance；价格为最近完整交易日复权收盘价。",
    ]
    parts.extend(format_stock(snapshot) for snapshot in snapshots)
    for ticker, error in errors.items():
        parts.append(f"\n【{ticker}】数据获取失败：{error}")
    parts.append("\n提示：RSI>70偏热，<30偏弱；区间与技术指标仅供研究，不构成投资建议。")
    return "\n".join(parts)


def send_wechat(text: str, sendkey: str) -> None:
    """Push the report to personal WeChat through ServerChan Turbo."""
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    response = requests.post(
        url,
        data={
            "title": "每日持仓监控",
            "desp": text,
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"ServerChan rejected the message: {payload}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the report without sending it to WeChat.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshots: list[StockSnapshot] = []
    errors: dict[str, str] = {}

    for ticker in TICKERS:
        try:
            snapshots.append(fetch_snapshot(ticker))
        except Exception as exc:
            print(f"Warning: data fetch failed for {ticker}: {exc}", file=sys.stderr)
            errors[ticker] = str(exc)

    report = build_report(snapshots, errors)
    print(report)

    if args.dry_run:
        return 0 if snapshots else 1

    sendkey = os.environ.get("SERVERCHAN_SENDKEY", "").strip()
    if not sendkey:
        print("SERVERCHAN_SENDKEY must be set.", file=sys.stderr)
        return 2

    send_wechat(report, sendkey)
    print("Report sent to WeChat through ServerChan.")
    return 0 if snapshots else 1


if __name__ == "__main__":
    raise SystemExit(main())
