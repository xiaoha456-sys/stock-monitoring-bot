#!/usr/bin/env python3
"""Reddit & X financial social buzz: top discussed tickers and sentiment."""

from __future__ import annotations

import html
import os
import re
import sys
from dataclasses import dataclass
from typing import Any

import requests

ROOT = __import__("pathlib").Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "portfolio_config.json"

_TICKER_RE = re.compile(r"\$([A-Z]{1,5})\b")
_DISCUSSED_PRICE_RE = re.compile(
    r"(?:\$|target(?:ing)?|pt|price|@)\s*(\d{1,5}(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_BULLISH = (
    "moon",
    "rocket",
    "buy",
    "calls",
    "long",
    "bullish",
    "breakout",
    "squeeze",
    "upgrade",
    "beat",
    "strong",
    "undervalued",
    "loading",
    "yolo",
    "rip higher",
    "all time high",
    "ath",
    "🚀",
    "📈",
    "green",
)
_BEARISH = (
    "puts",
    "short",
    "dump",
    "crash",
    "bearish",
    "sell",
    "downgrade",
    "weak",
    "overvalued",
    "bubble",
    "rip",
    "dead",
    "tank",
    "collapse",
    "📉",
    "red",
    "drill",
    "bagholder",
)


@dataclass(frozen=True)
class TickerBuzz:
    ticker: str
    name: str
    mentions: int
    sentiment_score: float
    sentiment_label: str
    source: str
    rank: int
    detail: str = ""
    price: float | None = None
    currency: str = ""
    buy_low: float | None = None
    buy_high: float | None = None
    target_price: float | None = None
    stop_loss: float | None = None
    discussed_prices: tuple[float, ...] = ()


@dataclass(frozen=True)
class SocialSentimentReport:
    reddit: tuple[TickerBuzz, ...]
    x_posts: tuple[TickerBuzz, ...]
    overall_label: str
    overall_score: float
    bullish_pct: float
    bearish_pct: float
    neutral_pct: float
    notes: tuple[str, ...]


def _load_config() -> dict[str, Any]:
    import json

    with CONFIG_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def social_config() -> dict[str, Any]:
    return _load_config().get("social_sentiment", {})


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def score_text_sentiment(text: str) -> tuple[float, str]:
    """Return sentiment score (-100..100) and label from post/tweet text."""
    lowered = text.casefold()
    bull = sum(1 for word in _BULLISH if word in lowered)
    bear = sum(1 for word in _BEARISH if word in lowered)
    if bull == bear == 0:
        return 0.0, "中性"
    score = _clamp((bull - bear) * 18.0, -100.0, 100.0)
    if score >= 18:
        return score, "看涨"
    if score <= -18:
        return score, "看跌"
    return score, "中性"


def _label_from_score(score: float) -> str:
    if score >= 15:
        return "看涨"
    if score <= -15:
        return "看跌"
    return "中性"


def _apewisdom_sentiment(item: dict[str, Any]) -> tuple[float, str]:
    mentions = int(item.get("mentions") or 0)
    prev = int(item.get("mentions_24h_ago") or mentions or 1)
    rank = int(item.get("rank") or 999)
    prev_rank = int(item.get("rank_24h_ago") or rank)
    upvotes = int(item.get("upvotes") or 0)

    score = 0.0
    if prev > 0:
        growth = (mentions - prev) / prev
        score += _clamp(growth * 35.0, -35.0, 35.0)
    if prev_rank > rank:
        score += _clamp((prev_rank - rank) * 2.5, 0.0, 25.0)
    elif prev_rank < rank:
        score -= _clamp((rank - prev_rank) * 2.5, 0.0, 25.0)
    upvote_ratio = upvotes / max(mentions, 1)
    score += _clamp((upvote_ratio - 6.0) * 4.0, -20.0, 20.0)
    return score, _label_from_score(score)


