"""
Stock RT - Tiện ích Kết nối Mạng
"""
import json
import urllib.request
from backend.constants.config import HEADERS

VIETCAP_TRADING_HEADERS = {
    **HEADERS,
    'Origin': 'https://trading.vietcap.com.vn',
    'Referer': 'https://trading.vietcap.com.vn/',
}

VIETCAP_IQ_HEADERS = {
    **HEADERS,
    'Origin': 'https://iq.vietcap.com.vn',
    'Referer': 'https://iq.vietcap.com.vn/',
}


def fetch_json(url, headers=None, timeout=5):
  """Thực hiện HTTP GET và parse JSON an toàn."""
  req = urllib.request.Request(url, headers=headers or HEADERS)
  with urllib.request.urlopen(req, timeout=timeout) as res:
    return json.loads(res.read().decode('utf-8'))
