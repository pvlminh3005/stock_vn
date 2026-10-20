"""
Stock RT - Technical Analysis & Quantitative Scoring Engine
Phân tích kỹ thuật chuyên sâu: RSI, EMA, SMA, ATR chuẩn Wilder, Fractal Pivots,
VSA Volume Signals, Multi-timeframe Confluence (D1 vs W1), và Risk-Budget Position Sizing.
"""

import time
import pandas as pd

from backend.constants.colors import (
    VOL_COLOR_INFLOW,
    VOL_COLOR_DISTRIBUTION,
    VOL_COLOR_WARNING,
    VOL_COLOR_ACTIVE,
    VOL_COLOR_NEUTRAL,
    STATUS_COLOR_PERFECT,
    STATUS_COLOR_MOMENTUM,
    STATUS_COLOR_VALUE,
    STATUS_COLOR_NEUTRAL,
    STATUS_COLOR_RISK,
    DECISION_TYPE_SUCCESS,
    DECISION_TYPE_WARNING,
    DECISION_TYPE_DANGER,
    DECISION_TYPE_INFO,
    DECISION_TYPE_NEUTRAL as DECISION_NEUTRAL,
)
from backend.constants.config import (
    DAILY_HISTORY_DAYS,
    VN_UTC_OFFSET_SEC,
    T_PLUS_RISK_BUDGET_PCT,
    SINGLE_STOCK_NAV_CAP_PCT,
)
from backend.utils.network import fetch_json
from backend.utils.time_utils import vn_date
from backend.utils.ohlc_helpers import merge_live_session_bar
from backend.data_providers.entrade_provider import fetch_chart_data
from backend.domain.valuation import calculate_fundamental_valuation

_VNINDEX_CACHE = {'timestamp': 0, 'data': None}
_WEEKLY_CHART_CACHE = {}


def get_vnindex_series(days=DAILY_HISTORY_DAYS):
  """Nến ngày VN-Index kèm ngày giao dịch (YYYY-MM-DD theo giờ VN) và khối lượng."""
  global _VNINDEX_CACHE
  now = time.time()
  cached = _VNINDEX_CACHE.get('data')
  if cached and now - _VNINDEX_CACHE['timestamp'] < 60:
    return cached
  try:
    now_ts = int(now)
    from_ts = now_ts - (days * 86400)
    url = f'https://services.entrade.com.vn/chart-api/v2/ohlcs/index?from={from_ts}&to={now_ts}&symbol=VNINDEX&resolution=1D'
    data = fetch_json(url)
    if data.get('c'):
      series = {
          'dates': [vn_date(t) for t in data.get('t', [])],
          'closes': data.get('c', []),
          'volumes': data.get('v', []),
      }
      _VNINDEX_CACHE['timestamp'] = now
      _VNINDEX_CACHE['data'] = series
      return series
  except Exception as e:
    print('Lỗi fetch VNINDEX candles:', e)
  return cached or {'dates': [], 'closes': [], 'volumes': []}


def calculate_relative_strength(stock_dates, stock_closes, vnindex_series):
  """Sức mạnh giá tương đối của cổ phiếu so với VN-Index (thang 5 - 99, 50 = đi cùng thị trường).

  - Hai chuỗi được ghép theo NGÀY giao dịch chung (tránh lệch khi mã có phiên ngừng giao dịch).
  - Đo Alpha so với VN-Index trong 1 tháng (20 phiên) và 3 tháng (60 phiên), trọng số 40/60.
  - Đây là điểm alpha tương đối, KHÔNG phải RS Rating O'Neil (xếp hạng phần trăm trên toàn thị trường).
    >= 80: Dẫn dắt mạnh | 65 - 79: Mạnh hơn VN-Index | 45 - 64: Trung tính
    40 - 44: Bắt đầu yếu hơn VN-Index | < 40: Tụt hậu
  """
  vni_map = dict(zip(vnindex_series.get('dates', []), vnindex_series.get('closes', [])))
  pairs = [(c, vni_map[d]) for d, c in zip(stock_dates, stock_closes) if d in vni_map]
  stock_closes = [p[0] for p in pairs]
  vnindex_closes = [p[1] for p in pairs]
  if len(stock_closes) < 15:
    return {
        'rsScore': 50,
        'rsStatus': 'neutral',
        'rsColor': 'amber',
        'stockAlpha1M': 0.0,
        'stockAlpha3M': 0.0,
        'stockPerf1M': 0.0,
        'vniPerf1M': 0.0,
        'stockPerf3M': 0.0,
        'vniPerf3M': 0.0,
    }

  n_1m = min(20, len(stock_closes) - 1)
  n_3m = min(60, len(stock_closes) - 1)

  stk_now = stock_closes[-1]
  stk_1m_ago = stock_closes[-1 - n_1m]
  stk_3m_ago = stock_closes[-1 - n_3m]

  vni_now = vnindex_closes[-1]
  vni_1m_ago = vnindex_closes[-1 - n_1m]
  vni_3m_ago = vnindex_closes[-1 - n_3m]

  stk_perf_1m = ((stk_now - stk_1m_ago) / stk_1m_ago) * 100.0 if stk_1m_ago > 0 else 0.0
  stk_perf_3m = ((stk_now - stk_3m_ago) / stk_3m_ago) * 100.0 if stk_3m_ago > 0 else 0.0

  vni_perf_1m = ((vni_now - vni_1m_ago) / vni_1m_ago) * 100.0 if vni_1m_ago > 0 else 0.0
  vni_perf_3m = ((vni_now - vni_3m_ago) / vni_3m_ago) * 100.0 if vni_3m_ago > 0 else 0.0

  alpha_1m = stk_perf_1m - vni_perf_1m
  alpha_3m = stk_perf_3m - vni_perf_3m

  # Trọng số: 60% 3 tháng gần nhất, 40% 1 tháng gần nhất
  raw_alpha = (alpha_3m * 0.6) + (alpha_1m * 0.4)
  rs_score = int(round(50 + (raw_alpha * 2.0)))
  rs_score = max(5, min(99, rs_score))

  if rs_score >= 80:
    rs_status = 'leader'
    rs_color = 'emerald'
  elif rs_score >= 65:
    rs_status = 'outperforming'
    rs_color = 'blue'
  elif rs_score >= 45:
    rs_status = 'neutral'
    rs_color = 'slate'
  elif rs_score >= 40:
    rs_status = 'underperforming'
    rs_color = 'amber'
  else:
    rs_status = 'laggard'
    rs_color = 'rose'

  return {
      'rsScore': rs_score,
      'rsStatus': rs_status,
      'rsColor': rs_color,
      'stockAlpha1M': round(alpha_1m, 1),
      'stockAlpha3M': round(alpha_3m, 1),
      'stockPerf1M': round(stk_perf_1m, 1),
      'vniPerf1M': round(vni_perf_1m, 1),
      'stockPerf3M': round(stk_perf_3m, 1),
      'vniPerf3M': round(vni_perf_3m, 1),
  }


