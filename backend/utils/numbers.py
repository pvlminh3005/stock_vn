"""
Stock RT - Tiện ích Xử lý Số học & Thống kê
"""
import math

def safe_num(val, default=0.0):
  """Chuyển đổi giá trị sang float an toàn, tránh NaN và None."""
  try:
    v = float(val)
    return default if (math.isnan(v) or v is None) else v
  except (ValueError, TypeError):
    return default

def percentile(values, q):
  """Tính phân vị percentile theo phương pháp nội suy tuyến tính."""
  vals = sorted([v for v in values if v is not None and not math.isnan(v)])
  if not vals:
    return None
  pos = (len(vals) - 1) * q
  lo, hi = int(pos), min(int(pos) + 1, len(vals) - 1)
  return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)

def round_price(price, step=100):
  """Làm tròn bước giá cổ phiếu."""
  if price <= 0:
    return 0.0
  return round(price / step) * step
