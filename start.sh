#!/bin/bash
set -e

# Chuyển về thư mục chứa script
cd "$(dirname "$0")"

# Xử lý tham số PORT và APP_ENV:
# Các cách dùng linh hoạt:
#   ./start.sh                -> PORT=8000, APP_ENV=development
#   ./start.sh 8080           -> PORT=8080, APP_ENV=development
#   ./start.sh prod           -> PORT=8000, APP_ENV=production
#   ./start.sh 8080 prod      -> PORT=8080, APP_ENV=production
#   ./start.sh --env prod     -> PORT=8000, APP_ENV=production

TARGET_PORT=""
TARGET_ENV="${APP_ENV:-development}"

for arg in "$@"; do
  if [[ "$arg" =~ ^[0-9]+$ ]]; then
    TARGET_PORT="$arg"
  elif [[ "$arg" =~ ^(dev|development|prod|production|test|testing)$ ]]; then
    TARGET_ENV="$arg"
  fi
done

PORT="${TARGET_PORT:-${PORT:-8000}}"
APP_ENV="${TARGET_ENV}"
export PORT
export APP_ENV

# Giải phóng cổng nếu đang có tiến trình chiếm dụng
PID=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [ -n "$PID" ]; then
  echo "⚠️  Đang giải phóng cổng $PORT (PID: $PID)..."
  echo "$PID" | xargs kill -9 2>/dev/null || true
  sleep 0.5
fi

# Khởi chạy server với môi trường ảo nếu có
echo "🚀 Đang khởi động Pro Stock Analytics Engine (ENV: $APP_ENV, PORT: $PORT)..."
if [ -f "./.venv/bin/python" ]; then
  exec ./.venv/bin/python backend/server.py "$PORT" --env "$APP_ENV"
else
  exec python3 backend/server.py "$PORT" --env "$APP_ENV"
fi
