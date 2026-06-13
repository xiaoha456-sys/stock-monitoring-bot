#!/usr/bin/env python3
"""A-share full-market screening via alphasift, mapped to Yahoo tickers."""

from __future__ import annotations

import re
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ALPHASIFT_DATA_DIR = ROOT / "data" / "alphasift"

_ALPHASIFT_IMPORT_ERROR: str | None = None
try:
    from alphasift import screen as alphasift_screen
except ImportError as exc:
    alphasift_screen = None  # type: ignore[assignment]
    _ALPHASIFT_IMPORT_ERROR = str(exc)


STRATEGY_LABELS = {
    "volume_breakout": "放量突破",
    "capital_heat": "资金热度",
    "momentum_quality": "趋势质量",
    "balanced_alpha": "均衡多因子",
    "dual_low": "双低选股",
    "oversold_reversal": "超跌反转",
    "quality_value": "稳健价值",
    "shrink_pullback": "缩量回踩",
}

_FINANCE_KEYWORDS = (
    "银行",
    "证券",
    "保险",
    "人寿",
    "信托",
    "券商",
    "财险",
    "金融",
    "农行",
    "工行",
    "建行",
    "交行",
    "招行",
    "太保",
    "海通",
    "中信",
    "广发",
    "华泰",
    "国泰",
    "兴业银",
    "平安银",
)


def strategy_display_name(strategy: str) -> str:
    return STRATEGY_LABELS.get(strategy, strategy)


def industry_bucket(candidate: AlphasiftCandidate) -> str:
    text = f"{candidate.industry} {candidate.name}"
    if any(keyword in text for keyword in _FINANCE_KEYWORDS):
        return "金融"
    if candidate.industry:
        return candidate.industry.strip()
    return "其他"


def diversify_candidates(
    candidates: list[AlphasiftCandidate],
    config: dict[str, Any],
) -> tuple[list[AlphasiftCandidate], dict[str, Any]]:
    """Limit sector concentration so one industry does not dominate the pool."""
    diversify = config.get("diversify", {})
    if not diversify.get("enabled", False):
        return candidates, {"enabled": False}

    max_output = int(config.get("max_output", 12))
    default_limit = int(diversify.get("max_per_bucket", 1))
    bucket_limits = {
        str(key): int(value)
        for key, value in (diversify.get("buckets") or {}).items()
    }
    bucket_counts: dict[str, int] = {}
    selected: list[AlphasiftCandidate] = []
    skipped: list[dict[str, str]] = []

    for candidate in candidates:
        bucket = industry_bucket(candidate)
        limit = bucket_limits.get(bucket, default_limit)
        if bucket_counts.get(bucket, 0) >= limit:
            skipped.append(
                {
                    "code": candidate.code,
                    "name": candidate.name,
                    "bucket": bucket,
                }
            )
            continue
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        selected.append(candidate)
        if len(selected) >= max_output:
            break

    meta = {
        "enabled": True,
        "selected_count": len(selected),
        "skipped_count": len(skipped),
        "bucket_counts": bucket_counts,
        "skipped_samples": skipped[:5],
    }
    return selected, meta


@dataclass(frozen=True)
class AlphasiftCandidate:
    rank: int
    code: str
    name: str
    final_score: float
    screen_score: float
    ranking_reason: str
    industry: str
    change_pct: float
    yahoo_ticker: str


def is_alphasift_available() -> bool:
    return alphasift_screen is not None


def alphasift_import_error() -> str | None:
    return _ALPHASIFT_IMPORT_ERROR


def normalize_cn_code(code: str) -> str:
    text = str(code).strip().upper()
    if "." in text:
        text = text.split(".", 1)[0]
    digits = re.sub(r"\D", "", text)
    if len(digits) < 6:
        raise ValueError(f"invalid A-share code: {code}")
    return digits[-6:].zfill(6)


def cn_code_to_yahoo(code: str) -> str:
    """Map A-share code to Yahoo Finance ticker suffix."""
    normalized = normalize_cn_code(code)
    if normalized.startswith(("688", "60", "90")):
        return f"{normalized}.SS"
    if normalized.startswith(("00", "30", "20")):
        return f"{normalized}.SZ"
    if normalized.startswith(("8", "4")):
        return f"{normalized}.BJ"
    return f"{normalized}.SZ"