def calculate_multi_timeframe_confluence(ticker, current_price, d1_ma20):
  """Kiểm tra xu hướng đồng thuận đa khung thời gian Ngày (D1) vs Tuần (W1)."""
  global _WEEKLY_CHART_CACHE
  now = time.time()
  w_data = None
  if ticker:
    cached = _WEEKLY_CHART_CACHE.get(ticker)
    if cached and (now - cached['time'] < 60):
      w_data = cached['data']
    else:
      try:
        w_data = fetch_chart_data(ticker, days=365, resolution='1W')
        _WEEKLY_CHART_CACHE[ticker] = {'time': now, 'data': w_data}
      except Exception:
        w_data = None

  d1_bullish = current_price >= d1_ma20 if d1_ma20 > 0 else True
  w1_bullish = False
  w_ma10 = 0.0

  if w_data and w_data.get('c'):
    w_closes = w_data['c']
    scale = 1000 if w_closes[-1] < 1000 else 1
    if len(w_closes) >= 10:
      w_ma10 = sum(w_closes[-10:]) / 10.0 * scale
      w1_bullish = current_price >= w_ma10

  if d1_bullish and w1_bullish:
    confluence = 'Đồng thuận Uptrend Đa Khung (D1 + W1)'
    color = 'emerald'
    is_aligned_bull = True
    is_severe_down = False
    desc = f'Nến ngày nằm trên MA20 ({d1_ma20:,.0f} đ) và nến tuần vững trên MA10 Tuần ({w_ma10:,.0f} đ). Xu hướng tăng bền vững được bảo trợ.'
  elif d1_bullish and not w1_bullish:
    confluence = 'Sóng hồi T+ trong Downtrend Tuần'
    color = 'amber'
    is_aligned_bull = False
    is_severe_down = False
    desc = f'Nến ngày vượt MA20 ({d1_ma20:,.0f} đ) nhưng vẫn nằm dưới MA10 Tuần ({w_ma10:,.0f} đ). Chỉ ưu tiên lướt sóng nhanh T+, không ôm dài hạn.'
  elif not d1_bullish and w1_bullish:
    confluence = 'Điều chỉnh ngắn hạn trên nền Uptrend Tuần'
    color = 'blue'
    is_aligned_bull = False
    is_severe_down = False
    desc = f'Nến ngày dưới MA20 nhưng xu hướng tuần vẫn giữ được MA10 ({w_ma10:,.0f} đ). Canh mua gom khi giá kiểm định hỗ trợ tuần.'
  else:
    confluence = 'Downtrend Toàn Diện (Tránh Bắt Đáy)'
    color = 'rose'
    is_aligned_bull = False
    is_severe_down = True
    desc = f'Giá vận động dưới cả MA20 Ngày ({d1_ma20:,.0f} đ) và MA10 Tuần ({w_ma10:,.0f} đ). Rủi ro giảm sâu tiếp diễn, kiên nhẫn đứng ngoài.'

  return {
      'confluence': confluence,
      'color': color,
      'd1Bullish': d1_bullish,
      'w1Bullish': w1_bullish,
      'wMa10': round(w_ma10, 0),
      'isAlignedBullish': is_aligned_bull,
      'isSevereDowntrend': is_severe_down,
      'description': desc,
  }


def calculate_rsi(closes, period=14):
  """Tính toán RSI 14 phiên chuẩn kỹ thuật Wilder trên chuỗi giá đóng cửa gần nhất."""
  if not closes or len(closes) < 3:
    return 50.0
  if len(closes) < period + 1:
    p = len(closes) - 1
    recent = closes[-p - 1:]
    diffs = [recent[i] - recent[i - 1] for i in range(1, len(recent))]
    g = sum(d for d in diffs if d > 0) / p
    l = sum(-d for d in diffs if d < 0) / p
    if l == 0:
      return 80.0
    return round(100.0 - (100.0 / (1.0 + g / l)), 1)

  s = pd.Series(closes, dtype=float)
  delta = s.diff()
  gain = delta.where(delta > 0, 0.0)
  loss = -delta.where(delta < 0, 0.0)
  avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
  avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
  rs = avg_gain / avg_loss
  rsi = 100.0 - (100.0 / (1.0 + rs))
  val = rsi.iloc[-1]
  return round(float(val), 1) if not pd.isna(val) else 50.0


def calculate_sma(series, period=20):
  if not series:
    return 0.0
  slice_data = series[-period:]
  return round(sum(slice_data) / len(slice_data), 1)


def calculate_ema(series, period=20):
  """Tính toán Exponential Moving Average (EMA) chu kỳ N phiên."""
  if not series:
    return 0.0
  if len(series) < period:
    return calculate_sma(series, len(series))
  s = pd.Series(series, dtype=float)
  ema = s.ewm(span=period, adjust=False).mean()
  return round(float(ema.iloc[-1]), 1)


def detect_rsi_divergence(closes, period=14):
  """Phát hiện phân kỳ RSI (Bullish Divergence: Giá tạo đáy thấp hơn/bằng nhưng RSI tạo đáy cao hơn)."""
  if not closes or len(closes) < period + 8:
    return {'hasBullishDivergence': False, 'detail': ''}

  s = pd.Series(closes, dtype=float)
  delta = s.diff()
  gain = delta.where(delta > 0, 0.0)
  loss = -delta.where(delta < 0, 0.0)
  avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
  avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
  rs = avg_gain / avg_loss
  rsi_series = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0).tolist()

  n = min(len(closes), 16)
  c_sub = closes[-n:]
  r_sub = rsi_series[-n:]

  half = n // 2
  min_c1 = min(c_sub[:half])
  idx_c1 = c_sub[:half].index(min_c1)
  r1 = r_sub[idx_c1]

  min_c2 = min(c_sub[half:])
  idx_c2 = half + c_sub[half:].index(min_c2)
  r2 = r_sub[idx_c2]

  has_bull_div = False
  detail = ''
  if min_c2 <= min_c1 * 1.015 and r2 > (r1 + 2.5) and r1 < 48:
    has_bull_div = True
    detail = f'Phân kỳ dương RSI: Giá tạo đáy {min_c2:,.0f} đ (thấp hơn/ngang {min_c1:,.0f} đ) nhưng RSI tăng từ {r1:.1f} lên {r2:.1f}'

  return {
      'hasBullishDivergence': has_bull_div,
      'detail': detail,
  }


def calculate_atr(highs, lows, closes, period=14):
  """Tính toán ATR 14 phiên chuẩn kỹ thuật Wilder (Average True Range)."""
  if not closes or len(closes) < 2:
    return 0.0
  tr_list = []
  for i in range(1, len(closes)):
    h = highs[i]
    l = lows[i]
    prev_c = closes[i - 1]
    tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
    tr_list.append(tr)
  if not tr_list:
    return 0.0
  if len(tr_list) < period:
    return round(float(sum(tr_list) / len(tr_list)), 1)
  atr = sum(tr_list[:period]) / period
  for tr in tr_list[period:]:
    atr = (atr * (period - 1) + tr) / period
  return round(float(atr), 1)


