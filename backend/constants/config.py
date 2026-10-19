"""
Stock RT - Hệ thống Cấu hình & Tham số Môi trường (System Configuration)
"""
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT_DIR = os.path.dirname(BACKEND_DIR)
DATA_DIR = os.path.join(ROOT_DIR, 'data')
DB_PATH = os.path.join(DATA_DIR, 'fundamentals.db')

def get_configured_port(default_port=8000):
  """Lấy cổng mạng (PORT) từ tham số dòng lệnh hoặc biến môi trường PORT (mặc định: 8000)."""
  if len(sys.argv) > 1 and sys.argv[1].isdigit():
    return int(sys.argv[1])
  if '--port' in sys.argv:
    try:
      idx = sys.argv.index('--port')
      return int(sys.argv[idx + 1])
    except (IndexError, ValueError):
      pass
  env_port = os.environ.get('PORT')
  if env_port and env_port.isdigit():
    return int(env_port)
  return default_port

PORT = get_configured_port(8000)

# HTTP Request Headers chuẩn
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        ' (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json, text/plain, */*',
}

SSI_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        ' (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Origin': 'https://iboard.ssi.com.vn',
    'Referer': 'https://iboard.ssi.com.vn/',
}

BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        ' (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
}

# API Rate Limits & Timeouts
VNSTOCK_CALLS_PER_MINUTE = 40
DEFAULT_TIMEOUT = 5

# Cache TTL (giây)
SSI_CACHE_TTL = 45
REGIME_CACHE_TTL = 120
FUNDAMENTAL_CACHE_TTL = 86400 * 30  # 30 ngày

# Thông số Kỹ thuật & Biểu đồ
DAILY_HISTORY_DAYS = 420
VN_UTC_OFFSET_SEC = 7 * 3600

# Dải định giá BCTC 12 quý (3 năm)
VALUATION_WINDOW_QUARTERS = 12
VALUATION_MIN_QUARTERS = 8
VCI_HISTORY_KEEP_QUARTERS = 20

# Quản lý rủi ro & Định lượng VSR
T_PLUS_RISK_BUDGET_PCT = 1.0
SINGLE_STOCK_NAV_CAP_PCT = 25.0
BREADTH_UNIVERSE_SIZE = 200
BREADTH_AD_UNIVERSE_SIZE = 100
BREADTH_CANDIDATE_SIZE = 300
BREADTH_HISTORY_DAYS = 50
BREADTH_FIRST_LOAD_WAIT_SEC = 20

REGIME_LEVELS = [
    # (điểm tối thiểu, tên, hệ số risk budget)
    (4, 'RISK_ON', 1.0),
    (3, 'NEUTRAL', 0.75),
    (2, 'DEFENSIVE', 0.5),
    (0, 'NO_NEW_RISK', 0.0),
]

# Cấu hình mapping trường VCI
_VCI_RATIO_FIELDS = {
    'pe_ratio': 'pe', 'pb_ratio': 'pb', 'ps_ratio': 'ps', 'roe': 'roe',
    'gross_margin': 'grossMargin', 'net_margin': 'netMargin',
    'debtPerEquity': 'borrowDE', 'market_cap': 'marketCap',
    'outstanding_shares': 'shares', 'npl': 'npl',
    'loan_loss_reserves_to_npls': 'nplCoverage', 'casa_ratio': 'casa', 'car': 'car',
    'net_interest_margin': 'nim',
}

_VCI_BS_FIELDS = {
    'cash_and_cash_equivalents': 'cash',
    'short_term_investments': 'shortInvestments',
    'short_term_borrowings': 'shortBorrowings',
    'long_term_borrowings': 'longBorrowings',
    'owners_equity': 'equity',
}

_VCI_CF_FIELDS = {
    'net_cash_inflows_outflows_from_operating_activities': 'cfo',
}
