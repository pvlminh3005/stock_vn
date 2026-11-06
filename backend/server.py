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

# Tự động nạp file .env nội bộ (nếu có) để đọc config bảo mật
def reload_env_file():
  """Đọc và nạp các biến môi trường từ file .env nội bộ nếu có."""
  env_path = os.path.join(ROOT_DIR, '.env')
  found_keys = set()
  if os.path.isfile(env_path):
    try:
      with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
          line = line.strip()
          if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k:
              os.environ[k] = v
              found_keys.add(k)
    except Exception:
      pass

  # Nếu WHITELIST_HOSTS bị xóa hoặc comment khỏi file .env -> Xóa ngay khỏi os.environ
  if 'WHITELIST_HOSTS' not in found_keys:
    os.environ.pop('WHITELIST_HOSTS', None)

reload_env_file()

def get_whitelist_hosts():
  """Lấy danh sách Host được miễn trừ mã PIN từ biến môi trường WHITELIST_HOSTS (không hardcode)."""
  reload_env_file()
  raw = os.environ.get('WHITELIST_HOSTS', '').strip()
  if not raw:
    return []
  return [h.strip().lower() for h in raw.split(',') if h.strip()]

# ==================== IMPORT FROM CLEAN ARCHITECTURE MODULES ====================
from backend.domain.regime import warm_up_market_data
from backend.utils.portfolio_scheduler import start_portfolio_scheduler
from backend.controllers import (
    handle_stock_detail,
    handle_chart,
    handle_market_regime,
    handle_market_sentiment,
    handle_search,
    handle_screener,
    handle_top_tplus,
    start_screener_worker,
    handle_portfolio_bundle,
    handle_portfolio_alternatives,
    handle_portfolio_sectors,
    handle_telegram_test,
    handle_get_portfolio,
    handle_add_trade,
    handle_delete_trade,
    handle_reset_portfolio,
    handle_save_settings,
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

  def is_whitelisted_host(self):
    """Kiểm tra xem request có thuộc WHITELIST_HOSTS được cấu hình từ ENV không.
    Chỉ lấy từ biến môi trường WHITELIST_HOSTS, tuyệt đối không hardcode bất kỳ host nào.
    Bất kỳ host nào không nằm trong danh sách này đều BẮT BUỘC phải xác thực mã PIN.
    """
    whitelist = get_whitelist_hosts()
    if not whitelist:
      return False

    host = self.headers.get('Host', '').split(':')[0].lower()
    is_cloud_proxy = bool(
        self.headers.get('X-Forwarded-For') or 
        self.headers.get('X-Forwarded-Host') or 
        self.headers.get('X-Render-Origin-Server')
    )
    # Nếu client từ Cloud Proxy (Internet) giả mạo host cục bộ -> Từ chối
    if is_cloud_proxy and host in ['localhost', '127.0.0.1', '0.0.0.0']:
      return False

    return host in whitelist

  def check_pin_authenticated(self, params):
    """Kiểm tra xác thực mã PIN bảo vệ (nếu biến APP_ACCESS_PIN được cấu hình)."""
    # 0. Miễn phí xác thực nếu Host nằm trong WHITELIST_HOSTS cấu hình từ ENV
    if self.is_whitelisted_host():
      return True

    pin_required = os.environ.get('APP_ACCESS_PIN', '').strip()
    if not pin_required:
      return True

    # 1. Kiểm tra tham số URL (?auth=PIN hoặc ?pin=PIN)
    query_pin = params.get('auth', [''])[0].strip() or params.get('pin', [''])[0].strip()
    if query_pin == pin_required:
      return True

    # 2. Kiểm tra Header X-Access-Pin
    header_pin = self.headers.get('X-Access-Pin', '').strip()
    if header_pin == pin_required:
      return True

    # 3. Kiểm tra Cookie stock_rt_auth
    cookie_header = self.headers.get('Cookie', '')
    if cookie_header:
      for item in cookie_header.split(';'):
        if '=' in item:
          k, v = item.strip().split('=', 1)
          if k == 'stock_rt_auth' and v == pin_required:
            return True

    return False

  def do_HEAD(self):
    """Xử lý HEAD request siêu nhẹ cho các hệ thống giám sát / uptime monitor."""
    self.send_response(200)
    self.send_header('Content-Type', 'application/json; charset=utf-8')
    self.send_header('Access-Control-Allow-Origin', '*')
    self.end_headers()

  def do_GET(self):
    parsed = urllib.parse.urlparse(self.path)
    path = parsed.path
    params = urllib.parse.parse_qs(parsed.query)

    # 0. API: Health Check & Keep-Alive siêu nhẹ cho Cron-job / Uptime Monitor (< 40 bytes)
    if path in ['/ping', '/health', '/api/ping', '/api/health']:
      self.send_json(200, {'status': 'ok', 'message': 'pong'})
      return

    # 0B. API: Xác thực mã PIN nội bộ
    if path == '/api/auth/verify':
      if self.is_whitelisted_host():
        self.send_json(200, {'authenticated': True, 'isWhitelisted': True})
        return

      pin_required = os.environ.get('APP_ACCESS_PIN', '').strip()
      if not pin_required:
        self.send_json(200, {'authenticated': True, 'pinRequired': False})
        return

      # 1. Kiểm tra nếu người dùng gửi mã PIN qua form hoặc query
      input_pin = params.get('pin', [''])[0].strip() or params.get('auth', [''])[0].strip()
      if input_pin:
        if input_pin == pin_required:
          self.send_response(200)
          self.send_header('Content-Type', 'application/json; charset=utf-8')
          self.send_header('Access-Control-Allow-Origin', '*')
          cookie_val = f'stock_rt_auth={pin_required}; Path=/; Max-Age=315360000; SameSite=Lax'
          if self.headers.get('X-Forwarded-Proto') == 'https':
            cookie_val += '; Secure'
          self.send_header('Set-Cookie', cookie_val)
          self.end_headers()
          self.wfile.write(json.dumps({'authenticated': True, 'success': True, 'token': pin_required}).encode('utf-8'))
        else:
          self.send_json(401, {'authenticated': False, 'error': 'Mã PIN không chính xác'})
        return

      # 2. Nếu không gửi PIN, kiểm tra xem đã có Cookie hoặc Header xác thực từ trước chưa
      if self.check_pin_authenticated(params):
        self.send_json(200, {'authenticated': True, 'success': True})
        return

      self.send_json(401, {'authenticated': False, 'error': 'Yêu cầu mã PIN bảo vệ'})
      return

    # 0C. API: Đăng xuất & Khóa ứng dụng
    if path == '/api/auth/logout':
      self.send_response(200)
      self.send_header('Content-Type', 'application/json; charset=utf-8')
      self.send_header('Access-Control-Allow-Origin', '*')
      self.send_header('Set-Cookie', 'stock_rt_auth=; Path=/; Max-Age=0; SameSite=Lax')
      self.end_headers()
      self.wfile.write(json.dumps({'success': True, 'authenticated': False}).encode('utf-8'))
      return

    # Chốt chặn bảo vệ: Nếu là yêu cầu API mà chưa xác thực mã PIN thì từ chối truy cập
    if path.startswith('/api/'):
      if not self.check_pin_authenticated(params):
        self.send_json(401, {'error': 'UNAUTHORIZED', 'message': 'Yêu cầu mã PIN bảo vệ để truy cập hệ thống'})
        return

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

    # 7. API: Gói danh mục đầu tư theo vốn & Mã thay thế
    if path == '/api/portfolio-bundle':
      cap = params.get('capital', ['20000000'])[0]
      style = params.get('style', ['balanced'])[0]
      try:
        self.send_json(200, handle_portfolio_bundle(capital=cap, style=style))
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    if path == '/api/portfolio-alternatives':
      sym = params.get('symbol', [''])[0]
      sector = params.get('sector', [''])[0]
      max_budget = params.get('budget', ['10000000'])[0]
      exclude_sector = params.get('exclude_sector', [None])[0]
      target_sector = params.get('target_sector', [None])[0]
      try:
        self.send_json(200, handle_portfolio_alternatives(
            current_symbol=sym,
            sector=sector,
            max_budget=max_budget,
            exclude_sector=exclude_sector,
            target_sector=target_sector,
        ))
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    if path == '/api/portfolio-sectors':
      max_budget = params.get('budget', ['10000000'])[0]
      exclude_sector = params.get('exclude_sector', [None])[0]
      try:
        self.send_json(200, handle_portfolio_sectors(
            max_budget=max_budget,
            exclude_sector=exclude_sector,
        ))
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    # 8. API: Kiểm tra kết nối Telegram Bot & Gửi thử nghiệm
    if path == '/api/telegram/test':
      sym = params.get('ticker', ['SSI'])[0]
      try:
        self.send_json(200, handle_telegram_test(ticker=sym))
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    # 8.1 API: Lịch sử tin nhắn cảnh báo Telegram đã gửi (tracking)
    if path == '/api/telegram/logs':
      limit_str = params.get('limit', ['50'])[0]
      try:
        limit_val = int(limit_str) if limit_str.isdigit() else 50
        from backend.db.portfolio_db import get_telegram_sent_logs
        self.send_json(200, {'status': 'success', 'data': get_telegram_sent_logs(limit=limit_val)})
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    # 9. API: Sổ Lệnh / Danh Mục Cá Nhân
    if path == '/api/portfolio':
      try:
        self.send_json(200, handle_get_portfolio())
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    if path == '/api/portfolio/delete':
      trade_id = params.get('id', [''])[0]
      try:
        self.send_json(200, handle_delete_trade(trade_id))
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    # 10. Trang chủ HTML & Components
    if path in ['/', '', '/index.html']:
      index_file = os.path.join(ROOT_DIR, 'index.html')
      html_content = render_template_html(index_file)

      # Nếu chưa xác thực và host không nằm trong whitelist -> Hiển thị màn hình PIN ngay từ HTML ban đầu
      if not self.check_pin_authenticated(params):
        html_content = html_content.replace(
            'id="authPinOverlay" class="fixed inset-0 z-[9999] bg-slate-950/95 backdrop-blur-md flex items-center justify-center p-4 hidden"',
            'id="authPinOverlay" class="fixed inset-0 z-[9999] bg-slate-950/95 backdrop-blur-md flex items-center justify-center p-4"'
        )

      encoded = html_content.encode('utf-8')
      self.send_response(200)
      self.send_header('Content-Type', 'text/html; charset=utf-8')
      self.send_header('Content-Length', str(len(encoded)))
      
      # Tự động set cookie đăng nhập vĩnh viễn nếu mở từ link Telegram (?auth=PIN)
      pin_required = os.environ.get('APP_ACCESS_PIN', '').strip()
      query_pin = params.get('auth', [''])[0].strip() or params.get('pin', [''])[0].strip()
      if pin_required and query_pin == pin_required:
        self.send_header('Set-Cookie', f'stock_rt_auth={pin_required}; Path=/; Max-Age=315360000; SameSite=Lax')

      self.end_headers()
      self.wfile.write(encoded)
      return

    # Static assets (JS, CSS, Images, Components)
    super().do_GET()

  def do_POST(self):
    parsed = urllib.parse.urlparse(self.path)
    path = parsed.path
    params = urllib.parse.parse_qs(parsed.query)

    # Chốt chặn bảo vệ mã PIN
    if path.startswith('/api/'):
      if not self.check_pin_authenticated(params):
        self.send_json(401, {'error': 'UNAUTHORIZED', 'message': 'Yêu cầu mã PIN bảo vệ để truy cập hệ thống'})
        return

    content_length = int(self.headers.get('Content-Length', 0))
    post_body = {}
    if content_length > 0:
      raw_body = ''
      try:
        raw_body = self.rfile.read(content_length).decode('utf-8')
        post_body = json.loads(raw_body)
      except Exception:
        try:
          post_body = urllib.parse.parse_qs(raw_body)
          post_body = {k: v[0] if len(v) == 1 else v for k, v in post_body.items()}
        except Exception:
          post_body = {}

    if path == '/api/portfolio/trade':
      try:
        res = handle_add_trade(post_body)
        self.send_json(200 if res.get('success') else 400, res)
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    if path == '/api/portfolio/trade/delete':
      trade_id = str(post_body.get('id') or params.get('id', [''])[0])
      try:
        res = handle_delete_trade(trade_id)
        self.send_json(200 if res.get('success') else 400, res)
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    if path == '/api/portfolio/settings':
      try:
        res = handle_save_settings(post_body)
        self.send_json(200 if res.get('success') else 400, res)
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    if path == '/api/portfolio/reset':
      try:
        res = handle_reset_portfolio()
        self.send_json(200 if res.get('success') else 400, res)
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    self.send_json(404, {'error': 'NOT_FOUND', 'message': 'Endpoint không tồn tại'})


class ReusableTCPServer(socketserver.TCPServer):
  allow_reuse_address = True
  daemon_threads = True


if __name__ == '__main__':
  PORT = get_configured_port(8000)
  threading.Thread(target=warm_up_market_data, daemon=True).start()
  threading.Thread(target=start_screener_worker, daemon=True).start()
  start_portfolio_scheduler()
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
      print('👉 Hoặc chỉ định cổng khác: ./start.sh 8080  (hoặc PORT=8080 python3 backend/server.py)\n')
    raise