def calculate_supertrend(highs, lows, closes, period=10, multiplier=2.0):
  """Tính toán dải chỉ báo SuperTrend (ATR Volatility Trailing Band).

  Xác định xu hướng Xanh Vào (Bullish) / Hồng Ra (Bearish) và nhận diện điểm đảo chiều Flip.
  - Sóng Xanh (Bullish): Dải hỗ trợ Lower Band bám sát chân nến.
  - Sóng Hồng (Bearish): Dải kháng cự Upper Band bám sát đỉnh nến.
  """
  n = len(closes)
  if n < 2:
    return {
        'direction': 'NEUTRAL',
        'isBullish': True,
        'isBearish': False,
        'isFlipBuy': False,
        'isFlipSell': False,
        'bandPrice': closes[-1] if closes else 0.0,
    }

  tr_list = [highs[0] - lows[0]]
  for i in range(1, n):
    tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    tr_list.append(tr)

  atr = [0.0] * n
  sum_tr = 0.0
  for i in range(n):
    if i < period:
      sum_tr += tr_list[i]
      atr[i] = sum_tr / (i + 1)
    else:
      atr[i] = (atr[i - 1] * (period - 1) + tr_list[i]) / period

  final_upper = [0.0] * n
  final_lower = [0.0] * n
  trend = [1] * n

  for i in range(n):
    hl2 = (highs[i] + lows[i]) / 2.0
    basic_upper = hl2 + multiplier * atr[i]
    basic_lower = hl2 - multiplier * atr[i]

    if i == 0:
      final_upper[i] = basic_upper
      final_lower[i] = basic_lower
      trend[i] = 1 if closes[i] >= highs[i] * 0.99 else -1
    else:
      if basic_upper < final_upper[i - 1] or closes[i - 1] > final_upper[i - 1]:
        final_upper[i] = basic_upper
      else:
        final_upper[i] = final_upper[i - 1]

      if basic_lower > final_lower[i - 1] or closes[i - 1] < final_lower[i - 1]:
        final_lower[i] = basic_lower
      else:
        final_lower[i] = final_lower[i - 1]

      if trend[i - 1] == 1:
        trend[i] = -1 if closes[i] < final_lower[i] else 1
      else:
        trend[i] = 1 if closes[i] > final_upper[i] else -1

  last_trend = trend[-1]
  prev_trend = trend[-2] if n >= 2 else last_trend
  is_flip_buy = (last_trend == 1 and prev_trend == -1)
  is_flip_sell = (last_trend == -1 and prev_trend == 1)
  current_band = final_lower[-1] if last_trend == 1 else final_upper[-1]

  return {
      'direction': 'BULLISH' if last_trend == 1 else 'BEARISH',
      'isBullish': last_trend == 1,
      'isBearish': last_trend == -1,
      'isFlipBuy': is_flip_buy,
      'isFlipSell': is_flip_sell,
      'bandPrice': round(current_band, -2) if current_band >= 1000 else round(current_band, 2),
  }


def identify_structural_levels(highs, lows, closes, current_price, atr14):
  """Xác định hỗ trợ S1, S2 và kháng cự R1, R2 dựa trên cấu trúc Fractal Pivots (Swing High/Low).

  TUYỆT ĐỐI KHÔNG GÁN CỨNG PHẦN TRĂM MẶC ĐỊNH (+8.5% hay -4.5%) mà tính từ nến OHLCV thực tế.
  """
  n = len(closes)
  lookback = min(60, n)
  sub_h = highs[-lookback:]
  sub_l = lows[-lookback:]
  sub_c = closes[-lookback:]
  m = len(sub_c)

  swing_highs = []
  swing_lows = []

  # Tìm các đỉnh / đáy Fractal pivot (3-bar fractal)
  for i in range(1, m - 1):
    if sub_h[i] >= sub_h[i - 1] and sub_h[i] >= sub_h[i + 1]:
      swing_highs.append(sub_h[i])
    if sub_l[i] <= sub_l[i - 1] and sub_l[i] <= sub_l[i + 1]:
      swing_lows.append(sub_l[i])

  # Hỗ trợ S1: Swing low cao nhất nằm dưới giá hiện tại (cách ít nhất 0.8% để tránh nhiễu)
  valid_supports = [sl for sl in swing_lows if sl < current_price * 0.992]
  if valid_supports:
    s1 = max(valid_supports)
  else:
    min_recent_l = min(sub_l) if sub_l else (current_price - 1.5 * atr14)
    s1 = min_recent_l if min_recent_l < current_price * 0.992 else (current_price - 1.5 * atr14)

  # Hỗ trợ S2: Ngưỡng hỗ trợ sâu hơn nằm dưới S1
  valid_s2 = [sl for sl in swing_lows if sl < s1 * 0.985]
  if valid_s2:
    s2 = max(valid_s2)
  else:
    s2 = s1 - max(atr14, s1 * 0.03)

  # Kháng cự R1: Swing high thấp nhất nằm trên giá hiện tại (cách ít nhất 0.8%)
  valid_resistances = [sh for sh in swing_highs if sh > current_price * 1.008]
  if valid_resistances:
    r1 = min(valid_resistances)
  else:
    # Vượt đỉnh 60 phiên / ATH: Đo mục tiêu theo Fibonacci Projection từ nhịp sóng gần nhất
    rec_low = min(sub_l[-20:]) if len(sub_l) >= 20 else s1
    rec_high = max(sub_h[-20:]) if len(sub_h) >= 20 else current_price
    wave_range = rec_high - rec_low
    if wave_range > atr14:
      r1 = current_price + (0.618 * wave_range)
    else:
      r1 = current_price + (2.0 * atr14)

  # Kháng cự R2: Ngưỡng cản tiếp theo trên R1
  valid_r2 = [sh for sh in swing_highs if sh > r1 * 1.015]
  if valid_r2:
    r2 = min(valid_r2)
  else:
    r2 = r1 + max(atr14 * 1.5, r1 * 0.035)

  # Chuẩn hóa làm tròn về đơn vị 50/100 VND
  s1 = round(s1, -2) if s1 >= 1000 else round(s1, 1)
  s2 = round(s2, -2) if s2 >= 1000 else round(s2, 1)
  r1 = round(r1, -2) if r1 >= 1000 else round(r1, 1)
  r2 = round(r2, -2) if r2 >= 1000 else round(r2, 1)

  return s1, s2, r1, r2


