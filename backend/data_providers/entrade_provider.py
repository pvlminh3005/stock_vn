"""
Stock RT - Entrade Chart Data Provider
Cung cấp dữ liệu nến kỹ thuật lịch sử (OHLCV) từ Entrade Chart API.
"""
import time
from backend.constants.config import DAILY_HISTORY_DAYS
from backend.constants.urls import build_entrade_chart_url
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
    url = build_entrade_chart_url('stock', {'from': from_ts, 'to': now_ts, 'symbol': ticker, 'resolution': '1D'})
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
  url = build_entrade_chart_url('stock', {'from': from_ts, 'to': now_ts, 'symbol': ticker, 'resolution': resolution})
  return fetch_json(url)


def fetch_intraday_snapshot(ticker, daily_prev_close=None):
  """
  Trích xuất snapshot giá và khối lượng thời gian thực (Realtime) từ luồng nến 1 phút Entrade.
  Đảm bảo cung cấp dữ liệu sống trong ngày (intraday) mà KHÔNG BỊ CHẶN IP trên Cloud / Render.
  """
  sym = (ticker or '').strip().upper()
  now_ts = int(time.time())
  from_ts = now_ts - 86400 * 2  # Lấy 2 ngày gần nhất
  url = build_entrade_chart_url('stock', {'from': from_ts, 'to': now_ts, 'symbol': sym, 'resolution': 1})

  try:
    data = fetch_json(url, timeout=5)
    t = data.get('t', [])
    c = data.get('c', [])
    v = data.get('v', [])
    o = data.get('o', [])
    h = data.get('h', [])
    l = data.get('l', [])

    if not c or len(c) == 0:
      return None

    # Múi giờ Việt Nam GMT+7
    vn_offset = 7 * 3600
    today_vn = time.strftime('%Y-%m-%d', time.gmtime(now_ts + vn_offset))

    # Lọc các nến 1 phút thuộc phiên hôm nay
    today_indices = [
        i for i in range(len(t))
        if time.strftime('%Y-%m-%d', time.gmtime(t[i] + vn_offset)) == today_vn
    ]

    # Nếu hôm nay chưa có nến (ngoài giờ giao dịch/cuối tuần): lấy nến phiên gần nhất
    if not today_indices:
      last_date = time.strftime('%Y-%m-%d', time.gmtime(t[-1] + vn_offset))
      today_indices = [
          i for i in range(len(t))
          if time.strftime('%Y-%m-%d', time.gmtime(t[i] + vn_offset)) == last_date
      ]

    if not today_indices:
      return None

    last_idx = today_indices[-1]
    scale = 1000 if c[last_idx] < 1000 else 1
    matched_price = float(c[last_idx] * scale)
    today_highs = [h[i] * scale for i in today_indices]
    today_lows = [l[i] * scale for i in today_indices]
    today_vols = [v[i] for i in today_indices]

    high_p = float(max(today_highs)) if today_highs else matched_price
    low_p = float(min(today_lows)) if today_lows else matched_price
    total_vol = int(sum(today_vols))

    # Xác định giá tham chiếu
    ref_price = 0.0
    if daily_prev_close and daily_prev_close > 0:
      ref_price = float(daily_prev_close)
    else:
      prev_indices = [i for i in range(len(t)) if i < today_indices[0]]
      if prev_indices:
        ref_price = float(c[prev_indices[-1]] * scale)
      else:
        ref_price = matched_price

    price_change = matched_price - ref_price
    pct_change = round((price_change / ref_price * 100), 2) if ref_price > 0 else 0.0

    # Lực mua / bán chủ động từ các nến 1 phút
    buy_vol = 0
    sell_vol = 0
    for i in today_indices:
      vol_bar = v[i]
      if c[i] > o[i]:
        buy_vol += vol_bar
      elif c[i] < o[i]:
        sell_vol += vol_bar
      else:
        buy_vol += vol_bar // 2
        sell_vol += vol_bar // 2

    total_bs = buy_vol + sell_vol
    buy_ratio = round((buy_vol / total_bs * 100), 1) if total_bs > 0 else 50.0

    return {
        'stockSymbol': sym,
        'matchedPrice': matched_price,
        'refPrice': ref_price,
        'highest': high_p,
        'lowest': low_p,
        'stockVol': total_vol,
        'nmTotalTradedValue': float(total_vol * matched_price),
        'buyVol': buy_vol,
        'sellVol': sell_vol,
        'buyRatio': buy_ratio,
        'priceChange': price_change,
        'priceChangePercent': pct_change,
        'companyNameVi': f'CTCP {sym}',
        'exchange': 'HOSE',
        'stockType': 's',
        'isEntradeRealtime': True,
    }
  except Exception:
    return None


def handle_chart_only(ticker, resolution='1D'):
  """Trả về dữ liệu nến phục vụ chuyển nhanh khung thời gian trên biểu đồ."""
  from backend.data_providers.market_board_provider import get_market_board_data
  from backend.utils.ohlc_helpers import merge_live_candle_to_chart_data

  board_data = get_market_board_data()
  board_item = board_data.get(ticker, {})

  if resolution == '1D':
    days = DAILY_HISTORY_DAYS
  elif resolution == '1W':
    days = 730
  elif resolution == '1M':
    days = 1825
  else:
    days = 120
  chart_data = fetch_chart_data(ticker, days=days, resolution=resolution, ssi_item=board_item)
  chart_data = merge_live_candle_to_chart_data(chart_data, board_item, resolution=resolution)
  return {
      'ticker': ticker,
      'resolution': resolution,
      'candles': format_candles(chart_data, resolution=resolution),
  }
