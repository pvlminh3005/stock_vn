#!/bin/bash
set -e

# Chuyển về thư mục chứa script
cd "$(dirname "$0")"

# Cấu hình biến PORT: Ưu tiên tham số $1 -> biến môi trường $PORT -> mặc định 8000
PORT="${1:-${PORT:-8000}}"
export PORT

# Giải phóng cổng nếu đang có tiến trình chiếm dụng
PID=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [ -n "$PID" ]; then
  echo "⚠️  Đang giải phóng cổng $PORT (PID: $PID)..."
  echo "$PID" | xargs kill -9 2>/dev/null || true
  sleep 0.5
fi

# Khởi chạy server với môi trường ảo nếu có
echo "🚀 Đang khởi động Pro Stock Analytics Engine tại http://localhost:$PORT (PORT=$PORT) ..."
if [ -f "./.venv/bin/python" ]; then
  exec ./.venv/bin/python backend/server.py "$PORT"
else
  exec python3 backend/server.py "$PORT"
fi
