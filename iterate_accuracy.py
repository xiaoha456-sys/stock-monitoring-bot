#!/usr/bin/env python3
"""Analyze recommendation accuracy and auto-tune parameters."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from stock_bot import (
    MARKET_ORDER,
    _grade_prediction,
    _fetch_price_range,
    load_config,
)
from domain.predictions_repo import iter_prediction_snapshots
from tuning import (
    DEFAULT_TUNING,
    append_tuning_history,
    load_tuning,
    save_tuning,
)

SYDNEY = ZoneInfo("Australia/Sydney")
ROOT = Path(__file__).resolve().parent


def _iteration_config() -> dict[str, Any]:
    return load_config().get("iteration", {})


def _aggregate_bucket(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {}
    scores = [item["score"] for item in samples]
    count = len(samples)
    return {
        "count": count,
        "avg_score": round(sum(scores) / count, 1),
        "hit_rate": round(sum(1 for item in samples if item["score"] >= 60) / count, 3),
        "direction_rate": round(
            sum(1 for item in samples if "方向判断正确" in item["notes"]) / count,
            3,
        ),
        "target_rate": round(sum(1 for item in samples if item["target_hit"]) / count, 3),
        "stop_rate": round(sum(1 for item in samples if item["stop_hit"]) / count, 3),
    }


def _collect_day_stats(
    payload: dict[str, Any],
    signal_day: datetime,
    end: datetime,
    elapsed: int,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    picks_stats: dict[str, dict[str, Any]] = {}
    holdings_stats: dict[str, dict[str, Any]] = {}
    signal_date = payload.get("date", signal_day.strftime("%Y-%m-%d"))

    for market_key in MARKET_ORDER:
        block = payload.get("markets", {}).get(market_key)
        if block:
            picks = block.get("picks", [])
            if picks:
                bucket = picks_stats.setdefault(
                    market_key,
                    {"samples": [], "strategies": {}, "signal_dates": []},
                )
                bucket["signal_dates"].append(signal_date)
                strategy = (block.get("alphasift") or {}).get("strategy")
                if strategy:
                    bucket["strategies"].setdefault(strategy, [])
                for record in picks:
                    price_range = _fetch_price_range(record["ticker"], signal_day, end)
                    if not price_range:
                        continue
                    last_close, low, high = price_range
                    graded = _grade_prediction(record, last_close, low, high)
                    graded["signal_date"] = signal_date
                    graded["horizon_days"] = elapsed
                    bucket["samples"].append(graded)
                    if strategy:
                        bucket["strategies"][strategy].append(graded)

        holdings_records = (payload.get("holdings") or {}).get(market_key, [])
        if holdings_records:
            bucket = holdings_stats.setdefault(
                market_key,
                {"samples": [], "signal_dates": []},
            )
            bucket["signal_dates"].append(signal_date)
            for record in holdings_records:
                price_range = _fetch_price_range(record["ticker"], signal_day, end)
                if not price_range:
                    continue
                last_close, low, high = price_range
                graded = _grade_prediction(record, last_close, low, high)
                graded["signal_date"] = signal_date
                graded["horizon_days"] = elapsed
                bucket["samples"].append(graded)

    return picks_stats, holdings_stats


def collect_market_stats(
    horizon: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    report_time = (now or datetime.now(SYDNEY)).astimezone(SYDNEY)
    end = report_time
    picks_stats: dict[str, dict[str, Any]] = {}
    holdings_stats: dict[str, dict[str, Any]] = {}

    for signal_date, payload in iter_prediction_snapshots():
        try:
            signal_day = datetime.strptime(signal_date, "%Y-%m-%d").replace(tzinfo=SYDNEY)
        except ValueError:
            continue
        elapsed = (report_time.date() - signal_day.date()).days
        if elapsed < horizon:
            continue

        day_picks, day_holdings = _collect_day_stats(payload, signal_day, end, elapsed)
        for market_key, bucket in day_picks.items():
            target = picks_stats.setdefault(
                market_key,
                {"samples": [], "strategies": {}, "signal_dates": []},
            )
            target["signal_dates"].extend(bucket.get("signal_dates", []))
            target["samples"].extend(bucket.get("samples", []))
            for strategy, rows in bucket.get("strategies", {}).items():
                target["strategies"].setdefault(strategy, []).extend(rows)
        for market_key, bucket in day_holdings.items():
            target = holdings_stats.setdefault(
                market_key,
                {"samples": [], "signal_dates": []},
            )
            target["signal_dates"].extend(bucket.get("signal_dates", []))
            target["samples"].extend(bucket.get("samples", []))

    for market_key, bucket in picks_stats.items():
        aggregated = _aggregate_bucket(bucket["samples"])
        if aggregated:
            bucket.update(aggregated)
            strategy_stats: dict[str, Any] = {}
            for strategy, rows in bucket.get("strategies", {}).items():
                if not rows:
                    continue
                strategy_stats[strategy] = _aggregate_bucket(rows)
            bucket["strategy_stats"] = strategy_stats

    for market_key, bucket in holdings_stats.items():
        aggregated = _aggregate_bucket(bucket["samples"])
        if aggregated:
            bucket.update(aggregated)

    return {"picks": picks_stats, "holdings": holdings_stats}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def propose_adjustments(
    stats: dict[str, dict[str, Any]],
    tuning: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    target_hit_rate = float(config.get("target_hit_rate", 0.6))
    target_avg_score = float(config.get("target_avg_score", 65))
    min_samples = int(config.get("min_samples_per_market", 5))
    min_total = int(config.get("min_total_samples", 10))
    max_step = float(config.get("max_adjustment_per_run", 2))

    total_samples = sum(int(bucket.get("count", 0) or 0) for bucket in stats.values())
    if total_samples < min_total:
        return [
            {
                "market": "ALL",
                "action": "skip",
                "reason": f"全局样本不足（{total_samples}/{min_total}），本次不调整模型参数",
            }
        ]

    thresholds = tuning["thresholds"]
    price_levels = tuning["price_levels"]

    for market_key, bucket in stats.items():
        count = bucket.get("count", 0)
        if count < min_samples:
            changes.append(
                {
                    "market": market_key,
                    "action": "skip",
                    "reason": f"样本不足（{count}/{min_samples}），暂不调整",
                }
            )
            continue

        hit_rate = bucket.get("hit_rate", 0)
        avg_score = bucket.get("avg_score", 0)
        stop_rate = bucket.get("stop_rate", 0)

        if hit_rate < target_hit_rate or avg_score < target_avg_score:
            old_buy = thresholds["buy"]
            new_buy = _clamp(old_buy + max_step, 68, 82)
            if new_buy != old_buy:
                changes.append(
                    {
                        "market": market_key,
                        "action": "set",
                        "path": "thresholds.buy",
                        "old": old_buy,
                        "new": new_buy,
                        "reason": f"命中率 {hit_rate:.0%} / 均分 {avg_score:.1f} 低于目标，收紧买入阈值",
                    }
                )
                thresholds["buy"] = new_buy
                thresholds["watch"] = _clamp(thresholds["watch"] + max_step * 0.5, 52, 75)

        elif hit_rate >= target_hit_rate + 0.1 and avg_score >= target_avg_score + 5:
            old_buy = thresholds["buy"]
            new_buy = _clamp(old_buy - max_step * 0.5, 68, 82)
            if new_buy != old_buy:
                changes.append(
                    {
                        "market": market_key,
                        "action": "set",
                        "path": "thresholds.buy",
                        "old": old_buy,
                        "new": new_buy,
                        "reason": f"命中率 {hit_rate:.0%} 良好，略放宽买入阈值以增加候选",
                    }
                )
                thresholds["buy"] = new_buy

        if stop_rate > 0.35:
            old_stop_atr = price_levels["stop_atr"]
            new_stop_atr = _clamp(old_stop_atr + 0.2, 1.5, 3.0)
            changes.append(
                {
                    "market": market_key,
                    "action": "set",
                    "path": "price_levels.stop_atr",
                    "old": old_stop_atr,
                    "new": new_stop_atr,
                    "reason": f"止损触发率 {stop_rate:.0%} 偏高，放宽止损距离",
                }
            )
            price_levels["stop_atr"] = new_stop_atr

        if market_key == "CN":
            changes.extend(_propose_cn_adjustments(bucket, tuning, config))

    return changes


def _propose_cn_adjustments(
    bucket: dict[str, Any],
    tuning: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    target_hit_rate = float(config.get("target_hit_rate", 0.6))
    rotation = list(config.get("alphasift_strategy_rotation", []))
    cn_tuning = tuning.setdefault("markets", {}).setdefault("CN", {})
    blend = cn_tuning.setdefault("score_blend", {"screen": 0.55, "technical": 0.45})
    current_strategy = cn_tuning.get("alphasift_strategy", "volume_breakout")

    if bucket.get("hit_rate", 0) < target_hit_rate:
        old_screen = float(blend.get("screen", 0.55))
        new_screen = _clamp(old_screen + 0.05, 0.35, 0.7)
        if new_screen != old_screen:
            changes.append(
                {
                    "market": "CN",
                    "action": "set",
                    "path": "markets.CN.score_blend.screen",
                    "old": old_screen,
                    "new": new_screen,
                    "reason": "A股命中率偏低，提高 alphasift 策略分权重",
                }
            )
            blend["screen"] = round(new_screen, 2)
            blend["technical"] = round(1 - new_screen, 2)

        if rotation and current_strategy in rotation:
            index = rotation.index(current_strategy)
            next_strategy = rotation[(index + 1) % len(rotation)]
            if next_strategy != current_strategy and bucket.get("count", 0) >= int(
                config.get("min_samples_per_market", 5)
            ):
                changes.append(
                    {
                        "market": "CN",
                        "action": "set",
                        "path": "markets.CN.alphasift_strategy",
                        "old": current_strategy,
                        "new": next_strategy,
                        "reason": (
                            f"策略 {current_strategy} 命中率 {bucket.get('hit_rate', 0):.0%}，"
                            f"轮换至 {next_strategy}"
                        ),
                    }
                )
                cn_tuning["alphasift_strategy"] = next_strategy

    return changes


def run_alphasift_evaluation(config: dict[str, Any]) -> dict[str, Any]:
    """Optional hook: evaluate saved alphasift runs via external skill."""
    if not config.get("external_skills", {}).get("alphasift_evaluate", True):
        return {"status": "disabled"}

    try:
        from alphasift import evaluate_saved_runs
    except ImportError:
        return {"status": "unavailable", "reason": "alphasift not installed"}

    data_dir = ROOT / "data" / "alphasift"
    if not (data_dir / "runs").exists():
        return {"status": "skipped", "reason": "no saved alphasift runs"}

    try:
        results = evaluate_saved_runs(limit=int(config.get("alphasift_evaluate_limit", 10)))
    except Exception as exc:
        return {"status": "error", "reason": str(exc)}

    run_items: list[Any]
    if isinstance(results, dict):
        run_items = list(results.get("runs", []) or [])
    elif isinstance(results, list):
        run_items = results
    else:
        run_items = []

    summaries = []
    for item in run_items[:5]:
        if isinstance(item, dict):
            summaries.append(
                {
                    "run_id": item.get("run_id", ""),
                    "strategy": item.get("strategy", ""),
                    "win_rate": item.get("win_rate"),
                    "average_return_pct": item.get("average_return_pct"),
                }
            )
            continue
        summaries.append(
            {
                "run_id": getattr(item, "run_id", ""),
                "strategy": getattr(item, "strategy", ""),
                "win_rate": getattr(item, "win_rate", None),
                "average_return_pct": getattr(item, "average_return_pct", None),
            }
        )
    return {"status": "ok", "summaries": summaries}


def format_iteration_report(
    stats: dict[str, Any],
    changes: list[dict[str, Any]],
    alphasift_eval: dict[str, Any],
    applied: bool,
) -> str:
    lines = [
        "# 准确率自迭代报告",
        "",
        "> 基于历史推送复盘结果自动调整阈值与 A 股 alphasift 策略。观察池与持仓分开统计。",
        "",
        "## 观察池推荐准确率（滚动样本）",
        "",
        "| 市场 | 样本数 | 命中率 | 方向正确率 | 均分 | 达标率 | 止损触发率 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    labels = {"US": "美股", "CN": "A股", "AU": "澳股"}
    picks_stats = stats.get("picks", {})
    holdings_stats = stats.get("holdings", {})
    for market_key in MARKET_ORDER:
        bucket = picks_stats.get(market_key)
        if not bucket or not bucket.get("count"):
            continue
        lines.append(
            f"| {labels.get(market_key, market_key)} | {bucket['count']} | "
            f"{bucket['hit_rate'] * 100:.0f}% | {bucket['direction_rate'] * 100:.0f}% | "
            f"{bucket['avg_score']:.1f} | {bucket['target_rate'] * 100:.0f}% | "
            f"{bucket['stop_rate'] * 100:.0f}% |"
        )

    if not any(picks_stats.get(key, {}).get("count") for key in MARKET_ORDER):
        lines.extend(["", "_观察池暂无足够历史样本。_", ""])

    lines.extend(
        [
            "",
            "## 持仓操作准确率（滚动样本）",
            "",
            "| 市场 | 样本数 | 命中率 | 方向正确率 | 均分 | 达标率 | 止损触发率 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for market_key in MARKET_ORDER:
        bucket = holdings_stats.get(market_key)
        if not bucket or not bucket.get("count"):
            continue
        lines.append(
            f"| {labels.get(market_key, market_key)} | {bucket['count']} | "
            f"{bucket['hit_rate'] * 100:.0f}% | {bucket['direction_rate'] * 100:.0f}% | "
            f"{bucket['avg_score']:.1f} | {bucket['target_rate'] * 100:.0f}% | "
            f"{bucket['stop_rate'] * 100:.0f}% |"
        )

    if not any(holdings_stats.get(key, {}).get("count") for key in MARKET_ORDER):
        lines.extend(["", "_持仓暂无足够历史样本（需每日推送后自动存档）。_", ""])

    lines.extend(["", "## 本次调整", ""])
    actionable = [item for item in changes if item.get("action") == "set"]
    skipped = [item for item in changes if item.get("action") == "skip"]
    if skipped:
        lines.append("**未调整（样本不足）**")
        lines.append("")
        for item in skipped:
            market = item.get("market", "")
            lines.append(f"- {market}：{item.get('reason', '')}")
        lines.append("")
    if not actionable:
        if not skipped:
            lines.append("_无参数调整。_")
    else:
        for item in actionable:
            lines.append(
                f"- **{item['path']}**：{item['old']} → {item['new']}（{item['reason']}）"
            )

    if alphasift_eval.get("status") == "ok" and alphasift_eval.get("summaries"):
        lines.extend(["", "## alphasift 后验评估", ""])
        for item in alphasift_eval["summaries"]:
            win_rate = item.get("win_rate")
            win_text = f"{win_rate * 100:.0f}%" if isinstance(win_rate, (int, float)) else "n/a"
            lines.append(
                f"- `{item.get('strategy', '')}` run `{item.get('run_id', '')}`："
                f"胜率 {win_text}"
            )

    lines.extend(
        [
            "",
            f"**状态**：{'已写入 data/tuning.json' if applied else '仅预览，未写入'}",
            "",
            "**关联 Skills**：`prediction-review` · `daily-equity-picks` · `alphasift` · `accuracy-iteration`",
        ]
    )
    return "\n".join(lines)


def iterate_accuracy(
    *,
    apply: bool = True,
    now: datetime | None = None,
) -> tuple[str, dict[str, Any]]:
    config = _iteration_config()
    if not config.get("enabled", True):
        return "准确率迭代已关闭（iteration.enabled=false）。", {"enabled": False}

    horizon = int(config.get("primary_horizon_days", 5))
    stats = collect_market_stats(horizon=horizon, now=now)
    tuning = load_tuning()
    changes = propose_adjustments(stats.get("picks", {}), tuning, config)
    alphasift_eval = run_alphasift_evaluation(config)

    applied = False
    if apply and any(item.get("action") == "set" for item in changes):
        save_tuning(tuning)
        append_tuning_history(
            {
                "horizon": horizon,
                "stats": {
                    "picks": {
                        key: {
                            "count": value.get("count"),
                            "hit_rate": value.get("hit_rate"),
                            "avg_score": value.get("avg_score"),
                        }
                        for key, value in stats.get("picks", {}).items()
                        if value.get("count")
                    },
                    "holdings": {
                        key: {
                            "count": value.get("count"),
                            "hit_rate": value.get("hit_rate"),
                            "avg_score": value.get("avg_score"),
                        }
                        for key, value in stats.get("holdings", {}).items()
                        if value.get("count")
                    },
                },
                "changes": changes,
                "alphasift_eval": alphasift_eval,
            }
        )
        applied = True

    report = format_iteration_report(stats, changes, alphasift_eval, applied)
    payload = {
        "stats": stats,
        "changes": changes,
        "alphasift_eval": alphasift_eval,
        "applied": applied,
        "tuning": load_tuning() if applied else tuning,
    }
    return report, payload


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing tuning.json")
    args = parser.parse_args()
    report, _ = iterate_accuracy(apply=not args.dry_run)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
