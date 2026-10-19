"""
Stock RT - Tiện ích Thời gian & Phiên giao dịch Chứng khoán Việt Nam
"""
import time

VN_UTC_OFFSET_SEC = 7 * 3600
# Thời gian khớp lệnh HOSE/HNX: 9:00-11:30 (150 phút) + 13:00-14:45 gồm ATC (105 phút)
TRADING_MINUTES_PER_SESSION = 255
SESSION_CLOSE_MINUTE = 14 * 60 + 45

def vn_date(ts):
  """Chuyển timestamp thành chuỗi ngày 'YYYY-MM-DD' theo múi giờ Việt Nam (UTC+7)."""
  return time.strftime('%Y-%m-%d', time.gmtime(ts + VN_UTC_OFFSET_SEC))

def vn_now():
  """Lấy thời gian struct_time hiện tại theo giờ Việt Nam."""
  return time.gmtime(time.time() + VN_UTC_OFFSET_SEC)

def is_trading_day():
  """Kiểm tra hôm nay có phải ngày giao dịch (thứ 2 đến thứ 6) hay không."""
  now_vn = vn_now()
  return now_vn.tm_wday < 5

def is_trading_hours():
  """Kiểm tra thời điểm hiện tại có đang trong phiên giao dịch khớp lệnh hay không."""
  now_vn = vn_now()
  if now_vn.tm_wday >= 5:
    return False
  minute = now_vn.tm_hour * 60 + now_vn.tm_min
  # Sáng: 9:00 - 11:30 (540 - 690) | Chiều: 13:00 - 14:45 (780 - 885)
  return (540 <= minute <= 690) or (780 <= minute <= 885)

def trading_minutes_elapsed(minute_of_day):
  """Tính số phút giao dịch đã trôi qua trong ngày."""
  morning = min(max(minute_of_day - 9 * 60, 0), 150)
  afternoon = min(max(minute_of_day - 13 * 60, 0), 105)
  return morning + afternoon
