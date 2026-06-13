# Stock Monitoring Bot

分市场（美股 / A股 / 澳股）每日投资简报机器人。从可配置观察池中自动评分、给出买入区间与目标/止损价，通过**邮件**（或可选微信）分市场推送，并支持 T+1 / T+5 / T+20 复盘打分。

## 功能

- **合并邮件推送**：美股、A股、澳股合并为一封邮件（可在配置中关闭）
- **大盘环境**：美股 SPY、上证、ASX 200 判断强势/震荡/弱势，并调节推荐数量与买入门槛
- **每日推荐**：三市场统一 **放量突破量化策略**；A股由 alphasift 全市场筛选，美股/澳股从观察池截面量化打分
- **持仓优先**：合并简报以「持仓今日操作指南」为核心，观察池推荐作为参考附录
- **社交情绪**：Reddit 热议排行（ApeWisdom）+ X 金融大V讨论（可选 Twitter API），附整体看涨/看跌判断
- **买卖价建议**：建议买入区间、目标卖出价、止损参考价（基于 SMA + ATR）
- **复盘打分**：自动对比历史推送与实际走势，写入 `data/review_scores.json`
- **准确率自迭代**：根据复盘自动调整买入阈值、止损带宽、A 股 alphasift 策略权重
- **Cursor Skills**：`.cursor/skills/` 下 skill 覆盖选股、复盘、自迭代全流程

## 1. 配置邮件推送（推荐）

在 `portfolio_config.json` 中默认使用邮件：

```json
"notifications": {
  "channels": ["email"],
  "merge_markets": true,
  "combined_title": "每日全球投资简报"
}
```

默认三市场合并为一封邮件。若需分开发送，设 `"merge_markets": false`。

设置以下环境变量（本地 export，GitHub 用 Secrets）：

| 变量 | 说明 |
| --- | --- |
| `SMTP_HOST` | SMTP 服务器，如 `smtp.gmail.com` |
| `SMTP_PORT` | 端口，默认 `587`（TLS） |
| `SMTP_USER` | 登录用户名（通常与发件邮箱相同） |
| `SMTP_PASSWORD` | 密码或应用专用密码 |
| `EMAIL_FROM` | 发件人地址 |
| `EMAIL_TO` | 收件人，多个用逗号分隔 |

