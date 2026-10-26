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
    time_val = ts if is_intraday else vn_date(ts)
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
  session_ts = int(session_start / 1000.0) if session_start else int(time.time())

  last_date = vn_date(t_list[-1]) if t_list else None
  if last_date == today:
    opens[-1], highs[-1], lows[-1], closes[-1] = bar_open, bar_high, bar_low, price
    volumes[-1] = max(volumes[-1], bar_vol)
  elif last_date is None or last_date < today:
    if t_list is not None and isinstance(t_list, list):
      t_list.append(session_ts)
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


def merge_live_candle_to_chart_data(chart_data, ssi_item, resolution='1D'):
  """
  Ghép cây nến realtime tại thời điểm search từ SSI vào chart_data (dict t, o, h, l, c, v).
  - Tự động nhận diện scale (nghìn đồng vs đồng) để giá nến đồng nhất tuyệt đối.
  - Chống trùng lặp: nếu nến cuối đã là ngày hôm nay thì cập nhật in-place, nếu là ngày cũ thì nối thêm.
  - Đảm bảo hiển thị đầy đủ nến tới thời điểm search trên biểu đồ TradingView Lightweight Charts.
  """
  if not chart_data or not isinstance(chart_data, dict):
    return chart_data

  c_list = chart_data.get('c', [])
  t_list = chart_data.get('t', [])
  o_list = chart_data.get('o', [])
  h_list = chart_data.get('h', [])
  l_list = chart_data.get('l', [])
  v_list = chart_data.get('v', [])

  if not c_list or not t_list:
    return chart_data
  if not ssi_item or not isinstance(ssi_item, dict):
    return chart_data

  # Lấy giá khớp lệnh realtime (hoặc giá dự kiến ATO / giá tham chiếu nếu chưa khớp)
  price = ssi_item.get('matchedPrice') or ssi_item.get('expectedMatchedPrice') or 0
  if price <= 0:
    return chart_data

  session_start = ssi_item.get('sessionStart')
  now_vn = time.gmtime(time.time() + VN_UTC_OFFSET_SEC)
  today = time.strftime('%Y-%m-%d', now_vn)
  minute_of_day = now_vn.tm_hour * 60 + now_vn.tm_min

  # Kiểm tra tính hợp lệ của phiên hôm nay:
  # Phải là phiên có sessionStart trùng ngày hôm nay và sau 09:00 sáng
  if not session_start or vn_date(session_start / 1000.0) != today or minute_of_day < 9 * 60:
    return chart_data

  # Xác định tỷ lệ giá của chart_data (Entrade thường chia 1000, SSI là full VND)
  scale_factor = 1000.0 if c_list[-1] < 1000 else 1.0

  bar_open = (ssi_item.get('openPrice') or price) / scale_factor
  raw_high = max(ssi_item.get('highest') or price, price)
  raw_low = min(ssi_item.get('lowest') or price, price) if (ssi_item.get('lowest') or 0) > 0 else price
  bar_high = raw_high / scale_factor
  bar_low = raw_low / scale_factor
  bar_close = price / scale_factor
  bar_vol = int(ssi_item.get('stockVol') or 0)
  session_ts = int(session_start / 1000.0) if session_start else int(time.time())

  if resolution == '1D':
    last_date = vn_date(t_list[-1]) if t_list else None
    if last_date == today:
      # Nến hôm nay đã có sẵn trong chart_data -> Cập nhật in-place số liệu SSI mới nhất
      o_list[-1] = bar_open
      h_list[-1] = max(h_list[-1], bar_high)
      l_list[-1] = min(l_list[-1], bar_low) if l_list[-1] > 0 else bar_low
      c_list[-1] = bar_close
      v_list[-1] = max(v_list[-1], bar_vol)
    elif last_date is None or last_date < today:
      # Nối thêm nến hôm nay vào cuối chuỗi
      t_list.append(session_ts)
      o_list.append(bar_open)
      h_list.append(bar_high)
      l_list.append(bar_low)
      c_list.append(bar_close)
      v_list.append(bar_vol)

  elif resolution == '1W':
    import datetime
    today_dt = datetime.date(now_vn.tm_year, now_vn.tm_mon, now_vn.tm_mday)
    monday = today_dt - datetime.timedelta(days=today_dt.weekday())
    monday_str = monday.strftime('%Y-%m-%d')
    last_date = vn_date(t_list[-1]) if t_list else None
    if last_date == monday_str:
      h_list[-1] = max(h_list[-1], bar_high)
      l_list[-1] = min(l_list[-1], bar_low) if l_list[-1] > 0 else bar_low
      c_list[-1] = bar_close
      v_list[-1] = max(v_list[-1], bar_vol)
    elif last_date is None or last_date < monday_str:
      monday_ts = int(time.mktime((monday.year, monday.month, monday.day, 9, 0, 0, 0, 0, 0))) - VN_UTC_OFFSET_SEC
      t_list.append(monday_ts)
      o_list.append(bar_open)
      h_list.append(bar_high)
      l_list.append(bar_low)
      c_list.append(bar_close)
      v_list.append(bar_vol)

  elif resolution in ['1H', '30', '15', '5']:
    # Với intraday, cập nhật tick mới nhất vào nến cuối
    if c_list:
      c_list[-1] = bar_close
      h_list[-1] = max(h_list[-1], bar_close)
      l_list[-1] = min(l_list[-1], bar_close) if l_list[-1] > 0 else bar_close
      v_list[-1] = max(v_list[-1], bar_vol)

  return chart_data
