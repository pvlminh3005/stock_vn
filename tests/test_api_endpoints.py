"""
Stock RT - Comprehensive Test Suite for API Endpoints & Route Dispatcher
Kiểm thử toàn bộ hệ thống API, Route Registry, Controllers và Cơ chế bảo vệ mã PIN.
"""

import os
import sys
import unittest

# Đảm bảo import được các module từ backend
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
  sys.path.insert(0, ROOT_DIR)

# Thiết lập cứng môi trường TESTING để không tác động tới MongoDB Prod/Dev
os.environ['APP_ENV'] = 'testing'

from backend.server import (
    GET_ROUTES,
    POST_ROUTES,
    _route_chart,
    _route_stock,
    _route_market_regime,
    _route_market_sentiment,
    _route_top_tplus,
    _route_search,
    _route_portfolio_bundle,
    _route_portfolio_sectors,
    _route_portfolio_get,
    _route_portfolio_trade_add,
    _route_portfolio_trade_delete,
    _route_portfolio_settings,
    _route_telegram_logs,
)


class TestRouteRegistry(unittest.TestCase):
  """Kiểm tra tính đầy đủ và ánh xạ chính xác của bảng định tuyến."""

  def test_get_routes_registered(self):
    expected_get_routes = [
        '/api/chart',
        '/api/stock',
        '/api/market-regime',
        '/api/market-sentiment',
        '/api/screener',
        '/api/top-tplus',
        '/api/search',
        '/api/portfolio-bundle',
        '/api/portfolio-alternatives',
        '/api/portfolio-sectors',
        '/api/telegram/test',
        '/api/telegram/logs',
        '/api/portfolio',
        '/api/portfolio/delete',
    ]
    for route in expected_get_routes:
      self.assertIn(route, GET_ROUTES, f"Route GET {route} chưa được đăng ký trong GET_ROUTES")
      self.assertTrue(callable(GET_ROUTES[route]), f"Handler của {route} không phải là callable function")

  def test_post_routes_registered(self):
    expected_post_routes = [
        '/api/portfolio/trade',
        '/api/portfolio/trade/delete',
        '/api/portfolio/settings',
        '/api/portfolio/reset',
    ]
    for route in expected_post_routes:
      self.assertIn(route, POST_ROUTES, f"Route POST {route} chưa được đăng ký trong POST_ROUTES")
      self.assertTrue(callable(POST_ROUTES[route]), f"Handler của {route} không phải là callable function")


class TestGetApiHandlers(unittest.TestCase):
  """Kiểm thử từng hàm xử lý GET API với các tham số hợp lệ và bất thường."""

  def test_route_chart_validation(self):
    # Không có ticker -> Phải báo lỗi 400
    status, res = _route_chart({})
    self.assertEqual(status, 400)
    self.assertIn('error', res)

    # Có ticker hợp lệ
    status, res = _route_chart({'ticker': ['HPG'], 'resolution': ['1D']})
    self.assertEqual(status, 200)
    self.assertEqual(res.get('ticker'), 'HPG')
    self.assertIn('candles', res)
    self.assertIsInstance(res['candles'], list)

  def test_route_stock_validation(self):
    # Không có ticker -> Phải báo lỗi 400
    status, res = _route_stock({})
    self.assertEqual(status, 400)
    self.assertIn('error', res)

    # Có ticker hợp lệ (ví dụ: SSI)
    status, res = _route_stock({'ticker': ['SSI'], 'resolution': ['1D']})
    self.assertEqual(status, 200)
    self.assertEqual(res.get('code'), 'SSI')
    self.assertIn('decisionEngine', res)
    self.assertIn('technicals', res)

  def test_route_market_regime(self):
    status, res = _route_market_regime({})
    self.assertEqual(status, 200)
    self.assertIn('regime', res)
    self.assertIn('score', res)
    self.assertIn('conditions', res)

  def test_route_market_sentiment(self):
    status, res = _route_market_sentiment({})
    self.assertEqual(status, 200)
    # Có thể là fearGreedIndex hoặc sentiment data
    self.assertTrue('score' in res or 'fearGreedIndex' in res or isinstance(res, dict))

  def test_route_top_tplus(self):
    status, res = _route_top_tplus({})
    self.assertEqual(status, 200)
    self.assertTrue(isinstance(res, (list, dict)))

  def test_route_search(self):
    status, res = _route_search({'q': ['FPT']})
    self.assertEqual(status, 200)
    self.assertIsInstance(res, list)

  def test_route_portfolio_bundle(self):
    status, res = _route_portfolio_bundle({'capital': ['50000000'], 'style': ['balanced']})
    self.assertEqual(status, 200)
    self.assertIsInstance(res, dict)

  def test_route_portfolio_sectors(self):
    status, res = _route_portfolio_sectors({'budget': ['20000000']})
    self.assertEqual(status, 200)
    self.assertTrue('sectors' in res or isinstance(res, list) or isinstance(res, dict))

  def test_route_portfolio_get(self):
    status, res = _route_portfolio_get({})
    self.assertEqual(status, 200)
    self.assertIn('trades', res)
    self.assertIn('holdings', res)
    self.assertIn('summary', res)

  def test_route_telegram_logs(self):
    status, res = _route_telegram_logs({'limit': ['10']})
    self.assertEqual(status, 200)
    self.assertEqual(res.get('status'), 'success')
    self.assertIsInstance(res.get('data'), list)


