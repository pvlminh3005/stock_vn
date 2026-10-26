"""
Stock RT - Clean Architecture Main Server Entrypoint & Router
Phục vụ HTTP API và giao diện web với kiến trúc phân tầng Clean Architecture:
- Constants: backend/constants/
- Utils: backend/utils/
- Database: backend/db/
- Data Providers: backend/data_providers/
- Domain: backend/domain/
- Controllers: backend/controllers/
"""

import http.server
import json
import os
import re
import socketserver
import sys
import threading
import time
import urllib.parse

# Cấu hình đường dẫn root và backend cho sys.path
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BACKEND_DIR)
for p in [ROOT_DIR, BACKEND_DIR]:
  if p not in sys.path:
    sys.path.insert(0, p)

# ==================== IMPORT FROM CLEAN ARCHITECTURE MODULES ====================
from backend.domain.regime import warm_up_market_data
from backend.controllers import (
    handle_stock_detail,
    handle_chart,
    handle_market_regime,
    handle_market_sentiment,
    handle_search,
    handle_screener,
    handle_top_tplus,
)


def get_configured_port(default_port=8000):
  """Lấy cổng mạng (PORT) từ tham số dòng lệnh hoặc biến môi trường PORT (mặc định: 8000)."""
  if len(sys.argv) > 1 and sys.argv[1].isdigit():
    return int(sys.argv[1])
  if '--port' in sys.argv:
    try:
      idx = sys.argv.index('--port')
      return int(sys.argv[idx + 1])
    except (IndexError, ValueError):
      pass
  env_port = os.environ.get('PORT')
  if env_port and env_port.isdigit():
    return int(env_port)
  return default_port


def render_template_html(file_path):
  """Nạp tự động các component HTML phân tách qua cú pháp <!-- include: components/... -->"""
  try:
    with open(file_path, 'r', encoding='utf-8') as f:
      content = f.read()

    base_dir = os.path.dirname(os.path.abspath(file_path))

    def replace_include(match):
      rel_path = match.group(1).strip()
      target_path = os.path.join(base_dir, rel_path)
      if os.path.exists(target_path):
        with open(target_path, 'r', encoding='utf-8') as inc_f:
          return inc_f.read()
      return f"<!-- Missing component: {rel_path} -->"

    rendered = re.sub(r'<!--\s*include:\s*([^\s]+)\s*-->', replace_include, content)
    cache_ts = int(time.time())
    rendered = re.sub(r'\?v=[\w\.]+', f'?v={cache_ts}', rendered)
    return rendered
  except Exception as e:
    print('Lỗi render template HTML:', e)
    with open(file_path, 'r', encoding='utf-8') as f:
      return f.read()


class ModularStockServer(http.server.SimpleHTTPRequestHandler):
  """HTTP Request Handler định tuyến các API và Static Files của Stock RT."""

  extensions_map = http.server.SimpleHTTPRequestHandler.extensions_map.copy()
  extensions_map.update({
      '.js': 'application/javascript; charset=utf-8',
      '.mjs': 'application/javascript; charset=utf-8',
      '.css': 'text/css; charset=utf-8',
      '.html': 'text/html; charset=utf-8',
  })

  def __init__(self, *args, **kwargs):
    super().__init__(*args, directory=ROOT_DIR, **kwargs)

  def end_headers(self):
    self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
    self.send_header('Pragma', 'no-cache')
    self.send_header('Expires', '0')
    super().end_headers()

  def send_json(self, status, payload):
    try:
      self.send_response(status)
      self.send_header('Content-Type', 'application/json; charset=utf-8')
      self.send_header('Access-Control-Allow-Origin', '*')
      self.end_headers()
      self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    except (BrokenPipeError, ConnectionResetError):
      pass

  def do_GET(self):
    parsed = urllib.parse.urlparse(self.path)
    path = parsed.path
    params = urllib.parse.parse_qs(parsed.query)

    # 1. API: Nến Biểu đồ nhanh
    if path == '/api/chart':
      ticker_list = params.get('ticker', [''])
      ticker = ticker_list[0].strip().upper() if ticker_list else ''
      if not ticker:
        self.send_json(400, {'error': 'Vui lòng cung cấp mã cổ phiếu (ticker)'})
        return
      resolution = params.get('resolution', ['1D'])[0]
      try:
        self.send_json(200, handle_chart(ticker, resolution=resolution))
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    # 2. API: Chi tiết Cổ phiếu
    if path == '/api/stock' or self.path.startswith('/api/stock?'):
      ticker_list = params.get('ticker', [''])
      ticker = ticker_list[0].strip().upper() if ticker_list else ''
      if not ticker:
        self.send_json(400, {'error': 'Vui lòng cung cấp mã cổ phiếu (ticker)'})
        return
      resolution = params.get('resolution', ['1D'])[0]
      try:
        self.send_json(200, handle_stock_detail(ticker, resolution=resolution))
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    # 3. API: Regime thị trường
    if path == '/api/market-regime':
      try:
        self.send_json(200, handle_market_regime())
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    # 4. API: Tâm lý thị trường (Fear & Greed)
    if path == '/api/market-sentiment':
      try:
        self.send_json(200, handle_market_sentiment())
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    # 5. API: Screener & Top T+
    if path == '/api/screener':
      try:
        self.send_json(200, handle_screener())
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    if path == '/api/top-tplus':
      try:
        self.send_json(200, handle_top_tplus())
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    # 6. API: Tìm kiếm mã
    if path == '/api/search':
      q = params.get('q', [''])[0]
      try:
        self.send_json(200, handle_search(q))
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    # 7. Trang chủ HTML & Components
    if path in ['/', '', '/index.html']:
      index_file = os.path.join(ROOT_DIR, 'index.html')
      html_content = render_template_html(index_file)
      encoded = html_content.encode('utf-8')
      self.send_response(200)
      self.send_header('Content-Type', 'text/html; charset=utf-8')
      self.send_header('Content-Length', str(len(encoded)))
      self.end_headers()
      self.wfile.write(encoded)
      return

    # Static assets (JS, CSS, Images, Components)
    super().do_GET()


class ReusableTCPServer(socketserver.TCPServer):
  allow_reuse_address = True
  daemon_threads = True


if __name__ == '__main__':
  PORT = get_configured_port(8000)
  threading.Thread(target=warm_up_market_data, daemon=True).start()
  print(
      f'🚀 Pro Stock Analytics Engine khởi chạy tại: http://localhost:{PORT} (PORT={PORT})'
  )
  try:
    with ReusableTCPServer(('', PORT), ModularStockServer) as httpd:
      httpd.serve_forever()
  except OSError as e:
    if e.errno == 48:
      print(f'\n❌ Cổng {PORT} đang bị tiến trình khác chiếm dụng!')
      print(f'👉 Bạn có thể giải phóng cổng bằng lệnh: lsof -ti :{PORT} | xargs kill -9')
      print(f'👉 Hoặc chỉ định cổng khác: ./start.sh 8080  (hoặc PORT=8080 python3 backend/server.py)\n')
    raise