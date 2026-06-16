#!/usr/bin/env python3
"""Research Agent prototype: link potential radar picks with Serenity supply-chain theses."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from potential_screener import PotentialPick
from serenity_digest import SerenityDigest

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class SupplyChainTheme:
    theme_id: str
    label: str
    chokepoint: str
    tickers: frozenset[str]
    tw_codes: frozenset[str]
    serenity_keywords: tuple[str, ...]
    counter_thesis: str
    invalidation: tuple[str, ...]
    verification_steps: tuple[str, ...]


@dataclass(frozen=True)
class ResearchBrief:
    ticker: str
    name: str
    potential_score: float
    potential_phase: str
    chain_theme: str
    chokepoint_role: str
    link_type: str
    serenity_tickers: tuple[str, ...]
    evidence: tuple[str, ...]
    counter_thesis: str
    invalidation: tuple[str, ...]
    verification_steps: tuple[str, ...]
    confidence: str


def _config() -> dict[str, Any]:
    path = ROOT / "portfolio_config.json"
    return json.loads(path.read_text(encoding="utf-8")).get("research_agent", {})


def _load_themes() -> list[SupplyChainTheme]:
    raw_themes = _config().get("supply_chain_themes", _DEFAULT_THEMES)
    themes: list[SupplyChainTheme] = []
    for item in raw_themes:
        themes.append(
            SupplyChainTheme(
                theme_id=str(item["id"]),
                label=str(item["label"]),
                chokepoint=str(item["chokepoint"]),
                tickers=frozenset(str(t).upper() for t in item.get("tickers", [])),
                tw_codes=frozenset(str(c) for c in item.get("tw_codes", [])),
                serenity_keywords=tuple(str(k).lower() for k in item.get("serenity_keywords", [])),
                counter_thesis=str(item.get("counter_thesis", "")),
                invalidation=tuple(str(x) for x in item.get("invalidation", ())),
                verification_steps=tuple(str(x) for x in item.get("verification_steps", ())),
            )
        )
    return themes


def _symbol_keys(ticker: str) -> set[str]:
    text = ticker.upper().strip()
    keys = {text, text.split(".")[0]}
    if text.startswith("TW:"):
        keys.add(text.split(":", 1)[1])
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 4:
        keys.add(digits[-4:])
    return keys


def _serenity_ticker_keys(ticker: str) -> set[str]:
    if ticker.startswith("TW:"):
        return {ticker, ticker.split(":", 1)[1]}
    return {ticker.upper(), ticker.upper().split(".")[0]}


def _match_theme(ticker: str, themes: list[SupplyChainTheme]) -> SupplyChainTheme | None:
    keys = _symbol_keys(ticker)
    for theme in themes:
        if keys & theme.tickers:
            return theme
        if keys & theme.tw_codes:
            return theme
    return None


def _serenity_mentions_ticker(ticker: str, serenity: SerenityDigest) -> bool:
    keys = _symbol_keys(ticker)
    for serenity_ticker in serenity.tickers:
        if keys & _serenity_ticker_keys(serenity_ticker):
            return True
    blob = " ".join(post.text for post in serenity.posts).upper()
    for key in keys:
        if len(key) >= 2 and re.search(rf"\$?{re.escape(key)}\b", blob):
            return True
    return False


def _serenity_theme_hits(theme: SupplyChainTheme, serenity: SerenityDigest) -> list[str]:
    hits: list[str] = []
    corpus = " ".join(list(serenity.themes) + [post.text for post in serenity.posts]).lower()
    for keyword in theme.serenity_keywords:
        if keyword in corpus:
            hits.append(keyword)
    for serenity_ticker in serenity.tickers:
        if _serenity_ticker_keys(serenity_ticker) & theme.tickers:
            hits.append(f"${serenity_ticker}")
        code = serenity_ticker.replace("TW:", "")
        if code in theme.tw_codes:
            hits.append(f"TW:{code}")
    return list(dict.fromkeys(hits))


def _related_serenity_tickers(theme: SupplyChainTheme, serenity: SerenityDigest) -> list[str]:
    related: list[str] = []
    for serenity_ticker in serenity.tickers:
        keys = _serenity_ticker_keys(serenity_ticker)
        if keys & theme.tickers or keys & theme.tw_codes:
            related.append(serenity_ticker)
    return related


def _collect_evidence(
    pick: PotentialPick,
    theme: SupplyChainTheme,
    serenity: SerenityDigest | None,
    link_type: str,
) -> tuple[str, ...]:
    evidence: list[str] = []
    evidence.append(
        f"潜力雷达：{pick.phase} {pick.score:.0f}分 — {' · '.join(pick.reasons[:2])}"
    )
    evidence.append(f"产业链主题：{theme.label} — {theme.chokepoint}")

    if serenity and serenity.themes:
        if link_type == "Serenity 直接提及":
            for theme_line in serenity.themes[:2]:
                if any(hit in theme_line.lower() for hit in theme.serenity_keywords) or any(
                    key in theme_line.upper() for key in _symbol_keys(pick.ticker)
                ):
                    evidence.append(f"Serenity（{serenity.target_date}）：{theme_line}")
        else:
            hits = _serenity_theme_hits(theme, serenity)
            if hits:
                evidence.append(
                    f"Serenity 同主题标的/关键词：{', '.join(hits[:4])}（{serenity.target_date}）"
                )
            for theme_line in serenity.themes[:2]:
                if any(keyword in theme_line.lower() for keyword in theme.serenity_keywords):
                    evidence.append(f"Serenity 主题呼应：{theme_line}")
                    break
            if link_type == "Serenity 同主题" and serenity.themes:
                evidence.append(f"Serenity 框架：{serenity.themes[0]}")

    if pick.snapshot.headlines:
        evidence.append(f"近期新闻：{pick.snapshot.headlines[0]}")

    return tuple(evidence[:4])


def _confidence(link_type: str, evidence_count: int) -> str:
    if link_type == "Serenity 直接提及" and evidence_count >= 3:
        return "较高"
    if link_type == "Serenity 同主题" and evidence_count >= 3:
        return "中"
    if link_type == "产业链映射":
        return "中低"
    return "低"


def build_research_briefs(
    potential_picks: list[PotentialPick],
    serenity: SerenityDigest | None = None,
    *,
    max_briefs: int | None = None,
) -> list[ResearchBrief]:
    cfg = _config()
    if not cfg.get("enabled", True):
        return []

    limit = max_briefs if max_briefs is not None else int(cfg.get("max_briefs", 3))
    min_score = float(cfg.get("min_potential_score", 58))
    themes = _load_themes()
    briefs: list[ResearchBrief] = []

    for pick in potential_picks:
        if pick.score < min_score:
            continue
        theme = _match_theme(pick.ticker, themes)
        if theme is None:
            continue

        link_type = "产业链映射"
        serenity_tickers: list[str] = []
        if serenity and serenity.tickers:
            if _serenity_mentions_ticker(pick.ticker, serenity):
                link_type = "Serenity 直接提及"
                serenity_tickers = [
                    t for t in serenity.tickers if _symbol_keys(pick.ticker) & _serenity_ticker_keys(t)
                ] or list(serenity.tickers[:3])
            else:
                serenity_tickers = _related_serenity_tickers(theme, serenity)
                if serenity_tickers or _serenity_theme_hits(theme, serenity):
                    link_type = "Serenity 同主题"

        if serenity is None or not serenity.tickers:
            link_type = "产业链映射"

        evidence = _collect_evidence(pick, theme, serenity, link_type)
        briefs.append(
            ResearchBrief(
                ticker=pick.ticker,
                name=pick.name,
                potential_score=pick.score,
                potential_phase=pick.phase,
                chain_theme=theme.label,
                chokepoint_role=theme.chokepoint,
                link_type=link_type,
                serenity_tickers=tuple(serenity_tickers[:5]),
                evidence=evidence,
                counter_thesis=theme.counter_thesis,
                invalidation=theme.invalidation,
                verification_steps=theme.verification_steps,
                confidence=_confidence(link_type, len(evidence)),
            )
        )

    briefs.sort(
        key=lambda item: (
            0 if item.link_type == "Serenity 直接提及" else 1 if item.link_type == "Serenity 同主题" else 2,
            -item.potential_score,
        )
    )
    return briefs[:limit]


def format_research_agent_section(briefs: list[ResearchBrief]) -> list[str]:
    cfg = _config()
    lines = [
        "## 🔬 研究 Agent（Serenity × 潜力雷达）",
        "",
        "> Serenity 方法：产业链稀缺环节 → 证据 → 反方理由 → 失效条件。",
        "> 以下由潜力雷达候选自动联动生成，供深度验证。",
        "",
    ]

    if not briefs:
        lines.append("_今日潜力候选暂无高置信产业链联动，可查看附录 Serenity 摘要。_")
        lines.append("")
        return lines

    for index, brief in enumerate(briefs, start=1):
        label = brief.name if brief.name else brief.ticker
        if brief.name and brief.name != brief.ticker:
            title = f"{label} ({brief.ticker})"
        else:
            title = brief.ticker
        serenity_ref = ""
        if brief.serenity_tickers:
            serenity_ref = " · Serenity 关联 " + ", ".join(
                f"${t}" if not t.startswith("TW:") else t for t in brief.serenity_tickers[:3]
            )
        lines.append(
            f"### {index}. {title} · {brief.chain_theme} · 置信度 {brief.confidence}{serenity_ref}"
        )
        lines.append("")
        lines.append(f"**稀缺环节**：{brief.chokepoint_role}")
        lines.append("")
        lines.append(f"**联动类型**：{brief.link_type}（潜力 {brief.potential_phase} {brief.potential_score:.0f}分）")
        lines.append("")
        lines.append("**证据来源**")
        lines.append("")
        for item in brief.evidence:
            lines.append(f"- {item}")
        lines.append("")
        lines.append(f"**反方理由**：{brief.counter_thesis}")
        lines.append("")
        lines.append("**失效条件**")
        lines.append("")
        for item in brief.invalidation:
            lines.append(f"- {item}")
        lines.append("")
        if brief.verification_steps:
            lines.append("**下一步验证**")
            lines.append("")
            for step in brief.verification_steps[:3]:
                lines.append(f"- {step}")
            lines.append("")

    note = str(cfg.get("disclaimer", "") or "").strip()
    if note:
        lines.append(f"_{note}_")
        lines.append("")
    return lines


_DEFAULT_THEMES = [
    {
        "id": "cpo_optical",
        "label": "CPO / 光互连",
        "chokepoint": "共封装光学放量阶段的连接器、FAU、激光源与测试环节",
        "tickers": ["LITE", "COHR", "MTSI", "AAOI", "AXTI", "SIVE", "POET", "NVDA", "TSM", "ARM"],
        "tw_codes": ["3363", "6451", "3163", "6830", "8417"],
        "serenity_keywords": ["cpo", "optical", "foci", "transceiver", "coupe", "光互连", "sive", "lite", "cohr"],
        "counter_thesis": "CPO 量产节奏慢于预期，或 pluggable 方案生命周期延长",
        "invalidation": ["TSM COUPE 量产推迟", "NVDA 光学架构变更", "竞争对手低价抢单"],
        "verification_steps": [
            "核对 TSM/NVDA 光学供应链订单与指引",
            "比对 FOCI/信骅等台湾标的与 Serenity 提及标的估值差",
            "跟踪 LITE/COHR/MTSI 财报中 CPO 收入占比",
        ],
    },
    {
        "id": "memory_hbm",
        "label": "存储 / HBM",
        "chokepoint": "AI 训练拉动 HBM/DRAM 供需紧张与周期上行",
        "tickers": ["MU", "WDC", "STX", "SNDK", "SK"],
        "tw_codes": [],
        "serenity_keywords": ["hbm", "memory", "dram", "nand", "micron", "mu ", "存储"],
        "counter_thesis": "存储周期见顶、供给扩张或 AI 资本开支削减",
        "invalidation": ["HBM 价格战", "云厂商削减 Capex", "库存去化慢于预期"],
        "verification_steps": [
            "跟踪 MU/WDC 毛利率与 HBM 产能指引",
            "核对 NVDA 新一代 GPU 存储配置是否提升单台用量",
        ],
    },
    {
        "id": "ai_compute",
        "label": "AI 算力 / 服务器",
        "chokepoint": "算力集群建设中的 GPU、定制 ASIC 与服务器集成",
        "tickers": ["NVDA", "AMD", "ARM", "SMCI", "AVGO", "MRVL", "PLTR", "DELL", "VRT"],
        "tw_codes": ["688981", "002371"],
        "serenity_keywords": ["nvda", "gpu", "asic", "hyperscaler", "capex", "算力", "smci"],
        "counter_thesis": "算力投资回报率不及预期，大客户自研芯片替代",
        "invalidation": ["超大规模云厂商 CapEx 下调", "AMD/自研 ASIC 份额超预期", "估值透支"],
        "verification_steps": [
            "核对 hyperscaler CapEx 与 GPU 出货指引",
            "比较 SMCI/DELL 订单 backlog 与 GPU 供应",
        ],
    },
    {
        "id": "semi_equipment",
        "label": "半导体设备 / 制造",
        "chokepoint": "先进制程与封装扩产中的刻蚀、沉积、检测瓶颈",
        "tickers": ["LRCX", "KLAC", "AMAT", "ON", "MPWR", "CRDO", "ASML"],
        "tw_codes": ["688012", "688981"],
        "serenity_keywords": ["tsm", "foundry", "packaging", "cowos", "equipment", "semicap"],
        "counter_thesis": "晶圆厂资本开支周期下行或地缘政治限制设备出口",
        "invalidation": ["TSM Capex 削减", "出口管制扩大", "先进封装需求低于预期"],
        "verification_steps": [
            "跟踪 AMAT/LRCX/KLAC 中国区与先进制程订单",
            "核对 TSM 资本开支与 CoWoS 扩产进度",
        ],
    },
    {
        "id": "space_connectivity",
        "label": "太空通信 / 卫星",
        "chokepoint": "低轨星座与地面终端的射频、相控阵与发射服务",
        "tickers": ["RKLB", "ASTS", "SPCE"],
        "tw_codes": [],
        "serenity_keywords": ["space", "satellite", "rklb", "asts", "launch"],
        "counter_thesis": "商业航天订单波动大、融资环境收紧或技术落地慢",
        "invalidation": ["发射失败或延期", "星座部署放缓", "估值与现金流不匹配"],
        "verification_steps": [
            "核对 RKLB/ASTS 订单 backlog 与发射排期",
            "跟踪政府/商业星座招标节奏",
        ],
    },
]