def detect_candlestick_exit_signals(
    opens, highs, lows, closes, volumes, current_price, ma20, atr14,
    support_level, resistance_level, rsi, vol_ma20, rs_info=None, is_partial=False
):
  """Phân tích chi tiết hành vi nến (Candlestick / Price Action) và Volume (VSA) các phiên gần nhất

  để phát hiện trạng thái 'NÊN CHỐT LỜI SỚM / BẢO TOÀN LỢI NHUẬN' khi cổ phiếu qua giai đoạn tốt.
  Phục vụ trực tiếp cho nhà đầu tư ĐANG NẮM GIỮ CỔ PHIẾU (Holders Perspective).
  """
  n = len(closes)
  if n < 5:
    return {
        'decision': 'QUAN SÁT THEO DÕI',
        'type': DECISION_NEUTRAL,
        'action': 'Chưa đủ dữ liệu nến',
        'candlePattern': 'Dữ liệu chưa ghi nhận',
        'candleDescription': 'Cần tối thiểu 5 phiên giao dịch để đánh giá hình thái nến.',
        'trailingStop': support_level,
        'trailingStopDisplay': f'{support_level:,.0f} đ',
        'distToTrailingStop': -4.0,
        'distributionDays': 0,
        'distDetails': [],
        'guide': 'Dữ liệu chưa đủ phiên nến để nhận diện mẫu hình.',
        'hasWarning': False,
        'patterns': [],
    }

  # Lấy dữ liệu 5 phiên gần nhất
  o0, h0, l0, c0, v0 = opens[-1], highs[-1], lows[-1], closes[-1], volumes[-1]
  o1, h1, l1, c1, v1 = opens[-2], highs[-2], lows[-2], closes[-2], volumes[-2]

  # Biên độ, thân nến, râu nến phiên gần nhất (-1)
  rng0 = max(1.0, h0 - l0)
  b0 = abs(c0 - o0)
  uw0 = max(0.0, h0 - max(c0, o0))
  uw_ratio0 = round(uw0 / rng0, 2)
  is_bearish0 = c0 < o0

  # Phiên trước (-2)
  rng1 = max(1.0, h1 - l1)
  b1 = abs(c1 - o1)
  uw1 = max(0.0, h1 - max(c1, o1))
  uw_ratio1 = round(uw1 / rng1, 2)
  is_bullish1 = c1 > o1

  v_ratio0 = round(v0 / vol_ma20, 2) if vol_ma20 > 0 else 1.0

  # Đường MA10 ngắn hạn
  ma10 = calculate_sma(closes, 10) if n >= 10 else ma20

  # Bối cảnh tăng giá: mức tăng so với đáy 15 phiên
  lookback_low = min(lows[-15:]) if n >= 15 else min(lows)
  gain_from_low = ((current_price - lookback_low) / lookback_low) * 100.0 if lookback_low > 0 else 0.0
  is_extended = (current_price >= ma20 * 1.03) or (gain_from_low >= 6.0) or (rsi >= 60.0)

  # 1. Đếm ngày phân phối (Distribution Days) trong 5 phiên gần nhất
  dist_days = 0
  dist_details = []
  check_len = min(5, n - 1)
  for idx in range(n - check_len, n):
    c_curr = closes[idx]
    c_prev = closes[idx - 1]
    v_curr = volumes[idx]
    v_prev = volumes[idx - 1]
    pct_down = ((c_curr - c_prev) / c_prev) * 100.0 if c_prev > 0 else 0.0
    if pct_down <= -0.2 and v_curr > v_prev and (vol_ma20 > 0 and v_curr >= 0.9 * vol_ma20):
      dist_days += 1
      dist_details.append(f'T-{n - 1 - idx} giảm {pct_down:.1f}% kèm Vol tăng')

  # 2. Nhận diện các Mẫu hình Nến Price Action đảo chiều / suy yếu
  detected_patterns = []

  # A. Shooting Star / Pin-bar rụt đỉnh
  if uw_ratio0 >= 0.48 and uw0 >= 1.7 * max(1.0, b0) and (min(c0, o0) - l0 <= 0.42 * rng0):
    if is_extended or v_ratio0 >= 1.1:
      detected_patterns.append({
          'name': 'Nến Shooting Star / Búa ngược rụt đỉnh',
          'severity': 'warning',
          'desc': (
              f'Giá tăng chạm {h0:,.0f} đ trong phiên nhưng bị phe bán ép dội ngược về {c0:,.0f} đ '
              f'(Râu trên chiếm {uw_ratio0*100:.0f}% biên độ nến kèm Vol x{v_ratio0} TB20). '
              'Áp lực xả hàng quyết liệt ở vùng giá cao.'
          ),
      })

  # B. Bearish Engulfing (Nến nhấn chìm giảm)
  if is_bearish0 and is_bullish1 and (b1 >= 0.25 * atr14):
    if (o0 >= c1 * 0.996) and (c0 <= o1 * 1.004) and (c0 < l1):
      pat_sev = 'danger' if (v_ratio0 >= 1.1 or v0 > v1) else 'warning'
      detected_patterns.append({
          'name': 'Nến Bearish Engulfing (Nhấn chìm giảm)',
          'severity': pat_sev,
          'desc': (
              f'Nến đỏ thân dài ({o0:,.0f} đ -> {c0:,.0f} đ) nuốt chửng hoàn toàn nến tăng hôm qua kèm Vol x{v_ratio0} TB20. '
              'Phe bán đảo ngược quyền kiểm soát hoàn toàn xu hướng ngắn hạn.'
          ),
      })

  # C. Upthrust / Breakout xịt (Vượt đỉnh thất bại / Bull trap)
  if n >= 20:
    prev_20_high = max(highs[-21:-1])
    if h0 > prev_20_high and c0 < prev_20_high and (v_ratio0 >= 1.2 or uw_ratio0 >= 0.40):
      detected_patterns.append({
          'name': 'Nến Upthrust (Bẫy vượt đỉnh thất bại)',
          'severity': 'danger',
          'desc': (
              f'Giá bứt phá vượt đỉnh 20 phiên ({prev_20_high:,.0f} đ) lên {h0:,.0f} đ nhưng đóng cửa bị đạp ngược về {c0:,.0f} đ '
              f'với thanh khoản lớn x{v_ratio0} TB20. Dấu hiệu phân phối rõ rệt (kéo xả).'
          ),
      })

  # D. Dark Cloud Cover (Mây đen bao phủ)
  if is_bearish0 and is_bullish1 and (b1 >= 0.3 * atr14):
    if o0 >= c1 and c0 < (o1 + c1) / 2.0 and c0 >= o1:
      detected_patterns.append({
          'name': 'Nến Dark Cloud Cover (Mây đen bao phủ)',
          'severity': 'warning',
          'desc': (
              f'Mở gap tăng nhưng nến đỏ đâm sâu quá 50% thân nến xanh hôm trước ({c0:,.0f} đ). '
              'Lực cầu giá cao chững lại và bị hấp thụ ngược.'
          ),
      })

  # E. Hai phiên liên tiếp rút râu trên (Double Rejection Wicks)
  if len(detected_patterns) == 0 and uw_ratio0 >= 0.40 and uw_ratio1 >= 0.40 and is_extended:
    detected_patterns.append({
        'name': 'Cụm 2 nến rút râu trên liên tiếp',
        'severity': 'warning',
        'desc': (
            'Hai phiên liên tiếp xuất hiện râu nến trên dài (>40% biên độ). '
            'Vùng cản trên liên tục bị từ chối, động lượng tăng giá suy kiệt.'
        ),
    })

  # F. Thủng hỗ trợ động MA10 sau chuỗi ngày tăng
  if c0 < ma10 and c1 >= ma10 * 0.995 and is_bearish0:
    if is_extended or v_ratio0 >= 1.0:
      detected_patterns.append({
          'name': 'Nến gãy hỗ trợ động ngắn hạn MA10',
          'severity': 'danger',
          'desc': (
              f'Giá đóng cửa {c0:,.0f} đ xuyên thủng đường MA10 ({ma10:,.0f} đ). '
              'Đường ray tăng tốc ngắn hạn chính thức bị vi phạm.'
          ),
      })

  # G. No Demand Bar (Cạn kiệt lực cầu đỉnh)
  if len(detected_patterns) == 0 and is_extended and rng0 < 0.65 * atr14 and v_ratio0 <= 0.60:
    detected_patterns.append({
        'name': 'Nến cạn cầu (No Demand at Highs)',
        'severity': 'info',
        'desc': (
            f'Giá neo vùng cao nhưng biên độ nến co hẹp ({rng0:,.0f} đ) kèm Vol kiệt quệ chỉ x{v_ratio0} TB20. '
            'Lực cầu giá cao không mặn mà mua lên, tiềm ẩn nhịp chỉnh kiểm định lại cầu.'
        ),
    })

  # 3. Tính Mốc Chặn Lãi Động (Trailing Stop Price)
  if current_price >= ma20:
    candidate_ts = max(l1, round(ma10, -2))
    if candidate_ts >= current_price * 0.995:
      candidate_ts = round(current_price - (0.8 * atr14), -2)
    trailing_stop = max(round(support_level, -2), round(candidate_ts, -2))
  else:
    trailing_stop = round(support_level, -2)

  dist_to_ts = round(((trailing_stop - current_price) / current_price) * 100.0, 1) if current_price > 0 else 0.0

  # 4. Tổng hợp Quyết định Cho Vị Thế Đang Có (Holders Action)
  pattern_names = {p['name'] for p in detected_patterns}
  reversal_names = {
      'Nến Shooting Star / Búa ngược rụt đỉnh',
      'Nến Bearish Engulfing (Nhấn chìm giảm)',
      'Nến Dark Cloud Cover (Mây đen bao phủ)',
      'Cụm 2 nến rút râu trên liên tiếp',
  }
  rng_third = rng0 / 3.0
  weak_close = (is_bearish0 and (c0 - l0) <= rng_third) or bool(pattern_names & reversal_names)
  alpha_1m = (rs_info or {}).get('stockAlpha1M', 0.0)
  distribution_signals = [
      ('Đóng cửa yếu / nến đảo chiều', weak_close),
      (f'KL lớn ngày giảm ({dist_days} phiên/5)', dist_days >= 2),
      ('Breakout thất bại (Upthrust)', 'Nến Upthrust (Bẫy vượt đỉnh thất bại)' in pattern_names),
      ('Thủng hỗ trợ ngắn hạn (MA10/MA20)', ('Nến gãy hỗ trợ động ngắn hạn MA10' in pattern_names) or c0 < ma20),
      (f'RS 1 tháng xấu đi (Alpha {alpha_1m:+.1f}%)', alpha_1m < 0),
  ]
  signal_count = sum(1 for _, hit in distribution_signals if hit)
  signal_txt = ', '.join(name for name, hit in distribution_signals if hit) or 'không có'
  top_p = detected_patterns[0] if detected_patterns else None
  pattern_txt = f" Mẫu nến: {top_p['name']} - {top_p['desc']}" if top_p else ''
  cost_basis_note = (
      ' Chưa biết giá vốn của bạn: nếu đang lãi >= 1.5R cân nhắc chốt 20-30%, >= 2.5R chốt thêm 25-35%, phần còn lại giữ theo trailing stop.'
  )

  if signal_count >= 4:
    holding_decision = 'THOÁT VỊ THẾ (EXIT)'
    holding_type = DECISION_TYPE_DANGER
    holding_action = 'Bán phần lớn hoặc toàn bộ vị thế'
    p_name = top_p['name'] if top_p else f'{signal_count}/5 dấu hiệu phân phối'
    holding_guide = (
        f'Ghi nhận {signal_count}/5 dấu hiệu phân phối ({signal_txt}).{pattern_txt} '
        f'Cấu trúc tăng ngắn hạn đã hỏng; ưu tiên thoát vị thế, tối thiểu không để giá đóng cửa dưới Trailing Stop {trailing_stop:,.0f} đ ({dist_to_ts}%).'
    )
  elif signal_count == 3:
    holding_decision = 'GIẢM TỶ TRỌNG 30% - 50%'
    holding_type = DECISION_TYPE_WARNING
    holding_action = 'Bán bớt 1/3 - 1/2 vị thế'
    p_name = top_p['name'] if top_p else f'{signal_count}/5 dấu hiệu phân phối'
    holding_guide = (
        f'Ghi nhận {signal_count}/5 dấu hiệu phân phối ({signal_txt}).{pattern_txt} '
        f'Cân nhắc bán bớt 30% - 50% vị thế (chốt lời nếu đang lãi) và nâng Trailing Stop phần còn lại lên {trailing_stop:,.0f} đ ({dist_to_ts}%).{cost_basis_note}'
    )
  elif signal_count == 2 or (top_p and top_p['severity'] in ('danger', 'warning', 'info')):
    holding_decision = 'THEO DÕI SÁT / NÂNG CHẶN LÃI'
    holding_type = DECISION_TYPE_INFO
    holding_action = 'Nâng Trailing Stop & tạm dừng mua thêm'
    p_name = top_p['name'] if top_p else f'{signal_count}/5 dấu hiệu phân phối'
    holding_guide = (
        f'Ghi nhận {signal_count}/5 dấu hiệu phân phối ({signal_txt}).{pattern_txt} '
        f'Chưa đủ căn cứ bán; không mua thêm ở vùng giá này, nâng Trailing Stop lên {trailing_stop:,.0f} đ ({dist_to_ts}%).{cost_basis_note}'
    )
  elif current_price >= ma20 and not is_bearish0:
    holding_decision = 'TIẾP TỤC GỒNG LÃI (TREND RIDING)'
    holding_type = DECISION_TYPE_SUCCESS
    holding_action = 'Nắm giữ theo xu hướng'
    p_name = 'Nến giữ giá tích cực'
    rsi_note = f' RSI {rsi:.1f} cao không phải lý do bán, chỉ cần nâng chặn lãi sát hơn.' if rsi >= 70 else ''
    holding_guide = (
        f'Giá giữ trên MA20 ({ma20:,.0f} đ), {signal_count}/5 dấu hiệu phân phối. '
        f'Tiếp tục nắm giữ, Trailing Stop đặt tại {trailing_stop:,.0f} đ ({dist_to_ts}%).{rsi_note}'
    )
  elif current_price < ma20:
    holding_decision = 'DƯỚI MA20 - CANH CHẶN LỖ'
    holding_type = DECISION_TYPE_WARNING
    holding_action = 'Giữ kỷ luật chặn lỗ, không mua thêm'
    p_name = 'Vận động dưới MA20'
    holding_guide = (
        f'Giá nằm dưới MA20 ({ma20:,.0f} đ), xu hướng ngắn hạn nghiêng về giảm ({signal_count}/5 dấu hiệu phân phối). '
        f'Không bình quân giá xuống; nếu đóng cửa thủng hỗ trợ {support_level:,.0f} đ thì hạ tỷ trọng.'
    )
  else:
    holding_decision = 'QUAN SÁT THEO DÕI'
    holding_type = DECISION_NEUTRAL
    holding_action = 'Nắm giữ tỷ trọng an toàn'
    p_name = 'Nến đi ngang tích lũy'
    holding_guide = (
        f'Cổ phiếu đang vận động tích lũy đi ngang ({signal_count}/5 dấu hiệu phân phối). '
        f'Duy trì tỷ trọng an toàn và theo dõi mốc hỗ trợ {support_level:,.0f} đ.'
    )

  candle_note = (
      'Nến phiên hôm nay chưa hoàn thành (trước 14:45): mẫu hình nến và ngày phân phối đánh giá trên phiên đã đóng cửa gần nhất.'
      if is_partial else ''
  )
  if candle_note:
    holding_guide = f'{holding_guide} ({candle_note})'

  has_danger = holding_type == DECISION_TYPE_DANGER
  has_warning = holding_type == DECISION_TYPE_WARNING and signal_count >= 3

  return {
      'decision': holding_decision,
      'type': holding_type,
      'action': holding_action,
      'candlePattern': p_name,
      'candleDescription': detected_patterns[0]['desc'] if detected_patterns else 'Chưa xuất hiện mẫu hình nến đảo chiều nguy hiểm.',
      'trailingStop': trailing_stop,
      'trailingStopDisplay': f'{trailing_stop:,.0f} đ',
      'distToTrailingStop': dist_to_ts,
      'distributionDays': dist_days,
      'distDetails': dist_details,
      'guide': holding_guide,
      'hasWarning': has_danger or has_warning,
      'patterns': [p['name'] for p in detected_patterns],
      'distributionSignals': [{'name': name, 'hit': hit} for name, hit in distribution_signals],
      'distributionSignalCount': signal_count,
      'isPartialCandle': is_partial,
      'candleNote': candle_note,
  }


