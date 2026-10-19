"""
Stock RT - SSI iBoard Data Provider
Cung cấp dữ liệu bảng giá thời gian thực từ sàn HOSE, HNX, UPCoM.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from backend.constants.config import SSI_HEADERS, SSI_CACHE_TTL
from backend.utils.network import fetch_json

_SSI_CACHE = {'timestamp': 0, 'data': {}}

def get_ssi_board_data():
  """Lấy snapshot toàn bộ bảng giá 3 sàn HOSE, HNX, UPCoM từ SSI iBoard (cache 45 giây)."""
  global _SSI_CACHE
  now = time.time()
  if now - _SSI_CACHE['timestamp'] < SSI_CACHE_TTL and _SSI_CACHE['data']:
    return _SSI_CACHE['data']

  stock_map = {}
  def _fetch_exchange(ex):
    try:
      url = f'https://iboard-query.ssi.com.vn/stock/exchange/{ex}'
      res = fetch_json(url, headers=SSI_HEADERS, timeout=6)
      items = res.get('data', [])
      for item in items:
        item['exchange'] = ex.upper()
      return items
    except Exception as e:
      print(f'Lỗi fetch SSI board {ex}:', e)
      return []

  try:
    with ThreadPoolExecutor(max_workers=3) as pool:
      results = pool.map(_fetch_exchange, ['hose', 'hnx', 'upcom'])
      for items in results:
        for item in items:
          sym = item.get('stockSymbol')
          if sym:
            stock_map[sym.upper()] = item
    if stock_map:
      _SSI_CACHE['timestamp'] = now
      _SSI_CACHE['data'] = stock_map
      return stock_map
  except Exception as e:
    print('Lỗi fetch SSI board:', e)

  return _SSI_CACHE.get('data', {})
