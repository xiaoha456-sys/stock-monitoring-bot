---
name: daily-equity-picks
description: "每日分市场选股与买卖价建议。Use when: 用户要生成/优化美股、A股、澳股每日投资简报，调整观察池、评分阈值、买入/目标/止损逻辑，或改进微信推送格式。触发词：每日推荐、买卖价、分市场推送、观察池。"
---

# 每日分市场选股 Skill

将 `stock_bot.py` 从固定持仓监控升级为**分市场每日推荐引擎**，输出可操作的买入区间、目标价、止损参考。

## 工作流

1. 读取 `portfolio_config.json` 中各市场配置；**A股优先看 `markets.CN.alphasift`**（全市场选股），美股/澳股看 `watchlist`。
2. 运行 `python stock_bot.py --dry-run` 预览三份简报（美股 / A股 / 澳股）。
3. 根据用户反馈调整：
   - **观察池**：在 `portfolio_config.json` 增减 ticker（A股用 `.SS`/`.SZ`，澳股用 `.AX`）。
   - **评分逻辑**：修改 `stock_bot.py` 中 `_score_snapshot`、`_action_from_score`、`_price_levels`。
   - **推送数量**：修改各市场 `top_n`。
4. 满意后由 GitHub Actions 或本地 `python stock_bot.py` 分三封邮件（或微信）推送。

## 评分框架（参考 LLMQuant five-lens）

| 维度 | 权重思路 |
| --- | --- |
| 趋势 | 价格 vs SMA50 vs SMA200 |
| 动量 | RSI 区间、单日涨跌幅 |
| 位置 | 52周区间百分位 |
| 风控 | ATR 推导买入带、目标价、止损 |

推荐档位：`买入` ≥72 · `逢低关注` ≥58 · `观望` ≥45 · `减仓` ≥32 · `回避` <32

## 输出格式要求

微信推送使用 Markdown 表格，每条首选包含：

- 现价与涨跌幅
- 建议买入区间（低 ~ 高）
- 目标卖出价
- 止损参考价
- 2-3 条中文逻辑摘要 + 1 条新闻标题

## 数据与局限

- 行情来自 Yahoo Finance；A股覆盖取决于 Yahoo 是否有该代码。
- A股已默认接入 `alphasift`：`alphasift_cn.py` 全市场筛选 → Yahoo 技术面 enrich → 55/45 混合评分。
- 调整策略：`markets.CN.alphasift.strategy`（如 `balanced_alpha`、`dual_low`）。
- 本地调试：`python stock_bot.py --dry-run --market CN`。
- 所有输出须标注「仅供研究，不构成投资建议」。

## 相关文件

- `stock_bot.py` — 主逻辑
- `portfolio_config.json` — 观察池与推送配置
- `data/predictions/` — 每日推荐存档（供复盘）
