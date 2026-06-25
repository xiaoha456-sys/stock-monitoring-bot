---
name: accuracy-iteration
description: "准确率自迭代闭环。Use when: 用户要提升推荐命中率、自动调参、复盘后优化策略、轮换 alphasift 策略或查看 tuning 历史。触发词：准确率、自迭代、调参、命中率、iterate、tuning。"
---

# 准确率自迭代 Skill

把「推送 → 复盘 → 调参 → 再推送」做成可自动运行的闭环，目标持续提升命中率。

## 闭环架构

```
每日推送 (stock_bot.py)
    ↓ 存档 data/predictions/
T+1/5/20 复盘 (--review)
    ↓ 存档 data/review_scores.json
准确率迭代 (--iterate)
    ↓ 写入 data/tuning.json + tuning_history.jsonl
下一日推送读取 tuning 参数
```

## 关联 Skills

| Skill | 角色 |
| --- | --- |
| `daily-equity-picks` | 生成每日推荐与买卖价 |
| `prediction-review` | 历史推送打分 |
| `alphasift`（外部） | A 股全市场初选 + `evaluate_saved_runs` 后验 |
| **accuracy-iteration**（本 Skill） | 汇总表现、自动调参 |

## 操作命令

```bash
# 预览迭代建议（不写文件）
python stock_bot.py --iterate --dry-run

# 应用调参并邮件报告
python stock_bot.py --iterate

# 独立模块
python iterate_accuracy.py --dry-run
```

## 自动调整项（data/tuning.json）

| 参数 | 触发条件 | 调整方向 |
| --- | --- | --- |
| `thresholds.buy` | 命中率/均分低于目标 | 提高（更保守） |
| `thresholds.watch` | 同上 | 同步提高 |
| `price_levels.stop_atr` | 止损触发率 > 35% | 放宽止损 |
| `markets.CN.score_blend.screen` | A 股命中率偏低 | 提高 alphasift 权重 |
| `markets.CN.alphasift_strategy` | A 股持续低分 | 轮换策略列表下一项 |

配置入口：`portfolio_config.json` → `iteration`

## 外部 Skill 集成

- **alphasift**：`alphasift_cn.py` 每次选股保存 run 到 `data/alphasift/runs/`；`--iterate` 时调用 `evaluate_saved_runs` 做 T+N 后验。
- **Cursor 人工迭代**：当自动调参不足时，读取 `data/tuning_history.jsonl` 与复盘邮件，手动改 `tuning.json` 或 `portfolio_config.json` 观察池。

## 迭代原则

1. 样本不足（默认 < 5 条）不调整，避免过拟合。
2. 每次最多微调 2 分阈值，策略轮换每次只切一个。
3. 命中率良好时可略放宽买入阈值，避免过度保守。
4. 所有调整写入 `tuning_history.jsonl` 可追溯。

## 关键文件

- `iterate_accuracy.py` — 分析与调参逻辑
- `tuning.py` — 参数加载
- `data/tuning.json` — 当前生效参数（推送时读取）
- `data/tuning_history.jsonl` — 历史调整记录