def calculate_weekly_levels(ticker, current_price):
  """Trích xuất ngưỡng kỹ thuật nến tuần W1 (52-week High/Low, Weekly MA10, Weekly MA50)."""
  global _WEEKLY_CHART_CACHE
  now = time.time()
  w_data = None
  if ticker:
    cached = _WEEKLY_CHART_CACHE.get(ticker)
    if cached and (now - cached['time'] < 60):
      w_data = cached['data']
    else:
      try:
        w_data = fetch_chart_data(ticker, days=730, resolution='1W')
        if w_data and w_data.get('c'):
          _WEEKLY_CHART_CACHE[ticker] = {'time': now, 'data': w_data}
      except Exception:
        w_data = None

  w_closes = w_data.get('c', []) if w_data else []
  w_highs = w_data.get('h', []) if w_data else []
  w_lows = w_data.get('l', []) if w_data else []

  if not w_closes:
    return {
        'w52High': current_price,
        'w52Low': current_price,
        'wMa10': current_price,
        'wMa50': current_price,
        'wCloses': [],
    }

  scale = 1000 if w_closes[-1] < 1000 else 1
  c_scaled = [c * scale for c in w_closes]
  h_scaled = [h * scale for h in w_highs]
  l_scaled = [l * scale for l in w_lows]

  n52 = min(52, len(c_scaled))
  w52_high = round(max(h_scaled[-n52:]), -2)
  w52_low = round(min(l_scaled[-n52:]), -2)

  n10 = min(10, len(c_scaled))
  w_ma10 = round(sum(c_scaled[-n10:]) / n10, -2)

  n50 = min(50, len(c_scaled))
  w_ma50 = round(sum(c_scaled[-n50:]) / n50, -2)

  return {
      'w52High': w52_high,
      'w52Low': w52_low,
      'wMa10': w_ma10,
      'wMa50': w_ma50,
      'wCloses': c_scaled,
  }


