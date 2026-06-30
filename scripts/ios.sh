#!/usr/bin/env bash
# 方案 B：构建并打开 Xcode（需已安装 Xcode + CocoaPods）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/frontend"

if [[ ! -f .env.production ]]; then
  IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
  if [[ -z "$IP" ]]; then
    echo "请创建 frontend/.env.production，例如："
    echo "  VITE_API_BASE=http://192.168.x.x:8000"
    exit 1
  fi
  echo "VITE_API_BASE=http://${IP}:8000" > .env.production
  echo "已写入 .env.production → http://${IP}:8000"
fi

npm run build
npx cap sync ios

if command -v pod >/dev/null 2>&1; then
  (cd ios/App && pod install)
else
  echo "提示：未安装 CocoaPods，可在 Xcode 中继续，或运行 brew install cocoapods"
fi

echo ""
echo "请另开终端启动 API："
echo "  cd $ROOT && source .venv/bin/activate && uvicorn api.main:app --host 0.0.0.0 --port 8000"
echo ""
npx cap open ios