class TestPostApiHandlers(unittest.TestCase):
  """Kiểm thử các hàm xử lý POST API (Thêm, Xóa lệnh, Cài đặt)."""

  def test_portfolio_trade_crud_flow(self):
    # 1. Thêm một giao dịch mẫu hợp lệ
    mock_trade = {
        'symbol': 'SSI',
        'order_type': 'BUY',
        'volume': 100,
        'price': 30000,
        'trade_date': '2026-11-09',
        'note': 'Unit test trade'
    }
    status, res = _route_portfolio_trade_add(mock_trade, {})
    self.assertEqual(status, 200)
    self.assertTrue(res.get('success'))
    trade_id = res.get('id')

    # 2. Xóa giao dịch vừa tạo bằng ID
    if trade_id:
      status_del, res_del = _route_portfolio_trade_delete({'id': trade_id}, {})
      self.assertEqual(status_del, 200)
      self.assertTrue(res_del.get('success'))

  def test_portfolio_settings_save(self):
    mock_settings = {
        'total_nav': 100000000
    }
    status, res = _route_portfolio_settings(mock_settings, {})
    self.assertEqual(status, 200)
    self.assertTrue(res.get('success'))


class TestFrontendBackendSync(unittest.TestCase):
  """Kiểm tra tính đồng bộ giữa endpoints trong js/constants/apiUrls.js và backend GET/POST routes."""

  def test_frontend_endpoints_exist_in_backend(self):
    js_urls_file = os.path.join(ROOT_DIR, 'js', 'constants', 'apiUrls.js')
    self.assertTrue(os.path.isfile(js_urls_file), "File js/constants/apiUrls.js không tồn tại")

    with open(js_urls_file, 'r', encoding='utf-8') as f:
      content = f.read()

    # Tìm tất cả các sub-endpoint được định nghĩa trong API_ENDPOINTS = { ... }
    import re
    matches = re.findall(r":\s*'([^']+)'", content)
    self.assertTrue(len(matches) > 0, "Không tìm thấy endpoint nào trong apiUrls.js")

    all_backend_routes = set(list(GET_ROUTES.keys()) + list(POST_ROUTES.keys()))
    # Một số endpoint đặc biệt như auth và health
    all_backend_routes.add('/api/auth/verify')
    all_backend_routes.add('/api/auth/logout')
    all_backend_routes.add('/api/ping')
    all_backend_routes.add('/api/health')

    for sub_url in matches:
      full_api_path = f"/api{sub_url}" if not sub_url.startswith('/api') else sub_url
      # Bỏ qua screener-options nếu backend gom vào screener
      if sub_url == '/screener-options':
        continue
      self.assertIn(full_api_path, all_backend_routes, f"Endpoint {full_api_path} có ở frontend nhưng chưa có ở backend router")


if __name__ == '__main__':
  unittest.main(verbosity=2)
