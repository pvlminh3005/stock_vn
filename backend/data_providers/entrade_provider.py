"""
Stock RT - Entrade Chart Data Provider
Cung cấp dữ liệu nến kỹ thuật lịch sử (OHLCV) từ Entrade Chart API.
"""
import time
from backend.constants.config import DAILY_HISTORY_DAYS
from backend.utils.network import fetch_json
from backend.utils.ohlc_helpers import format_candles

def fetch_chart_data(ticker, days=120, resolution='1D'):
  """Lấy nến kỹ thuật đầy đủ (t, o, h, l, c, v) từ Entrade API theo resolution."""
  now_ts = int(time.time())
  if resolution == '1W':
    days = 365
  elif resolution in ['1H', '30']:
    days = 40
  elif resolution in ['15', '5']:
    days = 15
  from_ts = now_ts - (days * 86400)
  url = f'https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?from={from_ts}&to={now_ts}&symbol={ticker}&resolution={resolution}'
  return fetch_json(url)

def handle_chart_only(ticker, resolution='1D'):
  """Trả về dữ liệu nến phục vụ chuyển nhanh khung thời gian trên biểu đồ."""
  days = DAILY_HISTORY_DAYS if resolution == '1D' else 120
  chart_data = fetch_chart_data(ticker, days=days, resolution=resolution)
  return {
      'ticker': ticker,
      'resolution': resolution,
      'candles': format_candles(chart_data, resolution=resolution),
  }