def fetch_reddit_buzz(config: dict[str, Any] | None = None) -> tuple[list[TickerBuzz], dict[str, Any]]:
    cfg = (config or social_config()).get("reddit", {})
    if not cfg.get("enabled", True):
        return [], {"status": "disabled"}

    top_n = int(cfg.get("top_n", 10))
    filter_name = str(cfg.get("apewisdom_filter", "all-stocks"))
    url = f"https://apewisdom.io/api/v1.0/filter/{filter_name}/page/1"
    headers = {"User-Agent": "stock-monitoring-bot/1.0"}

    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        print(f"Warning: Reddit/ApeWisdom fetch failed: {exc}", file=sys.stderr)
        return [], {"status": "error", "reason": str(exc)}

    results: list[TickerBuzz] = []
    for item in payload.get("results", [])[:top_n]:
        score, label = _apewisdom_sentiment(item)
        prev = int(item.get("mentions_24h_ago") or 0)
        mentions = int(item.get("mentions") or 0)
        delta = mentions - prev
        sign = "+" if delta >= 0 else ""
        results.append(
            TickerBuzz(
                ticker=str(item.get("ticker", "")),
                name=html.unescape(str(item.get("name", "") or item.get("ticker", ""))),
                mentions=mentions,
                sentiment_score=round(score, 1),
                sentiment_label=label,
                source="Reddit",
                rank=int(item.get("rank") or len(results) + 1),
                detail=f"24h提及 {sign}{delta} · {int(item.get('upvotes') or 0)} upvotes",
            )
        )
    return results, {
        "status": "ok",
        "filter": filter_name,
        "source": "ApeWisdom (WSB / r/stocks / r/investing 等)",
        "count": len(results),
    }


def _extract_discussed_prices(text: str) -> tuple[float, ...]:
    """Pull dollar amounts that look like price targets from post/tweet text."""
    prices: list[float] = []
    for match in _DISCUSSED_PRICE_RE.finditer(text):
        try:
            value = float(match.group(1))
        except ValueError:
            continue
        if 0.5 <= value <= 50_000:
            prices.append(value)
    return tuple(dict.fromkeys(round(price, 2) for price in prices))


def _format_money(value: float, currency: str) -> str:
    symbol = {"USD": "$", "AUD": "A$", "CNY": "¥"}.get(currency, "")
    if symbol:
        return f"{symbol}{value:.2f}"
    return f"{value:.2f} {currency}"


def _format_price_line(item: TickerBuzz) -> str:
    parts: list[str] = []
    if item.price is not None and item.currency:
        parts.append(f"现价 {_format_money(item.price, item.currency)}")
    if item.buy_low is not None and item.buy_high is not None and item.currency:
        parts.append(
            f"技术买入 {_format_money(item.buy_low, item.currency)}"
            f"~{_format_money(item.buy_high, item.currency)}"
        )
    if item.target_price is not None and item.currency:
        parts.append(f"目标 {_format_money(item.target_price, item.currency)}")
    if item.stop_loss is not None and item.currency:
        parts.append(f"止损 {_format_money(item.stop_loss, item.currency)}")
    if item.discussed_prices:
        low = min(item.discussed_prices)
        high = max(item.discussed_prices)
        if low == high:
            parts.append(f"讨论提及 {_format_money(low, item.currency or 'USD')}")
        else:
            parts.append(
                f"讨论提及 {_format_money(low, item.currency or 'USD')}"
                f"~{_format_money(high, item.currency or 'USD')}"
            )
    return " · ".join(parts)


def enrich_buzz_with_prices(
    items: list[TickerBuzz],
    *,
    include_discussed: bool = True,
) -> list[TickerBuzz]:
    """Attach Yahoo quote + technical buy/target/stop levels to social buzz tickers."""
    if not items:
        return items

    from dataclasses import replace

    from stock_bot import build_recommendation, fetch_snapshot

    enriched: list[TickerBuzz] = []
    for item in items:
        yahoo_ticker = item.ticker
        try:
            rec = build_recommendation(fetch_snapshot(yahoo_ticker))
            snap = rec.snapshot
            enriched.append(
                replace(
                    item,
                    price=round(snap.price, 2),
                    currency=snap.currency,
                    buy_low=rec.buy_low,
                    buy_high=rec.buy_high,
                    target_price=rec.target_price,
                    stop_loss=rec.stop_loss,
                    discussed_prices=item.discussed_prices if include_discussed else (),
                )
            )
        except Exception as exc:
            print(f"Warning: price enrich failed for {item.ticker}: {exc}", file=sys.stderr)
            enriched.append(item)
    return enriched


