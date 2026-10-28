"""
Stock RT - Screener Controller
Bộ lọc cổ phiếu và tìm kiếm:
- /api/search: Tìm kiếm mã theo ký tự
- /api/screener: Bộ lọc cổ phiếu theo thanh khoản và biến động thực tế từ SSI
- /api/top-tplus: VSR Smart Screener Top 8 Cơ hội Lướt Sóng T+ (Phễu 2 tầng)
"""

import threading
import time

from backend.data_providers.ssi_provider import get_ssi_board_data
from backend.domain.screener_engine import build_top_tplus_opportunities, is_market_hours

_TOP_TPLUS_CACHE = {
    'timestamp': 0,
    'data': None,
}
_CACHE_LOCK = threading.Lock()
_WORKER_STARTED = False
_CACHE_TTL_SEC = 180  # 3 phút


def _screener_worker_loop():
  """Tiến trình chạy ngầm làm mới dữ liệu Top T+ định kỳ 3 phút trong giờ giao dịch."""
  while True:
    try:
      in_market = is_market_hours()
      # Quét định lượng Universe Top 45 mã
      data = build_top_tplus_opportunities(max_total=8)
      if data and data.get('topOpportunities'):
        with _CACHE_LOCK:
          _TOP_TPLUS_CACHE['data'] = data
          _TOP_TPLUS_CACHE['timestamp'] = time.time()
      
      if in_market:
        time.sleep(_CACHE_TTL_SEC)  # 3 phút trong phiên giao dịch
      else:
        time.sleep(600)  # Ngoài giờ giao dịch: ngủ 10 phút để tránh spam API
    except Exception as e:
      time.sleep(30)


def start_screener_worker():
  """Khởi động Background Worker một lần duy nhất khi server bật."""
  global _WORKER_STARTED
  with _CACHE_LOCK:
    if not _WORKER_STARTED:
      _WORKER_STARTED = True
      t = threading.Thread(target=_screener_worker_loop, daemon=True)
      t.start()


def handle_search(query):
  """Tìm kiếm mã cổ phiếu từ bảng giá SSI."""
  q = (query or '').strip().upper()
  if not q:
    return []
  board = get_ssi_board_data()
  results = []
  for sym, item in board.items():
    if sym.startswith(q) or q in str(item.get('companyNameVi', '')).upper():
      results.append({
          'symbol': sym,
          'name': item.get('companyNameVi', item.get('clientName', sym)),
          'exchange': item.get('exchange', 'HOSE'),
          'price': item.get('matchedPrice', item.get('refPrice', 0)),
          'change': item.get('priceChange', 0),
          'percentChange': item.get('priceChangePercent', 0),
      })
      if len(results) >= 15:
        break
  return results


def handle_screener():
  """Bộ lọc cổ phiếu thanh khoản cao và tích cực trong phiên."""
  board = get_ssi_board_data()
  stocks = [
      v for v in board.values()
      if v.get('stockType') == 's' and len(str(v.get('stockSymbol', ''))) == 3
  ]
  # Sắp xếp theo giá trị giao dịch
  sorted_stocks = sorted(
      (s for s in stocks if (s.get('nmTotalTradedValue') or 0) > 0),
      key=lambda s: -(s.get('nmTotalTradedValue') or 0),
  )
  items = []
  for s in sorted_stocks[:50]:
    items.append({
        'symbol': s.get('stockSymbol'),
        'name': s.get('companyNameVi', s.get('clientName', '')),
        'exchange': s.get('exchange', 'HOSE'),
        'price': s.get('matchedPrice', s.get('refPrice', 0)),
        'change': s.get('priceChange', 0),
        'percentChange': s.get('priceChangePercent', 0),
        'volume': s.get('stockVol', 0),
        'value': s.get('nmTotalTradedValue', 0),
        'foreignNet': (s.get('buyForeignQtty', 0) - s.get('sellForeignQtty', 0)),
    })
  return {'stocks': items}


def handle_top_tplus():
  """
  API /api/top-tplus: VSR Smart Screener Top 8 Cơ hội Lướt Sóng T+:
  - Trả về tức thì từ In-Memory Cache (0 delay)
  - Phân loại rõ ràng ⚡ BÙNG NỔ T0 vs 🎯 GOM PULLBACK T1-T2
  - Đảm bảo tương thích ngược cấu trúc dữ liệu cũ
  """
  start_screener_worker()

  with _CACHE_LOCK:
    cached_data = _TOP_TPLUS_CACHE.get('data')
    ts = _TOP_TPLUS_CACHE.get('timestamp', 0)

  # Nếu cache đã có sẵn và còn trong vòng 20 phút thì phục vụ ngay lập tức
  if cached_data and (time.time() - ts < 1200):
    opps = cached_data.get('topOpportunities', [])
    return {
        **cached_data,
        'top': opps,  # Tương thích ngược với caller cũ
        'stocks': opps,
    }

  # Nếu cold-start chưa có dữ liệu, tính toán trực tiếp 1 lần và lưu cache
  try:
    fresh_data = build_top_tplus_opportunities(max_total=8)
    with _CACHE_LOCK:
      _TOP_TPLUS_CACHE['data'] = fresh_data
      _TOP_TPLUS_CACHE['timestamp'] = time.time()
    opps = fresh_data.get('topOpportunities', [])
    return {
        **fresh_data,
        'top': opps,
        'stocks': opps,
    }
  except Exception as e:
    # Fallback an toàn: nếu tính toán nến gặp lỗi, fallback về top gainers thanh khoản
    res = handle_screener()
    stocks = res.get('stocks', [])
    gainers = [s for s in stocks if s.get('percentChange', 0) > 0]
    gainers.sort(key=lambda s: -(s.get('percentChange', 0)))
    top_items = gainers[:8]
    return {
        'updatedAt': time.strftime('%H:%M:%S %d/%m/%Y'),
        'marketRegime': 'NEUTRAL',
        'totalScanned': len(stocks),
        'topOpportunities': top_items,
        'top': top_items,
        'stocks': top_items,
        'isFallback': True,
    }
