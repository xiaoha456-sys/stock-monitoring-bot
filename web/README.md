# 持仓简报 App（Web / iOS）

聚焦 **持仓 + 每日简报 + 修改股数**，无 AI 能力。

## 技术栈

- 前端：React + Vite（移动端底部 Tab）
- 后端：FastAPI（`api/` 薄层，业务在 `domain/`）
- 持仓存储：`portfolio_config.json` + `data/holdings_live.json`
- iOS：Capacitor 打包 或 Safari「添加到主屏幕」PWA

## 架构

```
domain/          # 业务逻辑（配置、持仓、挂单、简报）
api/             # FastAPI 薄层（HTTP 路由 + Pydantic schemas）
stock_bot.py     # CLI / 定时推送入口
morning_brief.py # 简报 Markdown 组装
frontend/        # React 移动端
```

| 模块 | 职责 |
|------|------|
| `domain/config.py` | 读取 `portfolio_config.json`，合并 live 持仓 |
| `domain/holdings.py` | `holdings_live.json` 读写 |
| `domain/orders.py` | 限价挂单建议 |
| `domain/portfolio.py` | 持仓扫描 → API 列表 |
| `domain/brief.py` | 今日简报 → API |

根目录 `holdings_store.py` / `holding_orders.py` 为兼容 shim，新代码请直接 `from domain...`。

## 本地启动

```bash
# 1. 安装依赖
source .venv/bin/activate
pip install -r requirements.txt -r api/requirements.txt
cd frontend && npm install && cd ..

# 2. 一键启动
chmod +x scripts/dev.sh
./scripts/dev.sh
```

- 手机浏览器 / 模拟器访问：http://127.0.0.1:5173
- API：http://127.0.0.1:8000/docs

## 功能

| Tab | 功能 |
|-----|------|
| **持仓** | 列表显示现价、盈亏、操作建议、今日挂单 |
| **简报** | 生成每日持仓操作简报（结论 + 挂单 + 资金） |
| **详情** | 修改股数 / 成本，写入 `holdings_live.json` |

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/holdings` | 全部持仓 |
| GET | `/api/holdings/{ticker}` | 单只详情 |
| PUT | `/api/holdings/{ticker}` | `{"shares":60,"cost_basis":103}` |
| GET | `/api/brief/today` | 今日简报 |

## iOS 使用方式

### 方式 A：PWA（最快）

1. iPhone Safari 打开 `http://<你电脑局域网IP>:5173`
2. 分享 → **添加到主屏幕**
3. 后端需在同一 WiFi 可访问：`uvicorn api.main:app --host 0.0.0.0 --port 8000`
4. 创建 `frontend/.env.local`：
   ```bash
   VITE_API_BASE=http://192.168.x.x:8000
   ```
5. 重新 `npm run dev` 或 `npm run build`

### 方式 B：Capacitor 原生壳（可上架 TestFlight）

需 macOS + Xcode。

```bash
cd frontend
npm install
npm run build
npx cap add ios    # 首次
npm run cap:ios    # 打开 Xcode 运行到模拟器/真机
```

真机调试时 `frontend/.env.production`：

```bash
VITE_API_BASE=http://192.168.x.x:8000
```

然后 `npm run cap:sync`。

> 生产环境建议把 FastAPI 部署到云服务器，App 指向 `https://api.yourdomain.com`。

## 修改持仓

App 内编辑，或命令行：

```bash
python stock_bot.py --set-holding RKLB --shares 60 --cost 103
```
