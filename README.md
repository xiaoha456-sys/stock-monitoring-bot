# Stock Monitoring Bot

一个使用 Python、yfinance、GitHub Actions 和 Server酱的每日持仓监控机器人，报告推送到个人微信。

监控标的：

`NVDA`、`MU`、`QCOM`、`TSLA`、`CBA.AX`、`WTC.AX`、`TLX.AX`

报告包含：

- 最近完整交易日收盘价及涨跌幅
- 52 周价格区间及当前所处位置
- RSI(14)
- SMA50 与 SMA200
- 每只股票最多两条主要新闻标题

## 1. 配置微信推送

1. 打开 [Server酱 Turbo](https://sct.ftqq.com/)。
2. 使用微信扫码登录并按页面提示绑定微信。
3. 打开 **SendKey** 页面，复制你的 SendKey。
4. 不要把 SendKey 写入代码或提交到 GitHub。

## 2. 配置 GitHub Secrets

将项目推送到 GitHub 仓库，然后进入：

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

添加以下 Repository secret：

| Secret | 内容 |
| --- | --- |
| `SERVERCHAN_SENDKEY` | Server酱提供的 SendKey |

## 3. 启用定时任务

工作流位于 `.github/workflows/daily-stock-report.yml`，每天悉尼时间上午 10:00 运行：

```yaml
schedule:
  - cron: "0 10 * * *"
    timezone: "Australia/Sydney"
```

GitHub Actions 会按悉尼时区处理夏令时。定时工作流只会从默认分支运行，因此请确保工作流文件已经合并到默认分支。

也可以在仓库的 `Actions` 页面选择 **Daily stock report**，点击 **Run workflow** 手动测试。

## 4. 本地运行

需要 Python 3.10 或更高版本。

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python stock_bot.py --dry-run
```

实际推送到微信：

```bash
export SERVERCHAN_SENDKEY="your-serverchan-sendkey"
python stock_bot.py
```

运行测试：

```bash
python -m unittest discover -s tests
```

## 数据说明

- 行情和新闻来自 Yahoo Finance，可能存在延迟、缺失或标题语言不一致。
- 价格使用复权日线收盘价。
- 52 周区间按最近最多 252 个交易日计算。
- 技术指标和报告仅用于研究，不构成投资建议。