def fetch_x_buzz(config: dict[str, Any] | None = None) -> tuple[list[TickerBuzz], dict[str, Any]]:
    cfg = (config or social_config()).get("x", {})
    if not cfg.get("enabled", True):
        return [], {"status": "disabled"}

    token_env = str(cfg.get("bearer_token_env", "TWITTER_BEARER_TOKEN"))
    token = os.environ.get(token_env, "").strip()
    if not token:
        return [], {
            "status": "skipped",
            "reason": f"{token_env} 未配置，跳过 X 大V抓取（可在 .env 填入 Twitter API Bearer Token）",
        }

    influencers = [str(item).lstrip("@") for item in cfg.get("influencers", [])]
    if not influencers:
        return [], {"status": "skipped", "reason": "未配置 X influencers 列表"}

    top_n = int(cfg.get("top_n", 10))
    max_results = int(cfg.get("max_results", 100))
    user_query = " OR ".join(f"from:{user}" for user in influencers[:12])
    query = f"({user_query}) ($ OR stock OR shares OR earnings) lang:en -is:retweet"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "query": query,
        "max_results": min(max_results, 100),
        "tweet.fields": "created_at,public_metrics,author_id",
    }

    try:
        response = requests.get(
            "https://api.twitter.com/2/tweets/search/recent",
            headers=headers,
            params=params,
            timeout=25,
        )
        if response.status_code == 401:
            return [], {"status": "error", "reason": "Twitter API 认证失败，请检查 Bearer Token"}
        response.raise_for_status()
        tweets = response.json().get("data", [])
    except Exception as exc:
        print(f"Warning: X/Twitter fetch failed: {exc}", file=sys.stderr)
        return [], {"status": "error", "reason": str(exc)}

    ticker_stats: dict[str, dict[str, Any]] = {}
    for tweet in tweets:
        text = str(tweet.get("text", ""))
        score, label = score_text_sentiment(text)
        discussed = _extract_discussed_prices(text)
        for ticker in _extract_tickers(text):
            bucket = ticker_stats.setdefault(
                ticker,
                {
                    "mentions": 0,
                    "score_sum": 0.0,
                    "labels": [],
                    "sample": text[:120],
                    "discussed_prices": [],
                },
            )
            bucket["mentions"] += 1
            bucket["score_sum"] += score
            bucket["labels"].append(label)
            bucket["discussed_prices"].extend(discussed)

    ranked = sorted(ticker_stats.items(), key=lambda item: item[1]["mentions"], reverse=True)[:top_n]
    results: list[TickerBuzz] = []
    for index, (ticker, bucket) in enumerate(ranked, start=1):
        avg_score = bucket["score_sum"] / max(bucket["mentions"], 1)
        results.append(
            TickerBuzz(
                ticker=ticker,
                name=ticker,
                mentions=int(bucket["mentions"]),
                sentiment_score=round(avg_score, 1),
                sentiment_label=_label_from_score(avg_score),
                source="X",
                rank=index,
                detail=bucket["sample"],
                discussed_prices=tuple(
                    dict.fromkeys(round(price, 2) for price in bucket.get("discussed_prices", []))
                ),
            )
        )
    return results, {
        "status": "ok",
        "source": f"Twitter API · {len(influencers)} 位大V",
        "tweet_count": len(tweets),
        "count": len(results),
    }


def _extract_tickers(text: str) -> list[str]:
    return list(dict.fromkeys(match.group(1) for match in _TICKER_RE.finditer(text.upper())))


