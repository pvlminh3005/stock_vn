"""
Stock RT - Entrade Chart Data Provider
Cung cấp dữ liệu nến kỹ thuật lịch sử (OHLCV) từ Entrade Chart API.
"""
import time
from backend.constants.config import DAILY_HISTORY_DAYS
from backend.utils.network import fetch_json
from backend.utils.ohlc_helpers import format_candles

def aggregate_monthly_candles(daily_data):
  """Tổng hợp nến ngày (1D) thành nến tháng (1M) chuẩn OHLCV."""
  if not daily_data or not isinstance(daily_data, dict):
    return {'t': [], 'o': [], 'h': [], 'l': [], 'c': [], 'v': []}

  t_list = daily_data.get('t', [])
  o_list = daily_data.get('o', [])
  h_list = daily_data.get('h', [])
  l_list = daily_data.get('l', [])
  c_list = daily_data.get('c', [])
  v_list = daily_data.get('v', [])
  n = len(t_list)
  if n == 0:
    return {'t': [], 'o': [], 'h': [], 'l': [], 'c': [], 'v': []}

  months = {}
  for i in range(n):
    ts = t_list[i]
    lt = time.localtime(ts)
    key = (lt.tm_year, lt.tm_mon)
    if key not in months:
      months[key] = {
          't': ts,
          'o': o_list[i],
          'h': h_list[i],
          'l': l_list[i],
          'c': c_list[i],
          'v': v_list[i] if i < len(v_list) else 0,
      }
    else:
      m = months[key]
      m['h'] = max(m['h'], h_list[i])
      m['l'] = min(m['l'], l_list[i])
      m['c'] = c_list[i]
      m['v'] += (v_list[i] if i < len(v_list) else 0)

  res = {'t': [], 'o': [], 'h': [], 'l': [], 'c': [], 'v': []}
  for key in sorted(months.keys()):
    m = months[key]
    for k in res:
      res[k].append(m[k])
  return res

def fetch_chart_data(ticker, days=120, resolution='1D', ssi_item=None):
  """Lấy nến kỹ thuật đầy đủ (t, o, h, l, c, v) từ Entrade API theo resolution."""
  now_ts = int(time.time())
  if resolution == '1M':
    days_1m = 1825
    from_ts = now_ts - (days_1m * 86400)
    url = f'https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?from={from_ts}&to={now_ts}&symbol={ticker}&resolution=1D'
    raw_daily = fetch_json(url)
    if ssi_item:
      from backend.utils.ohlc_helpers import merge_live_candle_to_chart_data
      raw_daily = merge_live_candle_to_chart_data(raw_daily, ssi_item, resolution='1D')
    return aggregate_monthly_candles(raw_daily)
  elif resolution == '1W':
    days = 730
  elif resolution in ['1H', '30']:
    days = 40
  elif resolution in ['15', '5']:
    days = 15
  from_ts = now_ts - (days * 86400)
  url = f'https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?from={from_ts}&to={now_ts}&symbol={ticker}&resolution={resolution}'
  return fetch_json(url)

def handle_chart_only(ticker, resolution='1D'):
  """Trả về dữ liệu nến phục vụ chuyển nhanh khung thời gian trên biểu đồ."""
  from backend.data_providers.ssi_provider import get_ssi_board_data
  from backend.utils.ohlc_helpers import merge_live_candle_to_chart_data

  ssi_board = get_ssi_board_data()
  ssi_item = ssi_board.get(ticker, {})

  if resolution == '1D':
    days = DAILY_HISTORY_DAYS
  elif resolution == '1W':
    days = 730
  elif resolution == '1M':
    days = 1825
  else:
    days = 120
  chart_data = fetch_chart_data(ticker, days=days, resolution=resolution, ssi_item=ssi_item)
  chart_data = merge_live_candle_to_chart_data(chart_data, ssi_item, resolution=resolution)
  return {
      'ticker': ticker,
      'resolution': resolution,
      'candles': format_candles(chart_data, resolution=resolution),
  }
