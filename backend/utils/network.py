"""
Stock RT - Tiện ích Kết nối Mạng & Rate Limiter
"""
import json
import threading
import time
import urllib.request
from backend.constants.config import HEADERS, VNSTOCK_CALLS_PER_MINUTE

_VNSTOCK_CALL_TIMES = []
_VNSTOCK_LOCK = threading.Lock()

def fetch_json(url, headers=None, timeout=5):
  """Thực hiện HTTP GET và parse JSON an toàn."""
  req = urllib.request.Request(url, headers=headers or HEADERS)
  with urllib.request.urlopen(req, timeout=timeout) as res:
    return json.loads(res.read().decode('utf-8'))

def vnstock_call(fn, *args, **kwargs):
  """
  Gọi vnstock an toàn: tự giới hạn tần suất và chặn SystemExit (vnai gọi sys.exit khi vượt hạn mức).
  Bị giới hạn hoặc lỗi -> trả về None để phía gọi hiển thị 'Dữ liệu chưa ghi nhận' thay vì làm sập server.
  """
  with _VNSTOCK_LOCK:
    now = time.time()
    _VNSTOCK_CALL_TIMES[:] = [t for t in _VNSTOCK_CALL_TIMES if now - t < 60]
    if len(_VNSTOCK_CALL_TIMES) >= VNSTOCK_CALLS_PER_MINUTE:
      print(f'Bỏ qua lời gọi vnstock {getattr(fn, "__name__", fn)}: đạt giới hạn {VNSTOCK_CALLS_PER_MINUTE} request/phút')
      return None
    _VNSTOCK_CALL_TIMES.append(now)
  try:
    return fn(*args, **kwargs)
  except SystemExit as e:
    print('vnstock vượt hạn mức API (đã chặn SystemExit):', str(e)[:120])
  except Exception as e:
    print(f'Lỗi gọi vnstock {getattr(fn, "__name__", fn)}:', str(e)[:120])
  return None
