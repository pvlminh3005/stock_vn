#!/bin/bash
set -e

# Chuyển về thư mục chứa script
cd "$(dirname "$0")"

# Giải phóng cổng 8000 nếu đang có tiến trình chiếm dụng
PID=$(lsof -ti :8000 2>/dev/null || true)
if [ -n "$PID" ]; then
  echo "⚠️ Đang giải phóng cổng 8000 (PID: $PID)..."
  echo "$PID" | xargs kill -9 2>/dev/null || true
  sleep 0.5
fi

# Khởi chạy server với môi trường ảo nếu có
echo "🚀 Đang khởi động Pro Stock Analytics Engine tại http://localhost:8000 ..."
if [ -f "./.venv/bin/python" ]; then
  exec ./.venv/bin/python server.py
else
  exec python3 server.py
fi
