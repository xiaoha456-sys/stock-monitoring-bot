#!/usr/bin/env python3
"""Summarize @aleabitoreddit (Serenity) posts for the daily report."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests

SYDNEY = ZoneInfo("Australia/Sydney")
DEFAULT_HANDLE = "aleabitoreddit"


@dataclass(frozen=True)
class SerenityPost:
    text: str
    created_at: str
    url: str = ""


@dataclass(frozen=True)
class SerenityDigest:
    handle: str
    target_date: str
    posts: tuple[SerenityPost, ...]
    themes: tuple[str, ...]
    tickers: tuple[str, ...]
    sentiment_label: str
    source: str
    notes: tuple[str, ...]


def _config() -> dict[str, Any]:
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parent / "portfolio_config.json"
    return json.loads(path.read_text(encoding="utf-8")).get("social_sentiment", {}).get("serenity", {})


def _extract_tickers(text: str) -> list[str]:
    cashtags = re.findall(r"\$([A-Z]{1,5})\b", text.upper())
    codes = re.findall(r"\b(\d{4})\b", text)
    tickers = list(dict.fromkeys(cashtags + [f"TW:{code}" for code in codes]))
    return tickers


def _sentiment_from_posts(posts: list[SerenityPost]) -> str:
    from social_sentiment import score_text_sentiment

    if not posts:
        return "数据不足"
    scores: list[float] = []
    for post in posts:
        score, _ = score_text_sentiment(post.text)
        scores.append(score)
    avg = sum(scores) / len(scores)
    if avg >= 12:
        return "偏看涨"
    if avg <= -12:
        return "偏看跌"
    return "中性偏多"


def _fetch_twitter_posts(handle: str, start: datetime, end: datetime) -> list[SerenityPost]:
    token = os.environ.get("TWITTER_BEARER_TOKEN", "").strip()
    if not token:
        return []

    query = f"from:{handle} -is:retweet"
    params = {
        "query": query,
        "max_results": 100,
        "start_time": start.astimezone(SYDNEY).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time": end.astimezone(SYDNEY).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tweet.fields": "created_at,public_metrics",
    }
    response = requests.get(
        "https://api.twitter.com/2/tweets/search/recent",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=25,
    )
    if response.status_code != 200:
        print(f"Warning: Serenity Twitter fetch failed: {response.status_code}", file=sys.stderr)
        return []

    posts: list[SerenityPost] = []
    for tweet in response.json().get("data", []):
        tweet_id = tweet.get("id", "")
        posts.append(
            SerenityPost(
                text=str(tweet.get("text", "")),
                created_at=str(tweet.get("created_at", "")),
                url=f"https://x.com/{handle}/status/{tweet_id}" if tweet_id else "",
            )
        )
    return posts


def _curated_june_11_snapshot() -> SerenityDigest:
    posts = (
        SerenityPost(
            text=(
                "I expect FOCI (3363) to be a bottleneck for both $NVDA and $TSM optical programs. "
                "Rotated trimmed $LITE/$COHR profits into CPO names like $SIVE / Foci. "
                "Sell-side implying selling at ~$2.5B — institutions want the float."
            ),
            created_at="2026-06-11",
        ),
        SerenityPost(
            text=(
                "There we go. My CPO longs in Taiwan are finally starting to take off today. "
                "Shunsin +10% Foci +10% Xintec +10%. Just waiting on Win Semi, Msscorp, and Nextronics to catch up."
            ),
            created_at="2026-06-11",
        ),
        SerenityPost(
            text=(
                "HOW DOES $POET have a higher valuation than FOCI (3363)? FOCI is literally the bottleneck "
                "for CPO volume ramp and main supplier for $TSM and $NVDA. High conviction Foci outperforms "
                "once institutions find this name."
            ),
            created_at="2026-06-11",
        ),
        SerenityPost(
            text=(
                "Random CPO related names I like: $SIVE, Foci (3363), $TSEM, Browave (3163), $AXTI, "
                "Msscorps (6830), Shunsin (6451), $MTSI, Nextronics (8417), $LITE, $COHR, $SOI. "
                "Disclosure: I own most, not all."
            ),
            created_at="2026-06-11",
        ),
    )
    themes = (
        "核心新标的：FOCI (3363) 是 NVDA/TSM 光互连 CPO 放量瓶颈，估值仅约 $25亿，显著低于 POET",
        "仓位动作：5月已将 Lumentum/Coherent 获利了结，轮动至 $SIVE、FOCI 等 CPO 名字",
        "台湾光模块链启动：信骅 +10%、FOCI +10%、鑫创 +10%，等待 Win Semi、MSS、Nextronics 补涨",
        "整体框架不变：仍处光学 transceiver 第二阶段，第三阶段 SiPh/ELS/CPO 正在加仓",
        "机构行为解读：卖方暗示 FOCI 在 $25亿 估值出货 = 机构在抢筹码而非看空",
    )
    tickers = ("FOCI", "SIVE", "NVDA", "TSM", "POET", "LITE", "COHR", "AXTI", "MTSI", "SOI")
    return SerenityDigest(
        handle=DEFAULT_HANDLE,
        target_date="2026-06-11",
        posts=posts,
        themes=themes,
        tickers=tickers,
        sentiment_label="偏看涨",
        source="公开追踪站 semiconstocks.com / followserenity.com（X API 未配置）",
        notes=(
            "来源为第三方公开整理的 @aleabitoreddit 帖文，非官方 API 全量抓取。",
            "配置 TWITTER_BEARER_TOKEN 后可自动拉取原帖。",
        ),
    )


def _fallback_snapshot(target_date: str) -> SerenityDigest:
    """Curated public snapshot when X API is unavailable."""
    if target_date == "2026-06-11":
        return _curated_june_11_snapshot()

    # Reuse latest curated snapshot for nearby dates so research linkage still works.
    try:
        target = datetime.strptime(target_date, "%Y-%m-%d").date()
        anchor = datetime.strptime("2026-06-11", "%Y-%m-%d").date()
        if 0 < (target - anchor).days <= 7:
            digest = _curated_june_11_snapshot()
            return SerenityDigest(
                handle=digest.handle,
                target_date=target_date,
                posts=digest.posts,
                themes=digest.themes,
                tickers=digest.tickers,
                sentiment_label=digest.sentiment_label,
                source=digest.source,
                notes=digest.notes + (f"沿用 2026-06-11 公开摘要（{target_date} 暂无独立缓存）。",),
            )
    except ValueError:
        pass

    return SerenityDigest(
        handle=DEFAULT_HANDLE,
        target_date=target_date,
        posts=(),
        themes=(),
        tickers=(),
        sentiment_label="数据不足",
        source="fallback",
        notes=("该日期暂无缓存摘要，请配置 TWITTER_BEARER_TOKEN 自动抓取。",),
    )


def build_serenity_digest(
    *,
    days_ago: int = 2,
    now: datetime | None = None,
) -> SerenityDigest:
    cfg = _config()
    handle = str(cfg.get("handle", DEFAULT_HANDLE)).lstrip("@")
    report_time = (now or datetime.now(SYDNEY)).astimezone(SYDNEY)
    target_day = (report_time.date() - timedelta(days=days_ago))
    target_date = target_day.strftime("%Y-%m-%d")
    start = datetime.combine(target_day, datetime.min.time(), SYDNEY)
    end = start + timedelta(days=1)

    posts = _fetch_twitter_posts(handle, start, end)
    if posts:
        themes: list[str] = []
        all_tickers: list[str] = []
        for post in posts[:8]:
            tickers = _extract_tickers(post.text)
            all_tickers.extend(tickers)
            snippet = post.text.replace("\n", " ")[:140]
            if tickers:
                themes.append(f"提及 {'/'.join('$' + t for t in tickers[:4])}：{snippet}")
            else:
                themes.append(snippet)
        unique_tickers = tuple(dict.fromkeys(all_tickers))[:12]
        return SerenityDigest(
            handle=handle,
            target_date=target_date,
            posts=tuple(posts),
            themes=tuple(themes[:6]),
            tickers=unique_tickers,
            sentiment_label=_sentiment_from_posts(posts),
            source="Twitter API",
            notes=(),
        )

    return _fallback_snapshot(target_date)


def format_serenity_section(digest: SerenityDigest) -> list[str]:
    lines = [
        "## 🦆 Serenity (@aleabitoreddit) 言论摘要",
        "",
        f"> **{digest.target_date}（前天）整体情绪**：{digest.sentiment_label} · 来源：{digest.source}",
        "",
    ]
    if digest.themes:
        lines.append("**核心观点**")
        lines.append("")
        for theme in digest.themes:
            lines.append(f"- {theme}")
        lines.append("")
    if digest.tickers:
        lines.append(f"**涉及标的**：{', '.join('$' + t if not t.startswith('TW:') else t for t in digest.tickers)}")
        lines.append("")
    if digest.posts:
        lines.append("**原帖摘录**")
        lines.append("")
        for index, post in enumerate(digest.posts[:4], start=1):
            text = post.text.replace("\n", " ").strip()
            if len(text) > 180:
                text = text[:177] + "..."
            if post.url:
                lines.append(f"{index}. [{text}]({post.url})")
            else:
                lines.append(f"{index}. {text}")
        lines.append("")
    for note in digest.notes:
        lines.append(f"- _{note}_")
    lines.append("")
    return lines
