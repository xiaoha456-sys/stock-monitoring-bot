# 持仓简报 App（Web / iOS）

聚焦 **持仓管理 + 每日简报**，数据存 **服务器数据库**（默认 SQLite，可换 PostgreSQL）。

## 技术栈

- 前端：React + Vite + Capacitor（可打包 iOS）
- 后端：FastAPI（`api/`）
- 持仓数据库：`data/portfolio.db`（`DATABASE_URL` 可配置）
- 策略配置：`portfolio_config.json`（市场、资金、选股策略；首次启动自动导入持仓到数据库）

## 架构

```
domain/          # 业务逻辑
  holdings_repo.py   # 数据库 CRUD
  holdings.py        # 统一入口（database / 旧版 JSON）
api/             # HTTP API
frontend/        # 手机 / Web 客户端
```

首次 API 启动时：若数据库为空，自动从 `portfolio_config.json` + `holdings_live.json` 导入。

## 本地启动

```bash
source .venv/bin/activate
pip install -r requirements.txt -r api/requirements.txt
cd frontend && npm install && cd ..
./scripts/dev.sh
```

- Web：http://127.0.0.1:5173
- API 文档：http://127.0.0.1:8000/docs

## App 内管理持仓

| 操作 | 页面 |
|------|------|
| 查看列表 | 底部 **持仓** |
| **添加** | 持仓页右上角 **添加** |
| **修改** | 点击股票 → 修改股数/成本/止损/目标 |
| **删除** | 详情页底部 **删除持仓** |
| 简报 | 底部 **简报** |

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/holdings` | 全部持仓（含行情） |
| POST | `/api/holdings` | 新增 `{"ticker":"RKLB","market":"US",...}` |
| GET | `/api/holdings/{ticker}` | 单只详情 |
| PUT | `/api/holdings/{ticker}` | 修改 |
| DELETE | `/api/holdings/{ticker}` | 删除 |
| GET | `/api/brief/today` | 今日简报 |

## 装到自己的 iPhone

手机 App **不存本地文件**，只连你的 API；API 连数据库。

### 开发阶段（同一 WiFi）

1. 电脑运行：`./scripts/dev.sh`
2. 查电脑局域网 IP（如 `192.168.1.10`）
3. 创建 `frontend/.env.production`：
   ```bash
   VITE_API_BASE=http://192.168.1.10:8000
   ```
4. 打包 iOS：
   ```bash
   cd frontend
   npm run build
   npx cap sync ios
   npx cap open ios
   ```
5. Xcode 运行到真机

### 生产阶段（推荐）

1. 把 API 部署到云服务器（VPS）
2. 设置环境变量：
   ```bash
   DATABASE_URL=postgresql://user:pass@host:5432/portfolio
   ```
3. 启动：`uvicorn api.main:app --host 0.0.0.0 --port 8000`
4. App 构建时：`VITE_API_BASE=https://api.yourdomain.com`

### PWA 快捷方式（免 Xcode）

1. Safari 打开 `http://<IP>:5173`
2. 分享 → **添加到主屏幕**
3. 需配置 `VITE_API_BASE` 指向 API

## 命令行（与 App 共用数据库）

```bash
python stock_bot.py --list-holdings
python stock_bot.py --set-holding RKLB --shares 60 --cost 103
python stock_bot.py --remove-holding OLD_TICKER
```

## 切回 JSON 文件存储（旧模式）

`portfolio_config.json`：

```json
"holdings_source": {
  "enabled": true,
  "storage": "file",
  "live_file": "data/holdings_live.json"
}
```