def classify_volume_signal(vol_ratio, day_change_pct, is_projected):
  """Khối lượng chỉ có ý nghĩa khi đi cùng chiều giá: KL lớn ngày giảm là phân phối, không phải dòng tiền vào."""
  tag = ' ước tính cả phiên' if is_projected else ''
  is_up = day_change_pct > 0
  is_down = day_change_pct < 0
  if vol_ratio >= 1.5:
    if is_up:
      return f'Dòng tiền vào mạnh: giá tăng kèm KL x{vol_ratio}{tag}', VOL_COLOR_INFLOW
    if is_down:
      return f'Bán mạnh kèm KL lớn x{vol_ratio}{tag} (dấu hiệu phân phối)', VOL_COLOR_DISTRIBUTION
    return f'KL lớn x{vol_ratio}{tag} nhưng giá đứng (giằng co cung cầu)', VOL_COLOR_WARNING
  if vol_ratio >= 1.0:
    if is_down:
      return f'Giá giảm với KL trên trung bình x{vol_ratio}{tag}', VOL_COLOR_WARNING
    if is_up:
      return f'Thanh khoản tích cực x{vol_ratio}{tag}', VOL_COLOR_ACTIVE
    return f'KL trên trung bình x{vol_ratio}{tag} nhưng giá đứng', VOL_COLOR_NEUTRAL
  if vol_ratio <= 0.6:
    if is_down:
      return f'Giảm với KL thấp x{vol_ratio}{tag} (lực bán yếu, cạn cung)', VOL_COLOR_NEUTRAL
    if is_up:
      return f'Tăng thiếu KL x{vol_ratio}{tag} (lực cầu chưa xác nhận)', VOL_COLOR_WARNING
    return f'Thanh khoản thấp x{vol_ratio}{tag}', VOL_COLOR_NEUTRAL
  return f'Thanh khoản bình quân x{vol_ratio}{tag}', VOL_COLOR_NEUTRAL