**Gmail 示例**：开启两步验证后，在 Google 账号生成[应用专用密码](https://myaccount.google.com/apppasswords)，`SMTP_HOST=smtp.gmail.com`，`SMTP_PORT=587`。

**QQ 邮箱（已预设）**：

```bash
cp .env.example .env
# 编辑 .env，把 SMTP_PASSWORD 换成 QQ 邮箱授权码
python stock_bot.py --dry-run --market US
python stock_bot.py --channel email
```

| 变量 | 值 |
| --- | --- |
| `SMTP_HOST` | `smtp.qq.com` |
| `SMTP_PORT` | `465`（SSL） |
| `SMTP_USER` | `313265258@qq.com` |
| `EMAIL_FROM` | `313265258@qq.com` |
| `EMAIL_TO` | `313265258@qq.com` |
| `SMTP_PASSWORD` | QQ 邮箱**授权码**（非登录密码） |

授权码获取：登录 [QQ 邮箱](https://mail.qq.com) → **设置** → **账号** → 开启 **POP3/SMTP** → **生成授权码**。

## 2. 配置微信推送（可选）

若仍想用 Server酱，把 `channels` 改为 `["email", "wechat"]` 或 `["wechat"]`，并配置：

| Secret / 环境变量 | 内容 |
| --- | --- |
| `SERVERCHAN_SENDKEY` | [Server酱 Turbo](https://sct.ftqq.com/) 的 SendKey |

## 3. 配置 GitHub Secrets

`Settings` → `Secrets and variables` → `Actions` → 添加邮件相关 Secrets（见上表）。若启用微信，再加 `SERVERCHAN_SENDKEY`。

## 4. 配置观察池

编辑 `portfolio_config.json`：

- `markets.US/CN/AU.watchlist` — 各市场候选股票
- `markets.*.top_n` — 每日首选数量
- `review_horizons_days` — 复盘周期（默认 1 / 5 / 20 天）

A股默认启用 **alphasift** 全市场选股（`volume_breakout` 放量突破策略），静态 `watchlist` 仅在 alphasift 失败时兜底。金融股行业分散：同一行业最多 1 只。
澳股代码示例：`CBA.AX`、`BHP.AX`

### 大盘指数（`market_indices`）

| 市场 | 默认指数 | 作用 |
| --- | --- | --- |
| 美股 | SPY | 判断标普环境，弱势时减少推荐、提高买入门槛 |
| A股 | 000001.SS 上证指数 | 写入 alphasift 上下文，并过滤个股推荐 |
| 澳股 | ^AXJO | 同上 |

### A股 alphasift 配置

`portfolio_config.json` → `markets.CN.alphasift`：

| 字段 | 说明 |
| --- | --- |
| `enabled` | 是否启用全市场选股 |
| `strategy` | 策略名，如 `volume_breakout`、`capital_heat`、`momentum_quality` |
| `max_output` | alphasift 初选数量（默认 12） |
| `diversify` | 行业分散，`金融` 桶最多 1 只，避免银行扎堆 |
| `use_llm` | 是否启用 LLM 排序（需配置 API key，默认 `false`） |
| `fallback_to_watchlist` | alphasift 失败时是否回退静态观察池 |
| `score_blend` | alphasift 分与技术面分的权重（默认 55% / 45%） |

## 5. 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# 预览三份简报（不发送）
python stock_bot.py --dry-run

# 只预览美股
python stock_bot.py --dry-run --market US

# 发送邮件
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USER="you@gmail.com"
export SMTP_PASSWORD="your-app-password"
export EMAIL_FROM="you@gmail.com"
export EMAIL_TO="you@gmail.com"
python stock_bot.py

# 只发邮件、不发微信
python stock_bot.py --channel email

# 复盘打分
python stock_bot.py --review --dry-run
python stock_bot.py --review

# 准确率自迭代（调参写入 data/tuning.json）
python stock_bot.py --iterate --dry-run
python stock_bot.py --iterate

# 持仓分析（持仓列表在 portfolio_config.json 的 holdings 中维护）
python stock_bot.py --holdings --dry-run
python stock_bot.py --holdings

# 社交热议 & 大V情绪（Reddit + X）
python stock_bot.py --social --dry-run
python stock_bot.py --social
```

### 社交情绪配置

`portfolio_config.json` → `social_sentiment`：

| 字段 | 说明 |
| --- | --- |
| `reddit.apewisdom_filter` | `all-stocks` 聚合 WSB / r/stocks / r/investing 等 |
| `reddit.top_n` | Reddit 热议 Top N |
| `x.influencers` | 跟踪的 X 金融大V账号列表 |
| `x.bearer_token_env` | 环境变量名，默认 `TWITTER_BEARER_TOKEN` |

Reddit 无需 API Key（通过 ApeWisdom）。X 需在 `.env` 配置 [Twitter API Bearer Token](https://developer.twitter.com/) 后才会抓取大V推文；未配置时仍推送 Reddit 部分。

测试：

```bash
python -m unittest discover -s tests
```

## 6. 定时任务

`.github/workflows/daily-stock-report.yml` 每天悉尼时间 10:00：

1. 运行测试
2. 复盘历史推荐（T+1 / T+5 / T+20）
3. 分市场生成并邮件推送今日简报
4. 将推荐存档到 `data/predictions/`

## 推送示例结构

```markdown
# 🇺🇸 美股每日投资简报

## 今日首选操作

### 1. NVDA · 买入 ★★★★☆ (78分)

| 项目 | 数值 |
| --- | --- |
| 现价 | $150.00 (+1.25%) |
| 建议买入 | $145.00 ~ $148.00 |
| 目标卖出 | $165.00 |
| 止损参考 | $138.00 |
```

## 准确率自迭代

每日工作流：**复盘 → 迭代调参 → 推送**。调参结果保存在 `data/tuning.json`，下次推送自动生效。

| 可调参数 | 说明 |
| --- | --- |
| `thresholds.buy/watch` | 买入/关注分数线（默认 72/58） |
| `price_levels.stop_atr` | 止损 ATR 倍数 |
| `markets.CN.score_blend` | alphasift 分 vs 技术面分权重 |
| `markets.CN.alphasift_strategy` | A 股策略轮换（volume_breakout / capital_heat 等） |

样本不足时不会调整，避免过拟合。完整历史见 `data/tuning_history.jsonl`。

## Cursor Skills

| Skill | 用途 |
| --- | --- |
| `daily-equity-picks` | 调整观察池、评分逻辑、推送格式 |
| `prediction-review` | 解读复盘结果、迭代阈值 |
| `accuracy-iteration` | 准确率闭环、自动调参、alphasift 后验 |

A股全市场选股使用 [alphasift](https://github.com/ZhuLinsen/alphasift)，已写入 `requirements.txt` 自动安装。

## 数据说明

- 行情与新闻来自 Yahoo Finance，可能存在延迟或缺失。
- 技术指标与推荐仅供研究，**不构成投资建议**。
- 复盘得分用于迭代策略，不代表未来收益保证。
