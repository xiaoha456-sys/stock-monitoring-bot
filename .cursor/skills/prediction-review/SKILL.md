---
name: prediction-review
description: "推荐复盘与准确率打分。Use when: 用户要评估历史推送是否命中、查看 T+1/T+5/T+20 表现、迭代评分阈值或 skills。触发词：复盘、打分、准确率、回测推荐、review。"
---

# 推荐复盘 Skill

用历史推送记录自动打分，驱动 skills 与评分逻辑迭代。

## 工作流

1. 确认 `data/predictions/YYYY-MM-DD.json` 存在（由每日 `stock_bot.py` 自动生成）。
2. 运行复盘：
   ```bash
   python stock_bot.py --review --dry-run
   ```
3. 发送复盘邮件：
   ```bash
   export SMTP_HOST="smtp.gmail.com"
   export EMAIL_FROM="you@gmail.com"
   export EMAIL_TO="you@gmail.com"
   export SMTP_USER="you@gmail.com"
   export SMTP_PASSWORD="your-app-password"
   python stock_bot.py --review
   ```
4. 查看累计记录：`data/review_scores.json`（保留最近 60 次）。

## 打分对象（分开统计）

| 类型 | 来源 | 复盘章节 |
| --- | --- | --- |
| **观察池推荐** | `markets.*.picks` | `### 美股 · 观察池推荐` |
| **持仓操作** | `holdings.*` | `### 美股 · 持仓操作` |

每日推送会自动把持仓建议写入 `data/predictions/YYYY-MM-DD.json` 的 `holdings` 字段，与观察池 picks 分开存档。

## 打分规则（单条推荐）

| 事件 | 分值 |
| --- | --- |
| 方向判断正确（买入类且收涨 / 减仓类且收跌） | +40 |
| 期间最低价进入建议买入区间 | +20 |
| 期间最高价达到目标卖出价 | +30 |
| 触及止损参考位 | -25 |

最终得分 clamp 到 0–100。命中率定义为得分 ≥60 的占比。

## 默认复盘周期

`portfolio_config.json` → `review_horizons_days`: `[1, 5, 20]`

对应短线、波段、中线验证。可按用户风格修改。

## 迭代建议

复盘后若某市场持续低分：

1. 收紧 `_action_from_score` 买入阈值（如 72 → 75）。
2. 缩小观察池，去掉低流动性或 Yahoo 数据不稳的代码。
3. A股可改用 `alphasift screen` 预筛后再进 watchlist。
4. 调整 `_price_levels` 中 ATR 倍数，使买入带更贴近实际波动。

## GitHub Actions

工作流在每日推送后自动运行 `--review`，将复盘报告发到邮箱（需配置 SMTP 相关 Secrets）。