def build_social_report(config: dict[str, Any] | None = None) -> SocialSentimentReport:
    cfg = config or social_config()
    reddit, reddit_meta = fetch_reddit_buzz(cfg)
    x_items, x_meta = fetch_x_buzz(cfg)

    price_cfg = cfg.get("price_levels", {})
    if price_cfg.get("enabled", True):
        reddit = enrich_buzz_with_prices(reddit)
        x_items = enrich_buzz_with_prices(x_items)

    notes: list[str] = []
    if reddit_meta.get("status") == "ok":
        notes.append(f"Reddit：{reddit_meta.get('source', '')}")
    elif reddit_meta.get("reason"):
        notes.append(f"Reddit：{reddit_meta['reason']}")
    if x_meta.get("status") == "ok":
        notes.append(f"X：{x_meta.get('source', '')} · 抓取 {x_meta.get('tweet_count', 0)} 条推文")
    elif x_meta.get("reason"):
        notes.append(f"X：{x_meta['reason']}")

    all_items = [*reddit, *x_items]
    if not all_items:
        return SocialSentimentReport(
            reddit=tuple(reddit),
            x_posts=tuple(x_items),
            overall_label="数据不足",
            overall_score=0.0,
            bullish_pct=0.0,
            bearish_pct=0.0,
            neutral_pct=0.0,
            notes=tuple(notes),
        )

    weighted_scores: list[float] = []
    weights: list[float] = []
    label_counts = {"看涨": 0, "看跌": 0, "中性": 0}
    for item in all_items:
        weight = max(item.mentions, 1)
        weighted_scores.append(item.sentiment_score * weight)
        weights.append(weight)
        label_counts[item.sentiment_label] = label_counts.get(item.sentiment_label, 0) + 1

    overall_score = sum(weighted_scores) / sum(weights)
    total = len(all_items)
    bullish_pct = round(label_counts.get("看涨", 0) / total * 100, 1)
    bearish_pct = round(label_counts.get("看跌", 0) / total * 100, 1)
    neutral_pct = round(label_counts.get("中性", 0) / total * 100, 1)
    overall_label = _label_from_score(overall_score)
    if overall_score >= 10 and bullish_pct >= 50:
        overall_label = "整体偏看涨"
    elif overall_score <= -10 and bearish_pct >= 40:
        overall_label = "整体偏看跌"
    elif neutral_pct >= 50:
        overall_label = "整体中性观望"
    else:
        overall_label = f"整体{_label_from_score(overall_score)}"

    return SocialSentimentReport(
        reddit=tuple(reddit),
        x_posts=tuple(x_items),
        overall_label=overall_label,
        overall_score=round(overall_score, 1),
        bullish_pct=bullish_pct,
        bearish_pct=bearish_pct,
        neutral_pct=neutral_pct,
        notes=tuple(notes),
    )


def format_social_section(report: SocialSentimentReport) -> list[str]:
    lines = [
        "## 📣 社交热议 & 大V情绪",
        "",
        f"> **整体情绪**：{report.overall_label}（综合得分 {report.overall_score:+.1f}） · "
        f"看涨 {report.bullish_pct:.0f}% · 看跌 {report.bearish_pct:.0f}% · 中性 {report.neutral_pct:.0f}%",
        "",
        "> 价格区间：「技术买入/目标/止损」由本系统技术面算法生成；「讨论提及」从 X 推文原文解析（Reddit 无帖文全文）。",
        "",
    ]
    for note in report.notes:
        lines.append(f"- {note}")
    lines.append("")

    if report.reddit:
        lines.extend(["**Reddit 热议 Top**（ApeWisdom 聚合 WSB / stocks / investing）", ""])
        for item in report.reddit:
            icon = {"看涨": "🟢", "看跌": "🔴", "中性": "🟡"}.get(item.sentiment_label, "🟡")
            lines.append(
                f"{item.rank}. {icon} **${item.ticker}** {item.name} · "
                f"{item.mentions} 次提及 · **{item.sentiment_label}** ({item.sentiment_score:+.0f}) · {item.detail}"
            )
            price_line = _format_price_line(item)
            if price_line:
                lines.append(f"  　{price_line}")
        lines.append("")

    if report.x_posts:
        lines.extend(["**X 大V 讨论 Top**", ""])
        for item in report.x_posts:
            icon = {"看涨": "🟢", "看跌": "🔴", "中性": "🟡"}.get(item.sentiment_label, "🟡")
            lines.append(
                f"{item.rank}. {icon} **${item.ticker}** · "
                f"{item.mentions} 次提及 · **{item.sentiment_label}** ({item.sentiment_score:+.0f})"
            )
            price_line = _format_price_line(item)
            if price_line:
                lines.append(f"  　{price_line}")
            elif item.detail:
                lines.append(f"  　_{item.detail}_")
        lines.append("")
    elif not report.reddit:
        lines.append("_社交数据暂不可用，请检查网络或配置 Twitter API。_")
        lines.append("")

    return lines
