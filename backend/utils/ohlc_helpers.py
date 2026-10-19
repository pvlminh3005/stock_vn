"""
Stock RT - Tiện ích Định dạng Nến & Phân tích Kỳ BCTC
"""
import re
import time
from backend.utils.time_utils import (
    VN_UTC_OFFSET_SEC,
    TRADING_MINUTES_PER_SESSION,
    SESSION_CLOSE_MINUTE,
    vn_date,
    trading_minutes_elapsed,
)

def format_candles(chart_data, resolution='1D'):
  """Chuẩn hóa dữ liệu nến cho TradingView Lightweight Charts."""
  t_list = chart_data.get('t', [])
  o_list = chart_data.get('o', [])
  h_list = chart_data.get('h', [])
  l_list = chart_data.get('l', [])
  c_list = chart_data.get('c', [])
  v_list = chart_data.get('v', [])
  if not c_list:
    return []
  scale = 1000 if c_list[-1] < 1000 else 1
  is_intraday = resolution in ['1H', '30', '15', '5']
  candles = []
  for i in range(len(t_list)):
    ts = t_list[i]
    time_val = ts if is_intraday else time.strftime('%Y-%m-%d', time.localtime(ts))
    candles.append({
        'time': time_val,
        'open': o_list[i] * scale,
        'high': h_list[i] * scale,
        'low': l_list[i] * scale,
        'close': c_list[i] * scale,
        'volume': v_list[i] if i < len(v_list) else 0,
    })
  return candles

def parse_quarter_key(col_name):
  """Parse nhãn quý dạng 'YYYY-Qn' thành tuple (year, quarter)."""
  try:
    parts = str(col_name).split('-Q')
    year = int(parts[0])
    quarter = int(parts[1].split('_')[0])
    return (year, quarter)
  except (IndexError, ValueError, TypeError):
    return (0, 0)

def period_key(period):
  """Regex trích xuất (năm, quý) từ chuỗi kỳ BCTC."""
  m = re.match(r'^(\d{4})-Q([1-4])', str(period or ''))
  return (int(m.group(1)), int(m.group(2))) if m else None

def expected_latest_report_period(now_ts=None):
  """Kỳ BCTC quý mới nhất đã quá hạn công bố (45 ngày sau khi kết thúc quý, áp dụng cho BCTC hợp nhất)."""
  now_ts = now_ts or time.time()
  today = time.gmtime(now_ts + VN_UTC_OFFSET_SEC)
  year, quarter = today.tm_year, (today.tm_mon - 1) // 3 + 1
  for _ in range(8):
    quarter -= 1
    if quarter == 0:
      year, quarter = year - 1, 4
    end_month = quarter * 3
    next_year, next_month = (year + 1, 1) if end_month == 12 else (year, end_month + 1)
    quarter_end = time.mktime((next_year, next_month, 1, 0, 0, 0, 0, 0, -1)) - 86400
    if quarter_end + 45 * 86400 <= time.mktime(today):
      return (year, quarter)
  return None

def merge_live_session_bar(t_list, opens, highs, lows, closes, volumes, ssi_item):
  """
  Ghép nến phiên hôm nay từ snapshot SSI vào chuỗi nến ngày (sửa trực tiếp các list).
  - Entrade thường chưa có nến hôm nay trong phiên -> nối thêm nến mới, KHÔNG ghi đè giá đóng cửa hôm qua.
  - Nếu Entrade đã có nến hôm nay -> cập nhật bằng số liệu SSI mới nhất.
  Trả về (has_live_bar, is_partial, elapsed_fraction):
    is_partial = phiên chưa kết thúc (trước 14:45), nến và khối lượng hôm nay chưa hoàn chỉnh.
  """
  if not ssi_item or ssi_item.get('matchedPrice', 0) <= 0 or not closes:
    return False, False, 1.0
  session_start = ssi_item.get('sessionStart')
  now_vn = time.gmtime(time.time() + VN_UTC_OFFSET_SEC)
  today = time.strftime('%Y-%m-%d', now_vn)
  minute_of_day = now_vn.tm_hour * 60 + now_vn.tm_min
  # Snapshot SSI không thuộc phiên hôm nay (cuối tuần, ngày nghỉ) hoặc chưa mở cửa -> không ghép
  if not session_start or vn_date(session_start / 1000.0) != today or minute_of_day < 9 * 60:
    return False, False, 1.0

  price = ssi_item['matchedPrice']
  bar_open = ssi_item.get('openPrice') or price
  bar_high = max(ssi_item.get('highest') or price, price)
  bar_low = min(ssi_item.get('lowest') or price, price)
  bar_vol = ssi_item.get('stockVol') or 0

  last_date = vn_date(t_list[-1]) if t_list else None
  if last_date == today:
    opens[-1], highs[-1], lows[-1], closes[-1] = bar_open, bar_high, bar_low, price
    volumes[-1] = max(volumes[-1], bar_vol)
  elif last_date is None or last_date < today:
    opens.append(bar_open)
    highs.append(bar_high)
    lows.append(bar_low)
    closes.append(price)
    volumes.append(bar_vol)
  else:
    return False, False, 1.0

  is_partial = now_vn.tm_wday < 5 and minute_of_day < SESSION_CLOSE_MINUTE
  elapsed = trading_minutes_elapsed(minute_of_day) / float(TRADING_MINUTES_PER_SESSION)
  # Tránh phóng đại khi mới mở cửa: coi tối thiểu 30 phút đã trôi qua
  elapsed = max(30.0 / TRADING_MINUTES_PER_SESSION, min(1.0, elapsed)) if is_partial else 1.0
  return True, is_partial, elapsed