def analyze_technicals_and_scoring(
    candles_data, ssi_item, current_price, fundamental_info, ticker=None, exchange='HOSE', regime=None
):
  """Phân tích toàn diện kỹ thuật, xung lực dòng tiền, hỗ trợ/kháng cự động cấu trúc Fractal,

  ATR(14) chuẩn Wilder, Trade Plan T+ sau phí thuế và Đầu tư Trung/Dài hạn chuẩn BCTC.
  TUYỆT ĐỐI KHÔNG HARDCODE SỐ LIỆU HAY BỊA +/- %.
  """
  c_list = candles_data.get('c', [])
  o_list = candles_data.get('o', [])
  h_list = candles_data.get('h', [])
  l_list = candles_data.get('l', [])
  v_list = candles_data.get('v', [])
  t_list = candles_data.get('t', [])

  scale = 1000 if c_list and c_list[-1] < 1000 else 1
  closes = [p * scale for p in c_list]
  opens = [p * scale for p in o_list] if o_list else closes[:]
  highs = [p * scale for p in h_list]
  lows = [p * scale for p in l_list]
  volumes = [v for v in v_list]

  # Ghép nến phiên hôm nay từ SSI (không ghi đè nến hôm qua khi Entrade chưa có nến hôm nay)
  has_live_bar, is_partial, elapsed_fraction = merge_live_session_bar(
      t_list, opens, highs, lows, closes, volumes, ssi_item
  )
  # Chuỗi nến đã hoàn thành: dùng cho mẫu hình nến, ngày phân phối, KL trung bình và RS
  n_done = len(closes) - 1 if is_partial else len(closes)
  bar_dates = [vn_date(t) for t in t_list]
  if len(closes) > len(bar_dates):
    bar_dates.append(time.strftime('%Y-%m-%d', time.gmtime(time.time() + VN_UTC_OFFSET_SEC)))
  dates_done = bar_dates[:n_done]
  opens_done, highs_done, lows_done = opens[:n_done], highs[:n_done], lows[:n_done]
  closes_done, volumes_done = closes[:n_done], volumes[:n_done]

  rsi = calculate_rsi(closes, 14)
  ema9 = calculate_ema(closes, 9)
  ema21 = calculate_ema(closes, 21)
  rsi_div_info = detect_rsi_divergence(closes, 14)
  ma20 = calculate_sma(closes, 20)
  ma50 = calculate_sma(closes, 50) if len(closes) >= 50 else ma20
  vol_ma20 = calculate_sma(volumes_done, 20)
  latest_vol = volumes[-1] if volumes else 0
  projected_vol = latest_vol / elapsed_fraction if is_partial else latest_vol
  prev_close = closes[-2] if len(closes) >= 2 else current_price
  day_change_pct = round(((closes[-1] - prev_close) / prev_close) * 100, 2) if closes and prev_close else 0.0

  vol_ratio = round(projected_vol / vol_ma20, 2) if vol_ma20 > 0 else 1.0
  vol_signal, vol_color = classify_volume_signal(vol_ratio, day_change_pct, is_partial)

  buy_active = ssi_item.get('stockBUVol', 0) if ssi_item else 0
  sell_active = ssi_item.get('stockSDVol', 0) if ssi_item else 0
  total_active = buy_active + sell_active
  buy_ratio = round((buy_active / total_active) * 100, 1) if total_active else 50.0

  buy_foreign = ssi_item.get('buyForeignQtty', 0) if ssi_item else 0
  sell_foreign = ssi_item.get('sellForeignQtty', 0) if ssi_item else 0
  foreign_net = buy_foreign - sell_foreign

  atr14 = calculate_atr(highs, lows, closes, period=14)
  if atr14 <= 0:
    atr14 = round(current_price * 0.02, 1)

  support_level, s2_support, resistance_level, r2_target = identify_structural_levels(
      highs, lows, closes, current_price, atr14
  )

  rs_info = calculate_relative_strength(dates_done, closes_done, get_vnindex_series())
  supertrend_info = calculate_supertrend(highs, lows, closes, period=10, multiplier=2.0)

  position_holding = detect_candlestick_exit_signals(
      opens_done, highs_done, lows_done, closes_done, volumes_done, current_price, ma20, atr14,
      support_level, resistance_level, rsi, vol_ma20, rs_info=rs_info, is_partial=is_partial
  )

  structural_stop = support_level - (0.5 * atr14)
  if structural_stop >= current_price:
    structural_stop = current_price - atr14
  stop_price = round(min(structural_stop, current_price - 2.0 * atr14), -2)

  downside_val = max(1.0, current_price - stop_price)
  downside = round((downside_val / current_price) * 100, 1) if current_price > 0 else 4.0

  target_price = resistance_level
  upside_val = max(0.0, target_price - current_price)
  upside = round((upside_val / current_price) * 100, 1) if current_price > 0 else 8.0

  upside2_val = max(0.0, r2_target - current_price)
  upside2 = round((upside2_val / current_price) * 100, 1) if current_price > 0 else 12.0

  net_upside = max(0.0, (target_price - current_price) - (0.004 * current_price))
  net_downside = (current_price - stop_price) + (0.004 * current_price)
  rr_ratio = round(net_upside / net_downside, 2) if net_downside > 0 else 1.0

  dist_to_support = round(((current_price - support_level) / support_level) * 100, 1) if support_level > 0 else 0.0

  if dist_to_support <= 3.8:
    entry_min = support_level
    entry_max = round(min(support_level * 1.025, current_price * 1.005), -2)
    tplus_entry = f'{entry_min:,.0f} - {entry_max:,.0f} đ'
  else:
    entry_min = support_level
    entry_max = round(support_level + 0.5 * atr14, -2)
    tplus_entry = f'Chờ test lại {entry_min:,.0f} - {entry_max:,.0f} đ'

  multi_tf = calculate_multi_timeframe_confluence(ticker, current_price, ma20)
  w_levels = calculate_weekly_levels(ticker, current_price)

  ex_clean = (exchange or 'HOSE').upper()
  floor_cap = 15.0 if 'HOSE' in ex_clean else (10.5 if 'HNX' in ex_clean else 7.2)
  regime = regime or {}
  regime_name = regime.get('regime', 'NEUTRAL')
  regime_coef = regime.get('coefficient', 0.75)
  risk_budget_pct = round(T_PLUS_RISK_BUDGET_PCT * regime_coef, 2)
  nominal_nav_pct = round((risk_budget_pct / downside) * 100.0, 1) if downside > 0 else 0.0
  max_nav_pct = round(min(floor_cap, SINGLE_STOCK_NAV_CAP_PCT, nominal_nav_pct), 1)
  pilot_nav_pct = round(max_nav_pct * 0.35, 1)
  pyramid_nav_pct = round(max_nav_pct * 0.65, 1)

  position_sizing = {
      'maxNavPct': max_nav_pct,
      'pilotNavPct': pilot_nav_pct,
      'pyramidNavPct': pyramid_nav_pct,
      'riskBudgetPct': risk_budget_pct,
      'baseRiskBudgetPct': T_PLUS_RISK_BUDGET_PCT,
      'regime': regime_name,
      'regimeCoefficient': regime_coef,
      'downsideRiskPct': downside,
      'floorCap': floor_cap,
      'exchange': ex_clean,
      'guide': (
          f'Regime {regime_name}: ngân sách rủi ro {T_PLUS_RISK_BUDGET_PCT}% x hệ số {regime_coef} = {risk_budget_pct}% NAV mỗi lệnh. '
          f'Giải ngân tối đa {max_nav_pct}% NAV (Sàn {ex_clean} trần kẹt sàn {floor_cap}% NAV). '
          f'Thăm dò: {pilot_nav_pct}% NAV quanh nền, Gia tăng: {pyramid_nav_pct}% NAV khi break cản {resistance_level:,.0f} đ. '
          f'Cắt lỗ tại {stop_price:,.0f} đ (-{downside}% deal, tổn thất tối đa ~{risk_budget_pct}% tổng NAV; '
          'lưu ý hàng mới mua chỉ bán được từ chiều T+2).'
      ),
  }

  ta_score = 40
  if current_price >= ma20: ta_score += 20
  if current_price >= ma50: ta_score += 10
  if 50 <= rsi <= 65: ta_score += 15
  elif 40 <= rsi < 50: ta_score += 8
  elif rsi > 70: ta_score -= 15

  if vol_ratio >= 1.5:
    ta_score += 15 if day_change_pct > 0 else (-10 if day_change_pct < 0 else 0)
  elif vol_ratio >= 1.1:
    ta_score += 8 if day_change_pct > 0 else (-5 if day_change_pct < 0 else 0)

  if buy_ratio >= 55: ta_score += 10
  elif buy_ratio < 45: ta_score -= 5

  rs_score = rs_info.get('rsScore', 50)
  if rs_score >= 80: ta_score += 15
  elif rs_score >= 65: ta_score += 8
  elif rs_score < 40: ta_score -= 10

  if multi_tf.get('isAlignedBullish'): ta_score += 8
  elif multi_tf.get('isSevereDowntrend'): ta_score -= 10

  ta_score = max(10, min(98, ta_score))

  if rsi > 70 or (rsi > 68 and foreign_net < -50000):
    tplus_decision = 'QUÁ MUA - CHỜ RUNG LẮC'
    tplus_type = DECISION_TYPE_DANGER
    tplus_reason = (
        f'RSI chạm {rsi} (vùng quá mua), giá đang ở vùng rủi ro điều chỉnh T+ cao. '
        f"Khối ngoại {'bán ròng ' + f'{abs(foreign_net):,.0f} cp' if foreign_net < 0 else 'đã đẩy giá cao'}. Tuyệt đối không mua đuổi."
    )
  elif current_price < ma20 or multi_tf.get('isSevereDowntrend'):
    tplus_decision = 'DƯỚI MA20 - CHỜ TẠO NỀN'
    tplus_type = DECISION_TYPE_DANGER
    tplus_reason = (
        f'Giá đóng cửa ({current_price:,.0f} đ) nằm dưới MA20 ({ma20:,.0f} đ), phe bán chiếm {100-buy_ratio:.1f}%. '
        'Cần chờ dòng tiền lớn tạo nền tích lũy trước khi mở vị thế.'
    )
  elif dist_to_support > 3.8:
    tplus_decision = 'XA NỀN - CHỜ RETEST'
    tplus_type = DECISION_TYPE_WARNING
    tplus_reason = (
        f'Giá hiện tại đã tăng cách ngưỡng hỗ trợ S1 {dist_to_support:.1f}% (>3.5%). '
        f'Vị thế treo leo bất lợi, ưu tiên chờ nhịp rung lắc test lại nền {support_level:,.0f} đ.'
    )
  elif rr_ratio < 2.0:
    tplus_decision = f'R:R KÉM (1:{rr_ratio}) - KHÔNG ĐẠT CHUẨN'
    tplus_type = DECISION_TYPE_WARNING
    tplus_reason = (
        f'Tỷ lệ Lợi nhuận/Rủi ro ròng chỉ đạt 1:{rr_ratio} (< 2.0 sau thuế phí 0.4%). '
        f'Biên lãi kỳ vọng (+{upside}%) không đủ bù đắp rủi ro cắt lỗ (-{downside}%). Không mở vị thế mua T+.'
    )
  elif ta_score >= 75 and vol_ratio >= 1.25 and day_change_pct > 0 and buy_ratio >= 50 and rs_score >= 60 and rr_ratio >= 2.0:
    tplus_decision = 'MUA T+ (DÒNG TIỀN XÁC NHẬN)'
    tplus_type = DECISION_TYPE_SUCCESS
    tplus_reason = (
        f"Giá giữ vững trên MA20 ({ma20:,.0f} đ), tăng {day_change_pct:+.2f}% kèm KL x{vol_ratio} TB20{' (ước tính cả phiên)' if is_partial else ''}, RS {rs_score}/99. "
        f'Lực mua chủ động chiếm {buy_ratio}%, Net R:R đạt chuẩn 1:{rr_ratio}. Giải ngân theo tỷ trọng đề xuất, tuân thủ mốc cắt lỗ.'
    )
  elif current_price >= ma20 and 42 <= rsi <= 68 and dist_to_support <= 3.8 and rr_ratio >= 2.0:
    tplus_decision = 'MUA TÍCH LŨY T+ (ĐẠT CHUẨN)'
    tplus_type = DECISION_TYPE_SUCCESS
    tplus_reason = (
        f'Nến duy trì sát nền MA20 ({ma20:,.0f} đ), cách hỗ trợ {dist_to_support:.1f}%, RSI lành mạnh ({rsi}), '
        f'Net R:R đạt chuẩn 1:{rr_ratio}. Gom trong các nhịp rung lắc quanh nền.'
    )
  elif rsi < 35:
    tplus_decision = 'BẮT ĐÁY NẢY KỸ THUẬT (RỦI RO CAO)'
    tplus_type = DECISION_TYPE_WARNING
    tplus_reason = (
        f'RSI vùng quá bán ({rsi}), sát hỗ trợ ({support_level:,.0f} đ). '
        'Chỉ dành cho nhà đầu tư chấp nhận rủi ro cao đánh nhịp hồi phục kiểm định MA20 (hàng về chiều T+2).'
    )
  else:
    tplus_decision = 'QUAN SÁT THEO DÕI'
    tplus_type = DECISION_TYPE_WARNING
    tplus_reason = (
        f'Cổ phiếu đang giằng co chưa hình thành setup T+ đạt chuẩn (RSI {rsi}, Net R:R 1:{rr_ratio}). '
        'Kiên nhẫn chờ tín hiệu dòng tiền rõ nét hơn.'
    )

  regime_summary = regime.get('summary', '')
  if tplus_type == DECISION_TYPE_SUCCESS and regime_name == 'NO_NEW_RISK':
    tplus_decision = 'TẠM NGỪNG MUA (THỊ TRƯỜNG RỦI RO CAO)'
    tplus_type = DECISION_TYPE_DANGER
    tplus_reason = f'Setup kỹ thuật của mã đạt chuẩn nhưng {regime_summary}. Tuyệt đối không mở vị thế mới cho đến khi chế độ thị trường cải thiện.'
  elif tplus_type == DECISION_TYPE_SUCCESS and regime_name == 'DEFENSIVE':
    tplus_decision = 'CHỜ - THỊ TRƯỜNG PHÒNG THỦ'
    tplus_type = DECISION_TYPE_WARNING
    tplus_reason = (
        f'Setup kỹ thuật của mã đạt chuẩn nhưng {regime_summary}. '
        'Chỉ xét mua tỷ trọng nhỏ nếu mã thuộc ngành dẫn dắt có xác nhận; mặc định chờ.'
    )

  sector = fundamental_info.get('sector', '') if fundamental_info else ''
  mid_term_plan = calculate_fundamental_valuation(
      fundamental_info, current_price, sector, w_levels, s2_support, multi_tf=multi_tf
  )
  if mid_term_plan.get('type') == 'success' and regime_name in ('DEFENSIVE', 'NO_NEW_RISK'):
    regime_vi = 'RỦI RO CAO' if regime_name == 'NO_NEW_RISK' else 'PHÒNG THỦ'
    mid_term_plan['decision'] = f'CHỜ - THỊ TRƯỜNG {regime_vi}'
    mid_term_plan['type'] = DECISION_TYPE_WARNING
    mid_term_plan['reason'] = (
        f"{mid_term_plan.get('reason', '')} Tuy nhiên {regime_summary}: chưa giải ngân mới; "
        'đưa mã vào danh sách theo dõi, gom khi thị trường phục hồi về mức trung lập trở lên.'
    )
  elif regime_name in ('DEFENSIVE', 'NO_NEW_RISK'):
    mid_term_plan['reason'] = f"{mid_term_plan.get('reason', '')} Lưu ý: {regime_summary}."

  fa_score = fundamental_info.get('faScore', 0) if fundamental_info else 0
  is_audited = fundamental_info.get('isAudited', False) if fundamental_info else False
  if is_audited and fa_score > 0:
    total_score = round(ta_score * 0.55 + fa_score * 0.45)
  else:
    total_score = ta_score

  if ta_score >= 75 and fa_score >= 70:
    overall_status = '🌟 CỔ PHIẾU HOÀN HẢO: FA xuất sắc & Dòng tiền T+ bùng nổ'
    overall_color = STATUS_COLOR_PERFECT
  elif ta_score >= 70:
    overall_status = '⚡ DÒNG TIỀN T+ MẠNH: Ưu tiên lướt sóng ngắn hạn'
    overall_color = STATUS_COLOR_MOMENTUM
  elif fa_score >= 75:
    overall_status = '💎 DOANH NGHIỆP GIÁ TRỊ: Thích hợp gom tích sản trung hạn'
    overall_color = STATUS_COLOR_VALUE
  elif ta_score < 45 and (fa_score < 50 and is_audited):
    overall_status = '⚠️ CẢNH BÁO RỦI RO: Cả kỹ thuật và cơ bản đều suy yếu'
    overall_color = STATUS_COLOR_RISK
  else:
    overall_status = '⏳ TRẠNG THÁI TRUNG TÍNH: Tích lũy chờ đợi tín hiệu mới'
    overall_color = STATUS_COLOR_NEUTRAL

  return {
      'rsi': rsi,
      'ema9': ema9,
      'ema21': ema21,
      'rsiDivergence': rsi_div_info,
      'ma20': ma20,
      'ma50': ma50,
      'atr14': atr14,
      'volMa20': vol_ma20,
      'volRatio': vol_ratio,
      'volSignal': vol_signal,
      'volColor': vol_color,
      'volProjected': is_partial,
      'dayChangePct': day_change_pct,
      'isPartialSession': is_partial,
      'buyRatio': buy_ratio,
      'buyActive': buy_active,
      'sellActive': sell_active,
      'support': support_level,
      'support2': s2_support,
      'resistance': resistance_level,
      'resistance2': r2_target,
      'upside': upside,
      'upside2': upside2,
      'downside': downside,
      'rrRatio': rr_ratio,
      'taScore': ta_score,
      'totalScore': total_score,
      'overallStatus': overall_status,
      'overallColor': overall_color,
      'rs': rs_info,
      'multiTimeframe': multi_tf,
      'weeklyLevels': w_levels,
      'positionSizing': position_sizing,
      'positionHolding': position_holding,
      'supertrend': supertrend_info,
      'tPlus': {
          'decision': tplus_decision,
          'type': tplus_type,
          'reason': tplus_reason,
          'entry': tplus_entry,
          'entryMin': entry_min,
          'entryMax': entry_max,
          'target': f'{target_price:,.0f} (+{upside}%)',
          'target2': f'{r2_target:,.0f} (+{upside2}%)',
          'stop': f'{stop_price:,.0f} (-{downside}%)',
          'stopPrice': stop_price,
          'targetPrice': target_price,
          'rrRatio': rr_ratio,
          'distSupportPct': dist_to_support,
          'isEligible': tplus_type == DECISION_TYPE_SUCCESS,
      },
      'midTerm': mid_term_plan,
      'regime': regime,
  }