def _pick_to_candidate(pick: Any) -> AlphasiftCandidate:
    code = normalize_cn_code(getattr(pick, "code", ""))
    reason = str(getattr(pick, "ranking_reason", "") or "").strip()
    if not reason:
        reason = str(getattr(pick, "llm_thesis", "") or "").strip()
    return AlphasiftCandidate(
        rank=int(getattr(pick, "rank", 0) or 0),
        code=code,
        name=str(getattr(pick, "name", "") or code),
        final_score=float(getattr(pick, "final_score", 0) or 0),
        screen_score=float(getattr(pick, "screen_score", 0) or 0),
        ranking_reason=reason,
        industry=str(getattr(pick, "industry", "") or ""),
        change_pct=float(getattr(pick, "change_pct", 0) or 0),
        yahoo_ticker=cn_code_to_yahoo(code),
    )


def _run_alphasift_screen_inner(
    strategy: str,
    max_output: int,
    use_llm: bool,
    context: str | None,
) -> Any:
    return alphasift_screen(
        strategy,
        market="cn",
        max_output=max_output,
        use_llm=use_llm,
        llm_context=context,
    )


def run_alphasift_screen(config: dict[str, Any]) -> tuple[list[AlphasiftCandidate], dict[str, Any]]:
    """Run alphasift strategy and return ranked Yahoo-ready candidates."""
    if alphasift_screen is None:
        raise RuntimeError(
            "alphasift is not installed. Run: pip install "
            "'alphasift @ git+https://github.com/ZhuLinsen/alphasift.git'"
        ) from None

    strategy = str(config.get("strategy", "balanced_alpha"))
    max_output = int(config.get("max_output", 12))
    use_llm = bool(config.get("use_llm", False))
    context = str(config.get("context", "") or "").strip() or None
    timeout_seconds = int(config.get("timeout_seconds", 90))

    print(
        f"Running alphasift screen: strategy={strategy}, max_output={max_output}, "
        f"use_llm={use_llm}",
        file=sys.stderr,
    )
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(
            _run_alphasift_screen_inner,
            strategy,
            max_output,
            use_llm,
            context,
        )
        try:
            result = future.result(timeout=timeout_seconds)
        except FuturesTimeoutError as exc:
            raise RuntimeError(
                f"alphasift screen timed out after {timeout_seconds}s"
            ) from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    candidates = [_pick_to_candidate(pick) for pick in result.picks]
    meta = {
        "strategy": result.strategy,
        "run_id": result.run_id,
        "strategy_version": result.strategy_version,
        "snapshot_count": result.snapshot_count,
        "after_filter_count": result.after_filter_count,
        "pick_count": len(candidates),
        "snapshot_source": result.snapshot_source,
        "llm_ranked": result.llm_ranked,
        "degradation": list(result.degradation),
        "source_errors": list(result.source_errors),
    }
    if result.degradation:
        sample = " | ".join(result.degradation[:3])
        print(f"alphasift notes: {sample}", file=sys.stderr)

    if config.get("save_run", True):
        try:
            from alphasift.store import save_screen_result

            ALPHASIFT_DATA_DIR.mkdir(parents=True, exist_ok=True)
            saved = save_screen_result(result, data_dir=ALPHASIFT_DATA_DIR)
            meta["saved_path"] = str(saved)
        except Exception as exc:
            print(f"Warning: failed to save alphasift run: {exc}", file=sys.stderr)

    return candidates, meta


def blend_scores(screen_score: float, technical_score: float, config: dict[str, Any]) -> float:
    blend = config.get("score_blend", {})
    screen_weight = float(blend.get("screen", 0.55))
    technical_weight = float(blend.get("technical", 0.45))
    total = screen_weight + technical_weight
    if total <= 0:
        return technical_score
    blended = (screen_score * screen_weight + technical_score * technical_weight) / total
    return max(0.0, min(blended, 100.0))


def build_screen_reasons(candidate: AlphasiftCandidate) -> tuple[str, ...]:
    reasons: list[str] = []
    if candidate.ranking_reason:
        reasons.append(f"alphasift #{candidate.rank}：{candidate.ranking_reason}")
    else:
        reasons.append(
            f"alphasift #{candidate.rank} 策略评分 {candidate.final_score:.1f}"
        )
    if candidate.industry:
        reasons.append(f"行业：{candidate.industry}")
    return tuple(reasons)
