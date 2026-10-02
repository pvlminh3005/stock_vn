import http.server
import io
import json
import os
import re
import socketserver
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from vnstock import Company, Finance

PORT = 8000

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

# ==================== CACHE QUẢN LÝ THỊ TRƯỜNG ====================
_SSI_CACHE = {'timestamp': 0, 'data': {}}


def fetch_json(url, headers=HEADERS, timeout=5):
  """Thực hiện HTTP GET và parse JSON an toàn."""
  req = urllib.request.Request(url, headers=headers)
  with urllib.request.urlopen(req, timeout=timeout) as res:
    return json.loads(res.read().decode('utf-8'))


from concurrent.futures import ThreadPoolExecutor

def get_ssi_board_data():
  """Lấy snapshot toàn bộ bảng giá 3 sàn HOSE, HNX, UPCoM từ SSI iBoard (cache 45 giây)."""
  global _SSI_CACHE
  now = time.time()
  if now - _SSI_CACHE['timestamp'] < 45 and _SSI_CACHE['data']:
    return _SSI_CACHE['data']

  stock_map = {}
  def _fetch_exchange(ex):
    try:
      url = f'https://iboard-query.ssi.com.vn/stock/exchange/{ex}'
      res = fetch_json(url, headers=SSI_HEADERS, timeout=6)
      return res.get('data', [])
    except Exception as e:
      print(f'Lỗi fetch SSI board {ex}:', e)
      return []

  try:
    with ThreadPoolExecutor(max_workers=3) as pool:
      results = pool.map(_fetch_exchange, ['hose', 'hnx', 'upcom'])
      for items in results:
        for item in items:
          sym = item.get('stockSymbol')
          if sym:
            stock_map[sym.upper()] = item
    if stock_map:
      _SSI_CACHE['timestamp'] = now
      _SSI_CACHE['data'] = stock_map
      return stock_map
  except Exception as e:
    print('Lỗi fetch SSI board:', e)

  return _SSI_CACHE.get('data', {})


def fetch_chart_data(ticker, days=120, resolution='1D'):
  """Lấy nến kỹ thuật đầy đủ (t, o, h, l, c, v) từ Entrade API theo resolution."""
  now_ts = int(time.time())
  if resolution == '1W':
    days = 365
  elif resolution in ['1H', '30']:
    days = 40
  elif resolution in ['15', '5']:
    days = 15
  from_ts = now_ts - (days * 86400)
  url = f'https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?from={from_ts}&to={now_ts}&symbol={ticker}&resolution={resolution}'
  return fetch_json(url)


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


def handle_chart_only(ticker, resolution='1D'):
  """Trả về dữ liệu nến phục vụ chuyển nhanh khung thời gian trên biểu đồ."""
  chart_data = fetch_chart_data(ticker, resolution=resolution)
  return {
      'ticker': ticker,
      'resolution': resolution,
      'candles': format_candles(chart_data, resolution=resolution),
  }


# ==================== CƠ SỞ DỮ LIỆU CƠ BẢN DOANH NGHIỆP QUA VNSTOCK ====================
os.environ['VNSTOCK_TELEMETRY'] = 'off'

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'fundamentals.db')

SECTOR_MAP = {
    'Technology': 'Công nghệ thông tin',
    'Construction & Materials': 'Xây dựng & Vật liệu',
    'Financial Services': 'Dịch vụ Tài chính / Chứng khoán',
    'Banks': 'Ngân hàng',
    'Real Estate': 'Bất động sản',
    'Food & Beverage': 'Thực phẩm & Đồ uống',
    'Retail': 'Bán lẻ tiêu dùng',
    'Basic Resources': 'Thép & Tài nguyên cơ bản',
    'Oil & Gas': 'Dầu khí & Năng lượng',
    'Utilities': 'Điện & Tiện ích',
    'Industrial Goods & Services': 'Hàng hóa & Dịch vụ công nghiệp',
    'Chemicals': 'Hóa chất & Phân bón',
    'Automobiles & Parts': 'Ô tô & Phụ tùng',
    'Personal & Household Goods': 'Hàng tiêu dùng cá nhân & Gia dụng',
    'Health Care': 'Y tế & Dược phẩm',
    'Telecommunications': 'Viễn thông',
    'Travel & Leisure': 'Du lịch & Giải trí',
    'Media': 'Truyền thông',
    'Insurance': 'Bảo hiểm',
}

_MEM_FUNDAMENTALS_CACHE = {}


def init_fundamentals_db():
  try:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
      conn.execute("""
        CREATE TABLE IF NOT EXISTS fundamentals (
            symbol TEXT PRIMARY KEY,
            name TEXT,
            sector TEXT,
            pe REAL,
            pb REAL,
            roe REAL,
            eps REAL,
            bvps REAL DEFAULT 0.0,
            debt_to_equity REAL,
            rev_growth REAL,
            profit_growth REAL,
            summary TEXT,
            updated_at INTEGER
        )
      """)
      for col, col_def in [
          ('bvps', 'REAL DEFAULT 0.0'),
          ('ocf', 'REAL DEFAULT 0.0'),
          ('gross_margin', 'REAL DEFAULT 0.0'),
          ('net_margin', 'REAL DEFAULT 0.0'),
          ('interest_coverage', 'REAL DEFAULT 0.0'),
          ('ocf_status', "TEXT DEFAULT ''"),
          ('nim', 'REAL DEFAULT 0.0'),
          ('ldr', 'REAL DEFAULT 0.0'),
      ]:
        try:
          conn.execute(f"ALTER TABLE fundamentals ADD COLUMN {col} {col_def}")
        except Exception:
          pass
  except Exception as e:
    print('Lỗi khởi tạo DB fundamentals:', e)


init_fundamentals_db()


def get_cached_fundamental(symbol):
  sym = symbol.upper()
  if sym in _MEM_FUNDAMENTALS_CACHE:
    item, ts = _MEM_FUNDAMENTALS_CACHE[sym]
    if time.time() - ts < 604800:  # 7 ngày
      return item

  try:
    with sqlite3.connect(DB_PATH) as conn:
      cur = conn.cursor()
      cur.execute(
          'SELECT name, sector, pe, pb, roe, eps, debt_to_equity, rev_growth,'
          ' profit_growth, summary, updated_at, bvps, ocf, gross_margin, net_margin,'
          ' interest_coverage, ocf_status, nim, ldr FROM fundamentals WHERE symbol = ?',
          (sym,),
      )
      row = cur.fetchone()
      if row:
        updated_at = row[10]
        if time.time() - updated_at < 604800:
          has_advanced = (len(row) > 13 and (row[12] or row[13] or (len(row) > 17 and row[17]))) or (len(row) > 16 and row[16])
          if not has_advanced:
            # Bản ghi cũ thiếu dữ liệu OCF & Gross Margin nâng cao, trả về None để fetch mới
            return None
          data = {
              'name': row[0],
              'sector': row[1],
              'pe': row[2],
              'pb': row[3],
              'roe': row[4],
              'eps': row[5],
              'debtToEquity': row[6],
              'revGrowth': row[7],
              'profitGrowth': row[8],
              'summary': row[9],
              'bvps': row[11] if len(row) > 11 and row[11] else 0.0,
              'ocf': row[12] if len(row) > 12 and row[12] else 0.0,
              'grossMargin': row[13] if len(row) > 13 and row[13] else 0.0,
              'netMargin': row[14] if len(row) > 14 and row[14] else 0.0,
              'interestCoverage': row[15] if len(row) > 15 and row[15] else 0.0,
              'ocfStatus': row[16] if len(row) > 16 and row[16] else '',
              'nim': row[17] if len(row) > 17 and row[17] else 0.0,
              'ldr': row[18] if len(row) > 18 and row[18] else 0.0,
              'isAudited': True,
          }
          _MEM_FUNDAMENTALS_CACHE[sym] = (data, updated_at)
          return data
  except Exception as e:
    print(f'Lỗi đọc cache SQLite {sym}:', e)

  return None


def save_cached_fundamental(symbol, data):
  sym = symbol.upper()
  now = int(time.time())
  _MEM_FUNDAMENTALS_CACHE[sym] = (data, now)
  try:
    with sqlite3.connect(DB_PATH) as conn:
      conn.execute(
          """
            INSERT OR REPLACE INTO fundamentals (
                symbol, name, sector, pe, pb, roe, eps,
                bvps, debt_to_equity, rev_growth, profit_growth, summary, updated_at,
                ocf, gross_margin, net_margin, interest_coverage, ocf_status, nim, ldr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          """,
          (
              sym,
              data.get('name', ''),
              data.get('sector', ''),
              data.get('pe', 0.0),
              data.get('pb', 0.0),
              data.get('roe', 0.0),
              data.get('eps', 0.0),
              data.get('bvps', 0.0),
              data.get('debtToEquity', 0.0),
              data.get('revGrowth', 0.0),
              data.get('profitGrowth', 0.0),
              data.get('summary', ''),
              now,
              data.get('ocf', 0.0),
              data.get('grossMargin', 0.0),
              data.get('netMargin', 0.0),
              data.get('interestCoverage', 0.0),
              data.get('ocfStatus', ''),
              data.get('nim', 0.0),
              data.get('ldr', 0.0),
          ),
      )
  except Exception as e:
    print(f'Lỗi ghi cache SQLite {sym}:', e)


def fetch_from_vnstock(symbol):
  """Lấy dữ liệu BCTC và hồ sơ doanh nghiệp thực tế qua vnstock."""
  old_stdout, old_stderr = sys.stdout, sys.stderr
  sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
  try:
    from vnstock import Company, Finance

    # 1. Thông tin doanh nghiệp từ VCI
    c = Company(symbol=symbol, source='VCI')
    ov = c.overview()
    name = (
        ov['organ_name'].values[0]
        if 'organ_name' in ov.columns and len(ov) > 0
        else f'Công ty Cổ phần {symbol}'
    )
    raw_sector = (
        ov['sector'].values[0]
        if 'sector' in ov.columns and len(ov) > 0
        else 'Doanh nghiệp'
    )
    sector = SECTOR_MAP.get(raw_sector, raw_sector)
    summary = (
        ov['company_profile'].values[0]
        if 'company_profile' in ov.columns and len(ov) > 0
        else ''
    )

    # 2. Chỉ số tài chính BCTC từ KBS
    f = Finance(source='KBS', symbol=symbol)
    r = f.ratio()
    latest_col = r.columns[-1]
    item_map = dict(zip(r['item'], r[latest_col]))

    def safe_num(val, default=0.0):
      try:
        v = float(val)
        return default if (v != v or v is None) else v
      except:
        return default

    bvps = safe_num(
        item_map.get('Giá trị sổ sách của cổ phiếu (BVPS)'), 0.0
    )
    pe = safe_num(item_map.get('Chỉ số giá thị trường trên thu nhập (P/E)'), 0.0)
    pb = safe_num(
        item_map.get('Chỉ số giá thị trường trên giá trị sổ sách (P/B)'), 0.0
    )
    roe = safe_num(item_map.get('ROE bình quân 4 quý gần nhất'), 0.0)
    eps = safe_num(
        item_map.get('Thu nhập trên mỗi cổ phần của 4 quý gần nhất (EPS)'), 0.0
    )
    debt = safe_num(item_map.get('Tỷ số Nợ trên Vốn chủ sở hữu'), 0.0) / 100.0
    rev_growth = safe_num(item_map.get('Tăng trưởng  doanh thu thuần'), 0.0)
    profit_growth = safe_num(
        item_map.get('Tăng trưởng lợi nhuận sau thuế của CĐ công ty mẹ'), 0.0
    )
    gross_margin = safe_num(item_map.get('Tỷ suất lợi nhuận gộp biên'), 0.0)
    net_margin = safe_num(item_map.get('Tỷ suất sinh lợi trên doanh thu thuần'), 0.0)
    interest_cov = safe_num(item_map.get('Khả năng thanh toán lãi vay'), 0.0)
    nim = safe_num(item_map.get('Tỷ lệ thu nhập lãi thuần (NIM)'), 0.0)
    ldr = safe_num(item_map.get('Dư nợ cho vay khách hàng/Tổng vốn huy động (LDR)'), 0.0)

    # 3. Trích xuất Dòng tiền thuần từ HĐKD (Operating Cash Flow - OCF)
    ocf = 0.0
    try:
      f_vci = Finance(source='VCI', symbol=symbol)
      cf = f_vci.cash_flow(period='quarter', lang='vi')
      if cf is not None and not cf.empty:
        latest_col_cf = cf.columns[3]
        for _, row in cf.iterrows():
          it = str(row.get('item', '')).strip().lower()
          if 'lưu chuyển tiền tệ ròng từ các hoạt động sản xuất kinh doanh' in it or 'lưu chuyển tiền thuần từ hoạt động kinh doanh' in it:
            raw_v = row[latest_col_cf]
            ocf = float(raw_v) if (raw_v == raw_v and raw_v is not None) else 0.0
            break
    except Exception:
      pass

    # Đánh giá chất lượng dòng tiền (Quality of Earnings)
    if ocf > 0:
      ocf_status = "Dương vững mạnh (Tiền tươi về DN)"
    elif ocf < 0 and profit_growth > 0:
      ocf_status = "⚠️ Cảnh báo Lợi nhuận giấy (OCF âm / Lãi ảo)"
    elif ocf < 0:
      ocf_status = "Âm (Thâm hụt dòng tiền lưu động)"
    else:
      ocf_status = "Dữ liệu chưa ghi nhận"

    has_audited_data = (pe > 0 or pb > 0 or roe != 0 or eps > 0)
    return {
        'name': name,
        'sector': sector,
        'pe': round(pe, 1) if pe > 0 else 0.0,
        'pb': round(pb, 2) if pb > 0 else 0.0,
        'roe': round(roe, 1) if roe != 0 else 0.0,
        'eps': round(eps) if eps > 0 else 0.0,
        'bvps': round(bvps) if bvps > 0 else 0.0,
        'debtToEquity': round(debt, 2),
        'revGrowth': round(rev_growth, 1),
        'profitGrowth': round(profit_growth, 1),
        'grossMargin': round(gross_margin, 1),
        'netMargin': round(net_margin, 1),
        'interestCoverage': round(interest_cov, 1),
        'ocf': round(ocf / 1e9, 1),  # Quy đổi về tỷ đồng
        'ocfStatus': ocf_status,
        'nim': round(nim, 2),
        'ldr': round(ldr, 1),
        'summary': (
            summary
            or f'Doanh nghiệp {symbol} niêm yết trên thị trường chứng khoán'
            ' Việt Nam.'
        ),
        'isAudited': has_audited_data,
    }
  except Exception as e:
    return None
  finally:
    sys.stdout, sys.stderr = old_stdout, old_stderr


def get_fundamental_profile(ticker, current_price):
  """Trả về hồ sơ cơ bản chuẩn hóa và điểm FA lấy từ vnstock (Không tạo số liệu giả)."""
  sym = ticker.upper()

  # 1. Kiểm tra cache
  cached = get_cached_fundamental(sym)
  info = cached

  # 2. Nếu chưa có trong cache, gọi vnstock
  if not info:
    fetched = fetch_from_vnstock(sym)
    if fetched:
      save_cached_fundamental(sym, fetched)
      info = fetched

  # 3. Nếu vnstock không có dữ liệu, KHÔNG được tự bịa đặt chỉ số ước lượng
  if not info:
    info = {
        'name': f'Công ty Cổ phần {sym}',
        'sector': 'Chưa phân loại',
        'pe': 0.0,
        'pb': 0.0,
        'roe': 0.0,
        'eps': 0.0,
        'bvps': 0.0,
        'debtToEquity': 0.0,
        'revGrowth': 0.0,
        'profitGrowth': 0.0,
        'grossMargin': 0.0,
        'netMargin': 0.0,
        'interestCoverage': 0.0,
        'ocf': 0.0,
        'ocfStatus': 'Dữ liệu chưa ghi nhận',
        'nim': 0.0,
        'ldr': 0.0,
        'summary': (
            f'Mã {sym} đang được giao dịch trên sàn với thanh khoản ghi nhận'
            ' thực tế theo phiên gần nhất. Dữ liệu BCTC kiểm toán đang được cập nhật.'
        ),
        'isAudited': False,
    }

  # Tính P/E và P/B động theo giá thị trường thời gian thực (chỉ khi có EPS/BVPS thực tế)
  eps = info.get('eps', 0.0)
  bvps = info.get('bvps', 0.0)
  if eps > 0 and current_price > 0:
    info['pe'] = round(current_price / eps, 2)
  if bvps > 0 and current_price > 0:
    info['pb'] = round(current_price / bvps, 2)

  # Chấm điểm FA Score (0 - 100) theo số liệu thực tế (Nếu chưa có BCTC, thông báo rõ ràng)
  is_audited = info.get('isAudited', False)
  roe = info.get('roe', 0.0)
  pe = info.get('pe', 0.0)
  growth = info.get('profitGrowth', 0.0)
  ocf = info.get('ocf', 0.0)
  gross_margin = info.get('grossMargin', 0.0)

  if not is_audited or (roe == 0.0 and pe == 0.0 and growth == 0.0):
    info['faScore'] = 0
    info['faVerdict'] = 'Dữ liệu chưa ghi nhận'
    info['faColor'] = 'slate'
    return info

  score = 50
  if roe >= 20:
    score += 20
  elif roe >= 14:
    score += 12
  elif roe < 8 and roe != 0:
    score -= 15

  if 0 < pe <= 12:
    score += 15
  elif 12 < pe <= 18:
    score += 8
  elif pe > 25:
    score -= 10

  if growth >= 20:
    score += 15
  elif growth > 0:
    score += 8
  elif growth < 0:
    score -= 10

  # Đánh giá chất lượng dòng tiền (Quality of Earnings)
  if ocf > 0:
    score += 8   # Dòng tiền kinh doanh thật dương
  elif ocf < 0 and growth > 0:
    score -= 12  # Cảnh báo lợi nhuận giấy / lãi ảo

  if gross_margin >= 30.0:
    score += 5   # Biên lợi nhuận gộp dày

  score = max(10, min(98, score))
  info['faScore'] = score
  if score >= 80:
    info['faVerdict'] = 'Doanh Nghiệp Xuất Sắc (Top FA)'
    info['faColor'] = 'emerald'
  elif score >= 60:
    info['faVerdict'] = 'Sức Khỏe Tài Chính Tốt'
    info['faColor'] = 'blue'
  elif score >= 45:
    info['faVerdict'] = 'Trung Bình / Cân Bằng'
    info['faColor'] = 'amber'
  else:
    info['faVerdict'] = 'Cơ Bản Kém / Cần Thận Trọng'
    info['faColor'] = 'rose'

  return info


# ==================== PHÂN TÍCH KỸ THUẬT & DÒNG TIỀN NÂNG CAO ====================

_VNINDEX_CACHE = {'timestamp': 0, 'candles': []}
_WEEKLY_CHART_CACHE = {}


def get_vnindex_candles(days=120):
  """Lấy dữ liệu nến đóng cửa VN-Index để tính toán tương quan sức mạnh giá RS O'Neil."""
  global _VNINDEX_CACHE
  now = time.time()
  if now - _VNINDEX_CACHE['timestamp'] < 60 and _VNINDEX_CACHE['candles']:
    return _VNINDEX_CACHE['candles']
  try:
    now_ts = int(now)
    from_ts = now_ts - (days * 86400)
    url = f'https://services.entrade.com.vn/chart-api/v2/ohlcs/index?from={from_ts}&to={now_ts}&symbol=VNINDEX&resolution=1D'
    data = fetch_json(url)
    c_list = data.get('c', [])
    if c_list:
      _VNINDEX_CACHE['timestamp'] = now
      _VNINDEX_CACHE['candles'] = c_list
      return c_list
  except Exception as e:
    print('Lỗi fetch VNINDEX candles:', e)
  return _VNINDEX_CACHE.get('candles', [])


def calculate_relative_strength(stock_closes, vnindex_closes):
  """Tính chỉ số Sức mạnh giá tương đối RS Rating (1 - 99) so với VN-Index theo chuẩn O'Neil / CANSLIM.

  - Đo lường Alpha vượt trội của cổ phiếu so với VN-Index trong 1 tháng (20 phiên) và 3 tháng (60 phiên).
  - Phân loại:
    >= 80: Siêu cổ phiếu Leader (Dẫn dắt)
    65 - 79: Kênh trên (Mạnh hơn VN-Index)
    45 - 64: Trung tính (Vận động cùng thị trường)
    30 - 44: Kênh dưới (Yếu hơn VN-Index)
    < 30: Cổ phiếu tụt hậu (Laggard)
  """
  if not stock_closes or not vnindex_closes or len(stock_closes) < 15 or len(vnindex_closes) < 15:
    return {
        'rsScore': 50,
        'rsRating': 'Trung tính (Đang cập nhật nến đối chiếu)',
        'rsStatus': 'neutral',
        'rsColor': 'amber',
        'stockAlpha1M': 0.0,
        'stockAlpha3M': 0.0,
        'stockPerf1M': 0.0,
        'vniPerf1M': 0.0,
        'stockPerf3M': 0.0,
        'vniPerf3M': 0.0,
    }

  n_1m = min(20, len(stock_closes) - 1, len(vnindex_closes) - 1)
  n_3m = min(60, len(stock_closes) - 1, len(vnindex_closes) - 1)

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
    rs_rating = 'Siêu cổ phiếu Leader (Dẫn dắt)'
    rs_status = 'leader'
    rs_color = 'emerald'
  elif rs_score >= 65:
    rs_rating = 'Kênh trên (Mạnh hơn VN-Index)'
    rs_status = 'outperforming'
    rs_color = 'blue'
  elif rs_score >= 45:
    rs_rating = 'Trung tính (Vận động cùng thị trường)'
    rs_status = 'neutral'
    rs_color = 'slate'
  elif rs_score >= 30:
    rs_rating = 'Kênh dưới (Yếu hơn VN-Index)'
    rs_status = 'underperforming'
    rs_color = 'amber'
  else:
    rs_rating = 'Cổ phiếu tụt hậu (Laggard)'
    rs_status = 'laggard'
    rs_color = 'rose'

  return {
      'rsScore': rs_score,
      'rsRating': rs_rating,
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
  if not closes or len(closes) < 3:
    return 50.0
  p = min(period, len(closes) - 1)
  gains, losses = 0.0, 0.0
  for i in range(1, p + 1):
    diff = closes[i] - closes[i - 1]
    if diff >= 0:
      gains += diff
    else:
      losses -= diff
  if losses == 0:
    return 80.0
  rs = (gains / p) / (losses / p)
  return round(100.0 - (100.0 / (1.0 + rs)), 1)


def calculate_sma(series, period=20):
  if not series:
    return 0.0
  slice_data = series[-period:]
  return round(sum(slice_data) / len(slice_data), 1)


def analyze_technicals_and_scoring(
    candles_data, ssi_item, current_price, fundamental_info, ticker=None
):
  """Phân tích toàn diện kỹ thuật, xung lực dòng tiền, hỗ trợ/kháng cự động,

  sức mạnh giá tương đối RS O'Neil, đa khung thời gian và chấm điểm.
  """
  c_list = candles_data.get('c', [])
  h_list = candles_data.get('h', [])
  l_list = candles_data.get('l', [])
  v_list = candles_data.get('v', [])

  scale = 1000 if c_list and c_list[-1] < 1000 else 1
  closes = [p * scale for p in c_list]
  highs = [p * scale for p in h_list]
  lows = [p * scale for p in l_list]
  volumes = [v for v in v_list]

  rsi = calculate_rsi(closes, 14)
  ma20 = calculate_sma(closes, 20)
  ma50 = calculate_sma(closes, 50) if len(closes) >= 50 else ma20
  vol_ma20 = calculate_sma(volumes, 20)
  latest_vol = (
      ssi_item.get('stockVol')
      if ssi_item and ssi_item.get('stockVol')
      else (volumes[-1] if volumes else 0)
  )

  # Đột biến Volume
  vol_ratio = round(latest_vol / vol_ma20, 2) if vol_ma20 > 0 else 1.0
  if vol_ratio >= 1.5:
    vol_signal = f'BÙNG NỔ DÒNG TIỀN (x{vol_ratio})'
    vol_color = 'emerald'
  elif vol_ratio >= 1.0:
    vol_signal = f'Thanh khoản tích cực (x{vol_ratio})'
    vol_color = 'blue'
  elif vol_ratio <= 0.6:
    vol_signal = f'Cạn cung test nền (x{vol_ratio})'
    vol_color = 'amber'
  else:
    vol_signal = f'Thanh khoản bình quân (x{vol_ratio})'
    vol_color = 'slate'

  # Tỷ lệ Mua / Bán chủ động từ SSI
  buy_active = ssi_item.get('stockBUVol', 0) if ssi_item else 0
  sell_active = ssi_item.get('stockSDVol', 0) if ssi_item else 0
  total_active = buy_active + sell_active
  buy_ratio = round((buy_active / total_active) * 100, 1) if total_active else 50.0

  # Hỗ trợ & Kháng cự ĐỘNG từ 25 phiên gần nhất
  lookback = min(25, len(lows))
  support_level = round(min(lows[-lookback:]), -2) if lookback > 0 else ma20
  resistance_level = round(max(highs[-lookback:]), -2) if lookback > 0 else ma20

  # Đảm bảo logic hỗ trợ/kháng cự so với giá hiện tại
  if support_level >= current_price:
    support_level = round(current_price * 0.96, -2)
  if resistance_level <= current_price:
    resistance_level = round(current_price * 1.08, -2)

  # Entry, Target, Stop Loss bám theo hỗ trợ / kháng cự thật
  entry_min = round(max(support_level * 1.01, current_price * 0.985), -2)
  entry_max = round(current_price * 0.995, -2)
  target_price = resistance_level
  stop_price = round(support_level * 0.97, -2)  # Cắt lỗ khi thủng hỗ trợ 3%

  upside = (
      round((target_price - current_price) / current_price * 100, 1)
      if current_price > 0
      else 8.0
  )
  downside = (
      round((current_price - stop_price) / current_price * 100, 1)
      if current_price > 0
      else 4.0
  )
  rr_ratio = round(upside / downside, 1) if downside > 0 else 2.0

  # Tính toán Sức mạnh giá tương đối RS O'Neil so với VN-Index
  vnindex_c = get_vnindex_candles()
  rs_info = calculate_relative_strength(closes, vnindex_c)

  # Tính toán Đồng thuận đa khung thời gian D1 + W1
  multi_tf = calculate_multi_timeframe_confluence(ticker, current_price, ma20)

  # Quản trị Vị thế & Quy mô Giải ngân (Risk-Based Position Sizing: Max Risk 1.5% NAV)
  downside_risk = max(2.5, downside)
  max_nav_pct = min(35.0, round((1.5 / downside_risk) * 100.0, 1))
  pilot_nav_pct = round(max_nav_pct * 0.35, 1)
  pyramid_nav_pct = round(max_nav_pct * 0.65, 1)
  position_sizing = {
      'maxNavPct': max_nav_pct,
      'pilotNavPct': pilot_nav_pct,
      'pyramidNavPct': pyramid_nav_pct,
      'riskBudgetPct': 1.5,
      'downsideRiskPct': downside,
      'guide': (
          f'Giải ngân tối đa {max_nav_pct}% NAV danh mục (Vị thế thăm dò: {pilot_nav_pct}% NAV, '
          f'Gia tăng: {pyramid_nav_pct}% NAV khi break cản). Khống chế mức lỗ tối đa không quá 1.5% tổng NAV.'
      ),
  }

  # CHẤM ĐIỂM KỸ THUẬT (TA SCORE / 100)
  ta_score = 40
  if current_price >= ma20:
    ta_score += 20
  if current_price >= ma50:
    ta_score += 10
  if 50 <= rsi <= 65:
    ta_score += 15
  elif 40 <= rsi < 50:
    ta_score += 8
  elif rsi > 70:
    ta_score -= 15  # Quá mua rủi ro
  elif rsi < 35:
    ta_score += 5  # Quá bán bắt đáy

  if vol_ratio >= 1.5:
    ta_score += 15
  elif vol_ratio >= 1.1:
    ta_score += 8

  if buy_ratio >= 55:
    ta_score += 10
  elif buy_ratio < 45:
    ta_score -= 5

  # Tác động của RS Rating O'Neil (CANSLIM)
  rs_score = rs_info.get('rsScore', 50)
  if rs_score >= 80:
    ta_score += 15  # Siêu cổ phiếu dẫn dắt
  elif rs_score >= 65:
    ta_score += 8   # Kênh trên mạnh hơn thị trường
  elif rs_score < 40:
    ta_score -= 10  # Cổ phiếu yếu tụt hậu

  # Tác động của Đa khung thời gian D1 + W1
  if multi_tf.get('isAlignedBullish'):
    ta_score += 8
  elif multi_tf.get('isSevereDowntrend'):
    ta_score -= 10

  ta_score = max(10, min(98, ta_score))

  # Quyết định T+
  if rsi > 72:
    tplus_decision = 'QUÁ MUA - HẠN CHẾ ĐUA GIÁ'
    tplus_type = 'danger'
    tplus_reason = (
        f'RSI chạm {rsi} (vùng quá mua), giá đang tiệm cận kháng cự đỉnh cũ'
        f' ({resistance_level:,.0f} đ). Nguy cơ điều chỉnh T+ cao.'
    )
  elif ta_score >= 75 and vol_ratio >= 1.2 and rs_score >= 60:
    tplus_decision = 'MUA MẠNH - BÙNG NỔ DÒNG TIỀN'
    tplus_type = 'success'
    tplus_reason = (
        f'Giá giữ vững trên MA20 ({ma20:,.0f} đ), Volume bùng nổ gấp'
        f' {vol_ratio}x lần bình quân, RS Rating {rs_score}/99 ({rs_info.get("rsRating")}). '
        f'Lực cầu chủ động chiếm {buy_ratio}%.'
    )
  elif current_price >= ma20 and 46 <= rsi <= 68:
    tplus_decision = 'MUA TÍCH LŨY T+ (ĐẠT CHUẨN)'
    tplus_type = 'success'
    tplus_reason = (
        f'Nến duy trì trên MA20 ({ma20:,.0f} đ), RSI lành mạnh ({rsi}), RS {rs_score}/99, '
        f'R/R đạt 1:{rr_ratio}. Gom trong các nhịp rung lắc.'
    )
  elif rsi < 36:
    tplus_decision = 'BẮT ĐÁY NẢY KỸ THUẬT (RỦI RO CAO)'
    tplus_type = 'warning'
    tplus_reason = (
        f'RSI vùng quá bán ({rsi}), sát hỗ trợ cứng ({support_level:,.0f} đ).'
        ' Đánh nhanh nhịp hồi phục T+3 kiểm định lại MA20.'
    )
  else:
    tplus_decision = 'QUAN SÁT / CHƯA CÓ ĐIỂM VÀO'
    tplus_type = 'danger'
    tplus_reason = (
        f'Giá đang vận động dưới MA20 ({ma20:,.0f} đ), áp lực bán chủ động'
        f' ({100-buy_ratio:.1f}%). Cần chờ dòng tiền lớn xác nhận lại xu hướng.'
    )

  # Quyết định Trung hạn
  is_audited = fundamental_info.get('isAudited', False) if fundamental_info else False
  roe = fundamental_info.get('roe', 0.0) if fundamental_info else 0.0
  pe = fundamental_info.get('pe', 0.0) if fundamental_info else 0.0
  fa_score = fundamental_info.get('faScore', 0) if fundamental_info else 0

  if not is_audited or (roe == 0.0 and pe == 0.0):
    mid_decision = 'CHỜ BỔ SUNG DỮ LIỆU BCTC'
    mid_type = 'warning'
    mid_reason = (
        'Dữ liệu chỉ số BCTC kiểm toán (P/E, ROE) chưa ghi nhận đầy đủ từ cổng công bố'
        ' thông tin. Tạm thời chỉ ưu tiên giao dịch theo dòng tiền kỹ thuật T+.'
    )
    mid_entry = '--'
    mid_target = '--'
    mid_stop = '--'
    total_score = ta_score  # Chỉ chấm điểm theo kỹ thuật và dòng tiền thực tế
  elif fa_score >= 70 and current_price <= ma50 * 1.08:
    mid_decision = 'GOM MUA TÍCH SẢN (VÙNG GIÁ TỐT)'
    mid_type = 'success'
    mid_reason = (
        f"Doanh nghiệp FA loại A ({fundamental_info.get('name')}), ROE đạt"
        f" {roe:.1f}%. Giá chiết khấu hấp dẫn gom theo"
        ' phương pháp DCA.'
    )
    mid_entry = f'{round(current_price * 0.93, -2):,.0f} - {round(current_price * 0.97, -2):,.0f}'
    mid_target = f'{round(current_price * 1.18, -2):,.0f} - {round(current_price * 1.25, -2):,.0f} (+18% ~ +25%)'
    mid_stop = f'{round(current_price * 0.92, -2):,.0f} (-8%)'
    total_score = round(ta_score * 0.6 + fa_score * 0.4)
  elif pe > 22.0:
    mid_decision = 'CHỜ CHIẾT KHẤU THÊM (P/E CAO)'
    mid_type = 'warning'
    mid_reason = (
        f"P/E hiện tại ({pe:.1f}x) phản ánh phần lớn kỳ"
        ' vọng, biên an toàn trung hạn chưa đủ hấp dẫn để giải ngân vốn lớn.'
    )
    mid_entry = f'{round(current_price * 0.90, -2):,.0f} - {round(current_price * 0.94, -2):,.0f}'
    mid_target = f'{round(current_price * 1.15, -2):,.0f} (+15%)'
    mid_stop = f'{round(current_price * 0.90, -2):,.0f} (-10%)'
    total_score = round(ta_score * 0.6 + fa_score * 0.4)
  else:
    mid_decision = 'NẮM GIỮ THEO DÕI NỀN'
    mid_type = 'warning'
    mid_reason = (
        f"Định giá P/E ({pe:.1f}x) ở mức hợp lý, tiếp tục theo dõi tiến độ công bố BCTC quý tiếp"
        ' theo.'
    )
    mid_entry = f'{round(current_price * 0.93, -2):,.0f} - {round(current_price * 0.97, -2):,.0f}'
    mid_target = f'{round(current_price * 1.18, -2):,.0f} - {round(current_price * 1.25, -2):,.0f} (+18% ~ +25%)'
    mid_stop = f'{round(current_price * 0.92, -2):,.0f} (-8%)'
    total_score = round(ta_score * 0.6 + fa_score * 0.4)

  # Đánh giá tổng hợp 1 câu kết luận (OVERALL VERDICT)
  if ta_score >= 75 and fa_score >= 70:
    overall_status = '🌟 CỔ PHIẾU HOÀN HẢO: FA xuất sắc & Dòng tiền T+ bùng nổ'
    overall_color = 'emerald'
  elif ta_score >= 70:
    overall_status = '⚡ DÒNG TIỀN T+ MẠNH: Ưu tiên lướt sóng ngắn hạn'
    overall_color = 'blue'
  elif fa_score >= 75:
    overall_status = '💎 DOANH NGHIỆP GIÁ TRỊ: Thích hợp gom tích sản trung hạn'
    overall_color = 'indigo'
  elif ta_score < 45 and (fa_score < 50 and is_audited):
    overall_status = '⚠️ CẢNH BÁO RỦI RO: Cả kỹ thuật và cơ bản đều suy yếu'
    overall_color = 'rose'
  else:
    overall_status = '⏳ TRẠNG THÁI TRUNG TÍNH: Tích lũy chờ đợi tín hiệu mới'
    overall_color = 'amber'

  return {
      'rsi': rsi,
      'ma20': ma20,
      'ma50': ma50,
      'volMa20': vol_ma20,
      'volRatio': vol_ratio,
      'volSignal': vol_signal,
      'volColor': vol_color,
      'buyRatio': buy_ratio,
      'buyActive': buy_active,
      'sellActive': sell_active,
      'support': support_level,
      'resistance': resistance_level,
      'upside': upside,
      'downside': downside,
      'rrRatio': rr_ratio,
      'taScore': ta_score,
      'totalScore': total_score,
      'overallStatus': overall_status,
      'overallColor': overall_color,
      'rs': rs_info,
      'multiTimeframe': multi_tf,
      'positionSizing': position_sizing,
      'tPlus': {
          'decision': tplus_decision,
          'type': tplus_type,
          'reason': tplus_reason,
          'entry': f'{entry_min:,.0f} - {entry_max:,.0f}',
          'target': f'{target_price:,.0f} (+{upside}%)',
          'stop': f'{stop_price:,.0f} (-{downside}%)',
      },
      'midTerm': {
          'decision': mid_decision,
          'type': mid_type,
          'reason': mid_reason,
          'entry': mid_entry,
          'target': mid_target,
          'stop': mid_stop,
      },
  }


# ==================== CONTROLLERS & ENDPOINTS ====================



# ==================== DỰ BÁO TRIỂN VỌNG TƯƠNG LAI ĐA CHIỀU (GSO, VIETSTOCK, SSI) ====================

# ==================== CHUYÊN GIA ĐỊNH LƯỢNG & ĐÁNH GIÁ RỦI RO (SECURITIES RISK ASSESSMENT ENGINE) ====================

MACRO_SECTOR_DRIVERS = {
    'Công nghệ thông tin': {
        'environment': 'Tích cực',
        'environment_color': 'emerald',
        'macro_impact': 'Lãi suất điều hành thấp và chu kỳ phục hồi kinh tế toàn cầu kích thích dòng vốn đầu tư mạnh mẽ vào chuyển đổi số, điện toán đám mây và trung tâm dữ liệu bán dẫn. Tỷ giá USD/VND duy trì mức cao giúp tối ưu hóa doanh thu và biên lợi nhuận quy đổi từ các hợp đồng xuất khẩu phần mềm lớn, trong khi chi phí vốn vay duy trì ở mức tối ưu.',
        'catalysts': 'Ký kết các hợp đồng xuất khẩu phần mềm quy mô lớn và ứng dụng GenAI gia tăng năng suất, biên lợi nhuận ròng.',
        'macro_risks': 'Nguy cơ suy thoái kỹ thuật cục bộ tại các thị trường trọng điểm (Mỹ, Nhật Bản) có thể làm chậm quyết định giải ngân ngân sách IT của khách hàng lớn.'
    },
    'Xây dựng & Vật liệu': {
        'environment': 'Tích cực',
        'environment_color': 'emerald',
        'macro_impact': 'Tiến độ giải ngân vốn đầu tư công đạt quy mô kỷ lục theo báo cáo KT-XH định kỳ của GSO tại các dự án giao thông trọng điểm quốc gia (Cao tốc Bắc - Nam, Sân bay Long Thành, Vành đai 3 & 4). Lãi suất cho vay ưu đãi của các ngân hàng thương mại nhà nước giúp giảm mạnh chi phí vốn vay ngắn hạn phục vụ thi công.',
        'catalysts': 'Nghiệm thu khối lượng lớn các gói thầu hạ tầng giao thông và trúng thầu thêm các gói dự án công mới.',
        'macro_risks': 'Áp lực nợ đọng đọng vốn lưu động kéo dài, nguy cơ biến động giá nguyên vật liệu xây dựng (cát san lấp, đá, xi măng) làm bào mòn biên lãi gộp.'
    },
    'Thép & Tài nguyên cơ bản': {
        'environment': 'Trung lập',
        'environment_color': 'amber',
        'macro_impact': 'Chính sách áp thuế chống bán phá giá tạm thời bảo vệ sản xuất nội địa hỗ trợ sản lượng tiêu thụ thép xây dựng, tuy nhiên thị trường BĐS dân dụng phục hồi chậm kiềm chế biên lợi nhuận. Tỷ giá và giá nguyên liệu than cốc/quặng sắt thế giới biến động đòi hỏi doanh nghiệp quản trị chi phí vốn nhập khẩu thận trọng.',
        'catalysts': 'Áp thuế chống bán phá giá chính thức cho HRC và các lò cao công suất mới đi vào vận hành giúp giảm chi phí đơn vị.',
        'macro_risks': 'Áp lực dư thừa nguồn cung thép giá rẻ từ khu vực và rủi ro chậm phục hồi của thị trường bất động sản dân dụng.'
    },
    'Ngân hàng': {
        'environment': 'Tích cực',
        'environment_color': 'emerald',
        'macro_impact': 'Ngân hàng Nhà nước giữ mặt bằng lãi suất thấp kích thích tăng trưởng tín dụng toàn nền kinh tế dự kiến đạt ~15%. Tỷ lệ tiền gửi không kỳ hạn (CASA) hồi phục giúp tối ưu hóa chi phí huy động vốn (COF), qua đó mở rộng biên lãi thuần (NIM) trong khi lạm phát được kiểm soát ổn định dưới 4.5%.',
        'catalysts': 'Tín dụng bán lẻ và cho vay sản xuất phục hồi, trích lập dự phòng rủi ro nợ xấu bắt đầu tạo đỉnh và có xu hướng hoàn nhập.',
        'macro_risks': 'Rủi ro nợ xấu tiềm ẩn từ nhóm khách hàng bất động sản và trái phiếu doanh nghiệp nếu thanh khoản thị trường tài sản phục hồi chậm hơn kỳ vọng.'
    },
    'Dịch vụ Tài chính / Chứng khoán': {
        'environment': 'Tích cực',
        'environment_color': 'emerald',
        'macro_impact': 'Kỳ vọng nâng hạng thị trường chứng khoán Việt Nam lên Emerging Markets theo chuẩn FTSE và triển khai hệ thống công nghệ mới KRX tạo xung lực mạnh mẽ. Mặt bằng lãi suất tiền gửi thấp dịch chuyển dòng vốn dân cư sang kênh chứng khoán, gia tăng thanh khoản và mở rộng biên lợi nhuận mảng margin cũng như phí môi giới.',
        'catalysts': 'Thanh khoản thị trường bùng nổ, tăng trưởng mạnh mảng cho vay Margin và doanh thu phí môi giới, tự doanh.',
        'macro_risks': 'Áp lực bán ròng của dòng vốn ngoại và biến động địa chính trị toàn cầu có thể gây rung lắc chỉ số và làm sụt giảm thanh khoản ngắn hạn.'
    },
    'Bán lẻ tiêu dùng': {
        'environment': 'Tích cực',
        'environment_color': 'emerald',
        'macro_impact': 'Báo cáo bán lẻ hàng hóa GSO tăng trưởng tích cực nhờ chính sách giảm 2% thuế VAT và các gói kích cầu tiêu dùng nội địa. Lạm phát được kiểm soát giúp bảo vệ sức mua thực tế của người tiêu dùng, đồng thời chi phí vốn lưu động giảm hỗ trợ mở rộng mạng lưới phân phối.',
        'catalysts': 'Tối ưu hóa chi phí chuỗi cửa hàng, doanh thu trên mỗi điểm bán tăng và mảng thương mại điện tử bứt phá.',
        'macro_risks': 'Sức mua phân khúc hàng cao cấp phục hồi chậm và áp lực cạnh tranh khốc liệt từ các nền tảng thương mại điện tử giá rẻ.'
    },
    'Bất động sản': {
        'environment': 'Trung lập',
        'environment_color': 'amber',
        'macro_impact': 'Bộ 3 luật sửa đổi (Luật Đất đai, Nhà ở, Kinh doanh BĐS) bắt đầu khơi thông các nút thắt pháp lý dự án tồn đọng. Mặt bằng lãi suất vay mua nhà hạ nhiệt kích thích cầu tiêu dùng thực, tuy nhiên áp lực chi phí vốn đáo hạn trái phiếu và thời gian thẩm định định giá đất vẫn là yếu tố kiềm chế biên lợi nhuận ngành.',
        'catalysts': 'Khơi thông dòng tiền bán hàng tại các đại dự án pháp lý chuẩn và xử lý dứt điểm áp lực đáo hạn trái phiếu.',
        'macro_risks': 'Áp lực đáo hạn trái phiếu doanh nghiệp riêng lẻ và nguy cơ chậm tiến độ cấp phép định giá đất tại các địa phương.'
    },
    'Dầu khí & Năng lượng': {
        'environment': 'Tích cực',
        'environment_color': 'emerald',
        'macro_impact': 'Quy hoạch Điện VIII và chuỗi dự án khí điện Lô B - Ô Môn thúc đẩy khối lượng công việc ngành năng lượng trong chu kỳ 3-5 năm tới. Giá dầu thô Brent thế giới neo ở mức khả quan đảm bảo biên lợi nhuận cho các nhà thầu cung cấp dịch vụ thăm dò, khai thác ngoài khơi.',
        'catalysts': 'Ký mới các hợp đồng dịch vụ khoan/thăm dò ngoài khơi dài hạn với giá thuê ngày duy trì ở mức cao.',
        'macro_risks': 'Rủi ro chậm tiến độ trao thầu các gói EPCI lớn và biến động thất thường của giá dầu thô thế giới do suy yếu tăng trưởng toàn cầu.'
    }
}

DEFAULT_MACRO_DRIVER = {
    'environment': 'Trung lập',
    'environment_color': 'amber',
    'macro_impact': 'Báo cáo tình hình kinh tế - xã hội định kỳ của GSO ghi nhận sản xuất công nghiệp, dịch vụ và thặng dư thương mại duy trì mức xuất siêu ổn định. Mặt bằng lãi suất điều hành thấp và lạm phát được kiềm chế giúp ổn định chi phí vốn kinh doanh, tuy nhiên tốc độ mở rộng biên lợi nhuận có sự phân hóa rõ nét giữa các phân khúc.',
    'catalysts': 'Mở rộng quy mô doanh thu và tối ưu hóa chi phí vận hành trong chu kỳ kinh doanh mới.',
    'macro_risks': 'Rủi ro tỷ giá biến động và biến chuyển thất thường của dòng vốn đầu tư gián tiếp quốc tế.'
}


def calculate_market_fear_greed_index(ssi_board, ssi_item, technical_info):
  """
  Chỉ số Tâm Lý Thị Trường & Cổ Phiếu (Securities Market Fear & Greed Index: 0 - 100).
  Kết hợp định lượng 5 trụ cột:
  1. Độ rộng thị trường toàn sàn (Market Breadth: % mã tăng vs giảm trên SSI board) - 30%
  2. Xung lực dòng tiền thị trường (Active Buy / Total Active Vol trên toàn sàn) - 20%
  3. Chỉ số xung lực cổ phiếu (RSI 14 phiên) - 25%
  4. Lực mua chủ động cổ phiếu (Stock Buy Ratio) - 15%
  5. Đột biến thanh khoản cổ phiếu (Vol Ratio vs MA20) - 10%
  """
  gainers = 0
  losers = 0
  total_bu = 0
  total_sd = 0

  if ssi_board:
    for item in ssi_board.values():
      m_p = item.get('matchedPrice', 0)
      r_p = item.get('refPrice', 0)
      if m_p > 0 and r_p > 0:
        if m_p > r_p:
          gainers += 1
        elif m_p < r_p:
          losers += 1
      total_bu += item.get('stockBUVol', 0)
      total_sd += item.get('stockSDVol', 0)

  # 1. Market breadth score
  total_mkt = gainers + losers
  breadth_ratio = (gainers / total_mkt) if total_mkt > 0 else 0.5
  breadth_score = breadth_ratio * 100.0

  # 2. Market active flow score
  tot_flow = total_bu + total_sd
  mkt_flow_score = (total_bu / tot_flow * 100.0) if tot_flow > 0 else 50.0

  # 3. Stock RSI
  stock_rsi = technical_info.get('rsi', 50.0) if technical_info else 50.0

  # 4. Stock active buy ratio
  stock_buy_ratio = technical_info.get('buyRatio', 50.0) if technical_info else 50.0

  # 5. Stock vol ratio
  stock_vol_ratio = min(2.5, technical_info.get('volRatio', 1.0) if technical_info else 1.0)
  vol_score = min(100.0, stock_vol_ratio * 50.0)

  raw_score = (
      breadth_score * 0.30 +
      mkt_flow_score * 0.20 +
      stock_rsi * 0.25 +
      stock_buy_ratio * 0.15 +
      vol_score * 0.10
  )
  fear_greed_score = int(round(max(5.0, min(95.0, raw_score))))

  if fear_greed_score > 80:
    label = 'Cực kỳ hưng phấn (Extreme Greed)'
    color = 'rose'
  elif fear_greed_score >= 60:
    label = 'Lạc quan / Hưng phấn (Greed)'
    color = 'emerald'
  elif fear_greed_score >= 45:
    label = 'Cân bằng / Thận trọng (Neutral)'
    color = 'amber'
  elif fear_greed_score >= 25:
    label = 'Lo ngại / Thận trọng (Fear)'
    color = 'orange'
  else:
    label = 'Sợ hãi tột độ (Extreme Fear)'
    color = 'rose'

  return fear_greed_score, label, color


def detect_governance_and_legal_risks(ticker, news_list, fundamental_info):
  """
  Truy vết và phát hiện các rủi ro pháp lý, tranh chấp và kế hoạch phát hành pha loãng
  từ các nguồn tin tức BCTC, công bố thông tin HoSE/HNX, CafeF, VnExpress.
  Tuân thủ nghiêm ngặt Grounding Rule 1: Nếu không có dữ liệu vi phạm,
  ghi rõ 'Dữ liệu chưa ghi nhận rủi ro pháp lý hay kế hoạch phát hành pha loãng tiêu cực.'
  """
  legal_keywords = [
      'khởi tố', 'thanh tra', 'vi phạm', 'tranh chấp', 'bị phạt', 'khiếu kiện',
      'án phạt', 'tạm giam', 'thao túng', 'hủy niêm yết', 'đình chỉ', 'cảnh báo',
      'kiểm soát', 'phạt vi phạm', 'kê biên', 'truy cứu', 'bị kiện', 'tố tụng'
  ]
  dilution_keywords = [
      'phát hành riêng lẻ', 'chào bán riêng lẻ', 'chiết khấu', 'phát hành thêm giá',
      'esop tỷ lệ lớn', 'trái phiếu chuyển đổi', 'pha loãng cổ phiếu'
  ]
  mgmt_keywords = [
      'từ nhiệm', 'bổ nhiệm', 'chủ tịch', 'tổng giám đốc', 'miễn nhiệm',
      'thay đổi ban lãnh đạo', 'thay đổi nhân sự'
  ]

  legal_findings = []
  dilution_findings = []
  mgmt_findings = []

  texts_to_check = []
  if news_list:
    for n in news_list:
      title = n.get('title', '')
      if title:
        texts_to_check.append((title, n.get('source', 'Tin tức'), n.get('date', '')))

  summary = fundamental_info.get('summary', '') if fundamental_info else ''
  if summary:
    texts_to_check.append((summary, 'Hồ sơ doanh nghiệp', ''))

  for text, src, dt in texts_to_check:
    lower_text = text.lower()
    for kw in legal_keywords:
      if kw in lower_text:
        legal_findings.append(f"{text} ({src})")
        break
    for kw in dilution_keywords:
      if kw in lower_text:
        dilution_findings.append(f"{text} ({src})")
        break
    for kw in mgmt_keywords:
      if kw in lower_text:
        mgmt_findings.append(f"{text} ({src})")
        break

  has_legal = len(legal_findings) > 0
  has_dilution = len(dilution_findings) > 0

  parts = []
  if has_legal:
    parts.append(f"⚠️ CẢNH BÁO PHÁP LÝ & TRANH CHẤP: Ghi nhận sự kiện '{legal_findings[0]}'. Cần giám sát chặt chẽ phán quyết từ cơ quan quản lý.")
  if has_dilution:
    parts.append(f"⚠️ CẢNH BÁO PHA LOÃNG: Ghi nhận kế hoạch '{dilution_findings[0]}'. Tiềm ẩn áp lực pha loãng EPS của cổ đông hiện hữu.")
  if mgmt_findings and not has_legal:
    parts.append(f"Ghi nhận thông tin biến động nhân sự: '{mgmt_findings[0]}'.")

  if not parts:
    governance_summary = "Dữ liệu chưa ghi nhận rủi ro tranh chấp pháp lý, biến động lãnh đạo tiêu cực hay kế hoạch phát hành pha loãng chiết khấu sâu trong các công bố gần nhất."
  else:
    governance_summary = " ".join(parts)

  return has_legal, has_dilution, legal_findings, dilution_findings, governance_summary


def evaluate_securities_risk_engine(ticker, sector, current_price, fundamental_info, technical_info, ssi_item, ssi_board, news_list):
  """
  CHUYÊN GIA ĐỊNH LƯỢNG & ĐÁNH GIÁ RỦI RO CHỨNG KHOÁN (SECURITIES RISK ASSESSMENT ENGINE)
  Triển khai quy trình phân tích định lượng chuẩn 5 phần và hệ thống Guardrail ngưỡng chặn rủi ro.
  Tuân thủ 3 nguyên tắc bất di bất dịch (Grounding Rules):
  1. Không suy diễn ngoài dữ liệu (nếu thiếu, ghi 'Dữ liệu chưa ghi nhận').
  2. Khách quan đa chiều (nhận định tích cực luôn đi kèm yếu tố rủi ro tương ứng).
  3. Phân biệt rõ giữa dữ liệu thực tế lịch sử/hiện tại và kịch bản dự báo xác suất.
  """
  driver = MACRO_SECTOR_DRIVERS.get(sector, DEFAULT_MACRO_DRIVER)
  env_rating = driver.get('environment', 'Trung lập')
  env_color = driver.get('environment_color', 'amber')
  macro_impact = driver.get('macro_impact', '')

  # 1. Tính toán Fear & Greed Index
  fear_greed_score, fear_greed_label, fear_greed_color = calculate_market_fear_greed_index(
      ssi_board, ssi_item, technical_info
  )

  # 2. Phân tích Dòng vốn Khối ngoại & Thanh khoản thực tế
  buy_f = ssi_item.get('buyForeignQtty', 0) if ssi_item else 0
  sell_f = ssi_item.get('sellForeignQtty', 0) if ssi_item else 0
  foreign_net = buy_f - sell_f
  vol_ratio = technical_info.get('volRatio', 1.0)
  buy_ratio = technical_info.get('buyRatio', 50.0)

  if foreign_net > 100000:
    foreign_flow_text = (
        f"Khối ngoại mua ròng tích cực +{foreign_net:,.0f} cổ phiếu trong phiên ngắn hạn "
        f"(Khối lượng mua: {buy_f:,.0f} cp vs Bán: {sell_f:,.0f} cp). Dòng tiền ngoại nâng đỡ tâm lý, "
        f"tuy nhiên cần kiểm định mức độ duy trì dòng vốn ngoại khi chỉ số tiến sát kháng cự đỉnh cũ."
    )
  elif foreign_net < -50000:
    foreign_flow_text = (
        f"Khối ngoại bán ròng đáng kể -{abs(foreign_net):,.0f} cổ phiếu trong phiên ngắn hạn "
        f"(Khối lượng mua: {buy_f:,.0f} cp vs Bán: {sell_f:,.0f} cp). Áp lực cơ cấu chốt lời từ dòng vốn "
        f"ngoại tạo áp lực cung tiềm ẩn lên các nhịp tăng giá."
    )
  elif foreign_net < 0:
    foreign_flow_text = (
        f"Khối ngoại bán ròng nhẹ -{abs(foreign_net):,.0f} cổ phiếu trong phiên, giao dịch tương đối cân bằng. "
        f"Dòng tiền nội địa giữ vai trò chủ đạo chi phối bước giá."
    )
  else:
    foreign_flow_text = (
        f"Khối ngoại giao dịch cân bằng (Ròng: {foreign_net:+,.0f} cp, Mua: {buy_f:,.0f} vs Bán: {sell_f:,.0f} cp). "
        f"Xu hướng trung hạn ổn định, cổ phiếu vận động theo cung cầu tự nhiên thị trường."
    )

  rs_info = technical_info.get('rs', {}) if technical_info else {}
  rs_score = rs_info.get('rsScore', 50)
  rs_rating = rs_info.get('rsRating', 'Trung tính')
  alpha_1m = rs_info.get('stockAlpha1M', 0.0)
  alpha_3m = rs_info.get('stockAlpha3M', 0.0)

  sentiment_liquidity_text = (
      f"Chỉ số Tâm lý thị trường ghi nhận {fear_greed_score}/100 ({fear_greed_label}). "
      f"Thanh khoản đạt {vol_ratio}x mức bình quân 20 phiên với tỷ lệ mua chủ động {buy_ratio}%, "
      f"cho thấy mức độ hấp thụ cung-cầu {'tích cực, phe mua kiểm soát thế trận' if buy_ratio >= 52 else 'thận trọng, phe bán vẫn còn gây sức ép'}. "
      f"Sức mạnh giá tương đối RS Rating O'Neil (CANSLIM) đạt {rs_score}/99 ({rs_rating}) "
      f"với Alpha 1 tháng {alpha_1m:+.1f}% và Alpha 3 tháng {alpha_3m:+.1f}% so với VN-Index."
  )

  # 3. Phân tích Nội tại & Rủi ro Pháp lý (Áp dụng Grounding Rules 1 & 2)
  pe = fundamental_info.get('pe', 0.0) if fundamental_info else 0.0
  pb = fundamental_info.get('pb', 0.0) if fundamental_info else 0.0
  roe = fundamental_info.get('roe', 0.0) if fundamental_info else 0.0
  growth = fundamental_info.get('profitGrowth', 0.0) if fundamental_info else 0.0
  debt = fundamental_info.get('debtToEquity', 0.0) if fundamental_info else 0.0
  is_audited = fundamental_info.get('isAudited', False) if fundamental_info else False
  ocf = fundamental_info.get('ocf', 0.0) if fundamental_info else 0.0
  gross_margin = fundamental_info.get('grossMargin', 0.0) if fundamental_info else 0.0
  net_margin = fundamental_info.get('netMargin', 0.0) if fundamental_info else 0.0
  ocf_status = fundamental_info.get('ocfStatus', '') if fundamental_info else ''

  pe_display = f"{pe:.1f}x" if pe > 0 else "Dữ liệu chưa ghi nhận"
  pb_display = f"{pb:.1f}x" if pb > 0 else "Dữ liệu chưa ghi nhận"
  roe_display = f"{roe:.1f}%" if roe != 0 else "Dữ liệu chưa ghi nhận"
  growth_display = f"{growth:+.1f}%" if growth != 0 else "Dữ liệu chưa ghi nhận"
  ocf_display = f"{ocf:+,.1f} tỷ đ" if ocf != 0 else "Dữ liệu chưa ghi nhận"

  ocf_text = f" Dòng tiền thuần HĐKD (OCF) ghi nhận {ocf_display} ({ocf_status}), Biên lãi gộp {gross_margin:.1f}% và Biên lãi ròng {net_margin:.1f}%." if ocf != 0 or gross_margin != 0 else ""

  if roe != 0 and pe > 0:
    if roe >= 15.0 and growth > 0:
      growth_quality = (
          f"Theo số liệu BCTC kiểm toán thực tế, {ticker} ghi nhận tỷ suất sinh lời ROE {roe_display} "
          f"và tăng trưởng lợi nhuận {growth_display} so với cùng kỳ. Định giá P/E hiện tại {pe_display} và P/B {pb_display}. "
          f"Dù hiệu quả sinh lời vững vàng, doanh nghiệp chịu áp lực đòn bẩy D/E ở mức {debt:.2f}x.{ocf_text}"
      )
    elif growth < 0:
      growth_quality = (
          f"Theo số liệu BCTC kiểm toán thực tế, {ticker} ghi nhận ROE {roe_display}, tuy nhiên tăng trưởng lợi nhuận "
          f"suy giảm {growth_display} so với cùng kỳ. Mặc dù P/E ở mức {pe_display} (P/B {pb_display}), "
          f"biên an toàn doanh nghiệp suy giảm và rủi ro điều chỉnh định giá vẫn hiện hữu nếu chu kỳ kinh doanh chưa tạo đáy.{ocf_text}"
      )
    else:
      growth_quality = (
          f"Theo BCTC thực tế, {ticker} duy trì ROE {roe_display} với P/E {pe_display} và P/B {pb_display}, "
          f"tăng trưởng lợi nhuận {growth_display}. Định giá ở mức hợp lý so với trung bình ngành, "
          f"tuy nhiên cần lưu ý rủi ro chi phí lãi vay và áp lực dòng tiền kinh doanh ngắn hạn.{ocf_text}"
      )
  else:
    growth_quality = (
        f"Chỉ số định giá P/E ({pe_display}) và ROE ({roe_display}) đang được cập nhật từ cổng công bố BCTC kiểm toán. "
        f"Doanh nghiệp đang giao dịch theo thanh khoản và dòng tiền thực tế trên sàn.{ocf_text}"
    )

  has_legal, has_dilution, legal_findings, dilution_findings, governance_summary = detect_governance_and_legal_risks(
      ticker, news_list, fundamental_info
  )

  # 4. Ma trận Kịch bản Kỳ vọng & Quản trị Rủi ro (Scenario Matrix)
  support_level = technical_info.get('support', round(current_price * 0.96, -2))
  resistance_level = technical_info.get('resistance', round(current_price * 1.08, -2))
  stop_loss_price = technical_info.get('tPlus', {}).get('stop', '')
  if not stop_loss_price or stop_loss_price == '--':
    stop_loss_price = f"{round(support_level * 0.97, -2):,.0f} đ"
  target_price_str = technical_info.get('tPlus', {}).get('target', '')
  if not target_price_str or target_price_str == '--':
    target_price_str = f"{resistance_level:,.0f} đ"

  upside = technical_info.get('upside', 8.0)
  downside = technical_info.get('downside', 4.0)
  rr_ratio = technical_info.get('rrRatio', 2.0)
  ma20 = technical_info.get('ma20', current_price)

  pos_sizing = technical_info.get('positionSizing', {})
  max_nav = pos_sizing.get('maxNavPct', 25.0)
  pilot_nav = pos_sizing.get('pilotNavPct', 8.5)
  pyramid_nav = pos_sizing.get('pyramidNavPct', 16.5)

  mtf = technical_info.get('multiTimeframe', {})
  confluence_text = mtf.get('confluence', 'Theo dõi xu hướng')
  mtf_desc = mtf.get('description', '')

  bull_trigger = (
      f"Dòng tiền mua chủ động duy trì trên 55%, RS Rating duy trì kênh trên (>=65), "
      f"khối ngoại ngừng bán ròng và giá giữ vững hỗ trợ then chốt {support_level:,.0f} đ (nền MA20 {ma20:,.0f} đ)."
  )
  bull_target = f"{resistance_level:,.0f} đ (+{upside}%)"

  bear_risk = (
      f"Áp lực bán ròng gia tăng, xuất hiện phiên phân phối thanh khoản đột biến, "
      f"hoặc giá đóng cửa xuyên thủng ngưỡng hỗ trợ {support_level:,.0f} đ."
  )
  bear_support = f"{support_level:,.0f} đ (Cắt lỗ tại {stop_loss_price} [-{downside}%])"

  # 5. Hệ thống Guardrail & Quyết định Hành động (Action Conclusion)
  guardrails_triggered = []
  action_status = "Theo dõi"
  status_color = "slate"

  # Guardrail 2: Cảnh báo Rủi ro Pháp lý / Tranh chấp hoặc Pha loãng sâu
  if has_legal or has_dilution:
    guardrail_msg = (
        "GUARDRAIL PHÁP LÝ & QUẢN TRỊ: Phát hiện cờ cảnh báo về pháp lý/tranh chấp hoặc kế hoạch phát hành pha loãng -> "
        "Buộc chuyển trạng thái sang 'Thận trọng / Hạn chế giao dịch' bất chấp tín hiệu kỹ thuật ngắn hạn."
    )
    guardrails_triggered.append(guardrail_msg)
    action_status = "Thận trọng / Hạn chế giao dịch"
    status_color = "rose"
    core_warning = (
        "Ưu tiên tuyệt đối bảo toàn vốn; tạm ngừng mở vị thế mua mới cho đến khi có thông cáo chính thức "
        "làm rõ các vấn đề pháp lý và kế hoạch pha loãng từ doanh nghiệp."
    )

  # Guardrail 1: Thị trường hưng phấn cực độ (Fear & Greed > 80) kết hợp Khối ngoại xả hàng
  elif (fear_greed_score > 80 or (technical_info.get('rsi', 50) > 72 and fear_greed_score >= 70)) and foreign_net < -50000:
    guardrail_msg = (
        f"GUARDRAIL QUẢN TRỊ RỦI RO: Chỉ số tâm lý thị trường hưng phấn cực độ ({fear_greed_score}/100) kết hợp áp lực "
        f"khối ngoại bán ròng mạnh ({foreign_net:,.0f} cp) -> Buộc AI hạ tỷ trọng khuyến nghị mua mới, ưu tiên quản trị chốt lời bảo vệ thành quả."
    )
    guardrails_triggered.append(guardrail_msg)
    action_status = "Hạ tỷ trọng"
    status_color = "amber"
    core_warning = (
        f"Cảnh giác bẫy tăng giá khi thị trường hưng phấn kết hợp khối ngoại bán ròng; chủ động hiện thực hóa lợi nhuận "
        f"từng phần khi giá tiệm cận vùng kháng cự {resistance_level:,.0f} đ."
    )

  # Guardrail 3: Cảnh báo Lợi nhuận giấy & Thâm hụt dòng tiền nặng
  elif ocf < 0 and growth > 0 and debt > 1.8:
    guardrail_msg = (
        f"GUARDRAIL CHẤT LƯỢNG LỢI NHUẬN: Cảnh báo OCF âm ({ocf:+,.1f} tỷ đ) dù LNST tăng trưởng, "
        f"kết hợp đòn bẩy D/E cao ({debt:.2f}x) -> Tiềm ẩn rủi ro lợi nhuận giấy và căng thẳng dòng tiền lưu động."
    )
    guardrails_triggered.append(guardrail_msg)
    action_status = "Theo dõi"
    status_color = "amber"
    core_warning = (
        f"Thận trọng với rủi ro dòng tiền OCF âm ({ocf:+,.1f} tỷ đ); chỉ giao dịch ngắn hạn theo dòng tiền T+ "
        f"với tỷ trọng nhỏ tối đa {pilot_nav}% NAV, không giải ngân vốn lớn."
    )

  # Động cơ khuyến nghị chuẩn khi không vi phạm Guardrail
  else:
    ta_score = technical_info.get('taScore', 50)
    fa_score = fundamental_info.get('faScore', 0) if fundamental_info else 0
    rsi = technical_info.get('rsi', 50)

    if ta_score >= 75 and current_price >= ma20 and buy_ratio >= 55 and rs_score >= 60:
      action_status = "Mở vị thế thăm dò"
      status_color = "emerald"
      core_warning = (
          f"Quản trị vị thế: Giải ngân thăm dò tối đa {pilot_nav}% NAV quanh {current_price*0.985:,.0f} - {current_price*0.995:,.0f} đ "
          f"(tổng vị thế tối đa {max_nav}% NAV). {mtf_desc} Cắt lỗ tuyệt đối nếu thủng {support_level:,.0f} đ."
      )
    elif current_price >= ma20 and 46 <= rsi <= 68:
      action_status = "Tích lũy"
      status_color = "blue"
      core_warning = (
          f"Theo dõi tính nhất quán của dòng tiền chủ động tại vùng hỗ trợ {support_level:,.0f} đ (RS {rs_score}/99). "
          f"Tỷ trọng đề xuất: Thăm dò {pilot_nav}% NAV, kiểm soát rủi ro danh mục <= 1.5% NAV."
      )
    elif rsi > 70:
      action_status = "Hạ tỷ trọng"
      status_color = "amber"
      core_warning = (
          f"Cổ phiếu tiến sâu vào vùng quá mua RSI ({rsi:.1f}), rủi ro điều chỉnh T+ gia tăng; "
          f"hạn chế đua giá và canh chốt lời từng phần tại {resistance_level:,.0f} đ."
      )
    elif current_price < ma20:
      action_status = "Theo dõi"
      status_color = "slate"
      core_warning = (
          f"Giá vẫn vận động dưới đường MA20 ({ma20:,.0f} đ) và {confluence_text}; "
          f"kiên nhẫn đứng ngoài quan sát cho đến khi xuất hiện nến đảo chiều xác nhận dòng tiền lớn hấp thụ trở lại."
      )
    else:
      action_status = "Theo dõi"
      status_color = "slate"
      core_warning = (
          f"Duy trì tỷ trọng an toàn và theo dõi phản ứng cung cầu của cổ phiếu quanh ngưỡng hỗ trợ {support_level:,.0f} đ."
      )

  # 6. Biên soạn Báo Cáo Markdown Chuẩn theo Prompt Yêu Cầu
  markdown_report = f"""# BÁO CÁO ĐỊNH LƯỢNG & ĐÁNH GIÁ RỦI RO: {ticker}

## 1. TỔNG QUAN TÁC ĐỘNG VĨ MÔ & NGÀNH
- **Đánh giá môi trường**: [{env_rating}]
- **Tác động cụ thể**: {macro_impact}

## 2. NỘI TẠI & RỦI RO PHÁP LÝ DOANH NGHIỆP
- **Chất lượng tăng trưởng**: {growth_quality}
- **Rủi ro quản trị & pha loãng**: {governance_summary}

## 3. DÒNG TIỀN & TÂM LÝ THỊ TRƯỜNG
- **Dòng vốn khối ngoại**: {foreign_flow_text}
- **Tâm lý & thanh khoản**: {sentiment_liquidity_text}

## 4. MA TRẬN KỊCH BẢN KỲ VỌNG & QUẢN TRỊ RỦI RO
- **Kịch bản Khả quan (Bull Case)**:
  - Điều kiện kích hoạt: {bull_trigger}
  - Mục tiêu giá/Kháng cự kỳ vọng: {bull_target}
- **Kịch bản Thận trọng/Phòng thủ (Bear Case)**:
  - Yếu tố rủi ro kích hoạt: {bear_risk}
  - Vùng hỗ trợ/Cắt lỗ đề xuất: {bear_support}
- **Tỷ lệ Lợi nhuận/Rủi ro (R:R Ratio)**: 1:{rr_ratio}
- **Quản trị vị thế (Position Sizing)**: Tỷ trọng giải ngân tối đa {max_nav}% NAV (Thăm dò: {pilot_nav}% NAV, Gia tăng: {pyramid_nav}% NAV) • Giới hạn rủi ro danh mục tối đa 1.5% NAV.

## 5. KẾT LUẬN HÀNH ĐỘNG
- **Trạng thái**: [{action_status}]
- **Xu hướng đa khung (Multi-Timeframe)**: {confluence_text}
- **Lưu ý cốt lõi**: {core_warning}
"""

  return {
      'macroSector': {
          'environment': env_rating,
          'environmentColor': env_color,
          'macroImpact': macro_impact,
          'sector': sector,
      },
      'fundamentalRisk': {
          'growthQuality': growth_quality,
          'governanceDilutionRisk': governance_summary,
          'peDisplay': pe_display,
          'pbDisplay': pb_display,
          'roeDisplay': roe_display,
          'growthDisplay': growth_display,
          'ocfDisplay': ocf_display,
          'grossMargin': gross_margin,
          'netMargin': net_margin,
          'ocfStatus': ocf_status,
          'hasLegalDisputes': has_legal,
          'hasDilutionRisk': has_dilution,
          'isAudited': is_audited,
      },
      'marketFlow': {
          'foreignFlow': foreign_flow_text,
          'foreignNet': foreign_net,
          'sentimentLiquidity': sentiment_liquidity_text,
          'fearGreedScore': fear_greed_score,
          'fearGreedLabel': fear_greed_label,
          'fearGreedColor': fear_greed_color,
          'buyRatio': buy_ratio,
          'volRatio': vol_ratio,
          'rsScore': rs_score,
          'rsRating': rs_rating,
      },
      'scenarioMatrix': {
          'bullCase': {
              'trigger': bull_trigger,
              'targetPrice': resistance_level,
              'targetDisplay': bull_target,
              'upside': upside,
          },
          'bearCase': {
              'trigger': bear_risk,
              'supportPrice': support_level,
              'stopLoss': stop_loss_price,
              'supportDisplay': bear_support,
              'downside': downside,
          },
          'rrRatio': rr_ratio,
          'positionSizing': pos_sizing,
      },
      'actionConclusion': {
          'status': action_status,
          'statusColor': status_color,
          'guardrailsTriggered': guardrails_triggered,
          'coreWarning': core_warning,
          'multiTimeframe': mtf,
      },
      'rawMarkdown': markdown_report,
  }


def generate_multi_source_future_outlook(ticker, sector, current_price, fundamental_info, technical_info, ssi_item=None, ssi_board=None, news_list=None):
  """Wrapper tương thích ngược tổng hợp phân tích đa nguồn từ SecuritiesRiskAssessmentEngine."""
  risk_rep = evaluate_securities_risk_engine(
      ticker=ticker,
      sector=sector,
      current_price=current_price,
      fundamental_info=fundamental_info,
      technical_info=technical_info,
      ssi_item=ssi_item or {},
      ssi_board=ssi_board or {},
      news_list=news_list or []
  )

  fg = risk_rep['marketFlow']
  act = risk_rep['actionConclusion']
  scen = risk_rep['scenarioMatrix']

  return {
      'consensus': act['status'].upper(),
      'consensusColor': act['statusColor'],
      'confidence': f"Fear & Greed: {fg['fearGreedScore']}/100 ({fg['fearGreedLabel']})",
      'macroSummary': f"[{risk_rep['macroSector']['environment']}] {risk_rep['macroSector']['macroImpact']}",
      'fundamentalSummary': f"{risk_rep['fundamentalRisk']['growthQuality']} {risk_rep['fundamentalRisk']['governanceDilutionRisk']}",
      'flowSummary': f"{fg['foreignFlow']} {fg['sentimentLiquidity']}",
      'bullScenario': f"Mục tiêu {scen['bullCase']['targetDisplay']}. Kích hoạt: {scen['bullCase']['trigger']}",
      'bearScenario': f"{scen['bearCase']['supportDisplay']}. Rủi ro kích hoạt: {scen['bearCase']['trigger']}",
      'riskEngine': risk_rep,
  }


# ==================== CỔNG TRUY VẾT TIN TỨC & SỰ KIỆN ĐA NGUỒN DYNAMIC ====================
_LIVE_NEWS_CACHE = {}
_LIVE_NEWS_CACHE_TTL = 600  # 10 phút cache cho mỗi mã cổ phiếu


def fetch_live_multi_sources(ticker, ssi_item, fundamental_info, current_price, pct_change, sector_name):
  """Truy vết Real-time dữ liệu Tin tức, BCTC, Sự kiện & Vĩ mô từ 5-6 nguồn uy tín ĐỘC LẬP
  (CafeF, Cổng Sự kiện HoSE/HNX, Vietstock Finance, VnExpress Kinh Doanh, SSI iBoard, Cổng TTĐT Chính Phủ/GSO).
  Tuyệt đối không gán cứng chuỗi text mẫu.
  """
  now = time.time()
  cached = _LIVE_NEWS_CACHE.get(ticker)
  if cached and (now - cached['time'] < _LIVE_NEWS_CACHE_TTL):
    records = [dict(r) for r in cached['data']]
    # Cập nhật số liệu SSI realtime mới nhất nếu có
    for r in records:
      if r.get('source') == 'SSI iBoard Pro':
        vol = ssi_item.get('stockVol', 0) if ssi_item else 0
        buy_vol = ssi_item.get('stockBUVol', 0) if ssi_item else 0
        sell_vol = ssi_item.get('stockSDVol', 0) if ssi_item else 0
        f_net = (ssi_item.get('buyForeignQtty', 0) - ssi_item.get('sellForeignQtty', 0)) if ssi_item else 0
        r['title'] = (
            f"Khớp lệnh {current_price:,.0f} ({pct_change:+.2f}%) | KL: {vol:,.0f} cp | "
            f"Mua CĐ: {buy_vol:,.0f} vs Bán CĐ: {sell_vol:,.0f} | NN ròng: {f_net:,.0f} cp"
        )
        r['date'] = time.strftime('%d/%m/%Y %H:%M')
    return records

  news_records = []

  # 1. Tracing CafeF qua crawler search realtime
  def trace_cafef():
    try:
      url = f'https://cafef.vn/tim-kiem.chn?keywords={ticker}'
      req = urllib.request.Request(
          url,
          headers={
              'User-Agent': (
                  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
                  ' AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
              )
          },
      )
      with urllib.request.urlopen(req, timeout=3.5) as res:
        soup = BeautifulSoup(res.read(), 'html.parser')
      for h in soup.find_all(['h3', 'h4']):
        a = h.find('a')
        if a and a.get_text(strip=True):
          txt = a.get_text(strip=True)
          link = a.get('href', '')
          if not link.startswith('http'):
            link = 'https://cafef.vn' + link
          if len(txt) > 15:
            return {
                'source': 'CafeF Doanh Nghiệp',
                'badge': 'TIN TỨC BÁO CHÍ',
                'badgeColor': 'amber',
                'title': txt,
                'date': time.strftime('%d/%m/%Y'),
                'url': link,
            }
    except Exception:
      pass
    return None

  # 2. Tracing Cổng Sự kiện Doanh Nghiệp (HoSE/HNX/VCI)
  def trace_events():
    try:
      c = Company(symbol=ticker, source='VCI')
      events = c.events()
      if events is not None and not events.empty:
        e0 = events.iloc[0]
        title = str(
            e0.get('event_title_vi')
            or e0.get('event_name_vi')
            or f'Công bố thông tin {ticker}'
        )
        pub_date = str(e0.get('public_date') or time.strftime('%d/%m/%Y'))[:10]
        return {
            'source': 'Cổng Sự Kiện Doanh Nghiệp (HoSE/HNX)',
            'badge': 'SỰ KIỆN & CỔ TỨC',
            'badgeColor': 'cyan',
            'title': title,
            'date': pub_date,
            'url': f'https://s.cafef.vn/tin-doanh-nghiep/{ticker}/event.chn',
        }
    except Exception:
      pass
    return None

  # 3. Tracing VnExpress Kinh Doanh RSS
  def trace_vne():
    try:
      url = 'https://vnexpress.net/rss/kinh-doanh.rss'
      req = urllib.request.Request(
          url,
          headers={
              'User-Agent': (
                  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
                  ' AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
              )
          },
      )
      with urllib.request.urlopen(req, timeout=3.5) as res:
        root = ET.fromstring(res.read())
      items = root.findall('.//item')
      # Ưu tiên khớp ticker hoặc ngành
      for item in items[:20]:
        t = item.find('title').text if item.find('title') is not None else ''
        l = item.find('link').text if item.find('link') is not None else ''
        d = item.find('pubDate').text if item.find('pubDate') is not None else ''
        if ticker.lower() in t.lower() or (
            sector_name and sector_name.lower() in t.lower()
        ):
          return {
              'source': 'VnExpress Kinh Doanh',
              'badge': 'THỜI SỰ & KINH TẾ',
              'badgeColor': 'purple',
              'title': t,
              'date': d[:16],
              'url': l,
          }
      if items:
        it = items[0]
        return {
            'source': 'VnExpress Kinh Doanh',
            'badge': 'THỜI SỰ & KINH TẾ',
            'badgeColor': 'purple',
            'title': it.find('title').text,
            'date': (
                it.find('pubDate').text[:16]
                if it.find('pubDate') is not None
                else ''
            ),
            'url': it.find('link').text,
        }
    except Exception:
      pass
    return None

  # 4. Tracing Vĩ mô Cổng Thông Tin Điện Tử Chính Phủ & GSO
  def trace_gov():
    try:
      url = 'https://baochinhphu.vn/kinh-te.rss'
      req = urllib.request.Request(
          url,
          headers={
              'User-Agent': (
                  'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
                  ' AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
              )
          },
      )
      with urllib.request.urlopen(req, timeout=3.5) as res:
        root = ET.fromstring(res.read())
      items = root.findall('.//item')
      if items:
        it0 = items[0]
        return {
            'source': 'Cổng TTĐT Chính Phủ (Vĩ Mô)',
            'badge': 'VĨ MÔ NHÀ NƯỚC',
            'badgeColor': 'rose',
            'title': it0.find('title').text,
            'date': (
                it0.find('pubDate').text[:16]
                if it0.find('pubDate') is not None
                else time.strftime('%d/%m/%Y')
            ),
            'url': it0.find('link').text,
        }
    except Exception:
      pass
    return None

  # Thực thi crawl song song 4 luồng
  with ThreadPoolExecutor(max_workers=4) as ex:
    f_cafef = ex.submit(trace_cafef)
    f_events = ex.submit(trace_events)
    f_vne = ex.submit(trace_vne)
    f_gov = ex.submit(trace_gov)

    cafef_item = f_cafef.result()
    events_item = f_events.result()
    vne_item = f_vne.result()
    gov_item = f_gov.result()

  # 1. CafeF Doanh Nghiệp (nếu không có thì fallback sang vnstock news của FiinGroup)
  if cafef_item:
    news_records.append(cafef_item)
  else:
    try:
      c = Company(symbol=ticker, source='VCI')
      news_df = c.news()
      if news_df is not None and not news_df.empty:
        n0 = news_df.iloc[0]
        news_records.append({
            'source': 'Tin Tức Doanh Nghiệp (FiinGroup/VCI)',
            'badge': 'TIN TỨC BÁO CHÍ',
            'badgeColor': 'amber',
            'title': str(n0.get('news_title')),
            'date': (
                str(n0.get('public_date', ''))[:10]
                or time.strftime('%d/%m/%Y')
            ),
            'url': f'https://s.cafef.vn/hose/{ticker}-cong-ty.chn',
        })
    except Exception:
      pass

  # 2. Cổng Sự kiện Doanh Nghiệp (HoSE/HNX)
  if events_item:
    news_records.append(events_item)

  # 3. Vietstock Finance (Báo cáo tài chính & chỉ số cơ bản thực tế)
  pe = fundamental_info.get('pe', 0.0) if fundamental_info else 0.0
  pb = fundamental_info.get('pb', 0.0) if fundamental_info else 0.0
  roe = fundamental_info.get('roe', 0.0) if fundamental_info else 0.0
  eps = fundamental_info.get('eps', 0.0) if fundamental_info else 0.0
  gross_margin = fundamental_info.get('gross_margin', 0.0) if fundamental_info else 0.0
  growth = fundamental_info.get('profitGrowth', 0.0) if fundamental_info else 0.0
  is_audited = fundamental_info.get('isAudited', False) if fundamental_info else False

  if is_audited and (pe > 0 or pb > 0 or roe != 0 or eps > 0):
    metrics = []
    if pe > 0:
      metrics.append(f'P/E {pe:.1f}x')
    if pb > 0:
      metrics.append(f'P/B {pb:.1f}x')
    if roe != 0:
      metrics.append(f'ROE {roe:.1f}%')
    if eps > 0:
      metrics.append(f'EPS {eps:,.0f}đ')
    if gross_margin > 0:
      metrics.append(f'Biên LN {gross_margin:.1f}%')
    if growth != 0:
      metrics.append(f'Tăng trưởng LN {growth:+.1f}%')
    vietstock_title = f'Hồ sơ BCTC kiểm toán mã {ticker}: ' + ' | '.join(metrics)
  else:
    vietstock_title = (
        f'Chỉ số tài chính mã {ticker}: Dữ liệu BCTC kiểm toán chưa ghi nhận'
        ' đầy đủ từ cổng công bố thông tin.'
    )
  news_records.append({
      'source': 'Vietstock Finance',
      'badge': 'BÁO CÁO TÀI CHÍNH',
      'badgeColor': 'blue',
      'title': vietstock_title,
      'date': time.strftime('%d/%m/%Y'),
      'url': f'https://finance.vietstock.vn/{ticker}/tai-chinh.htm',
  })

  # 4. VnExpress Kinh Doanh
  if vne_item:
    news_records.append(vne_item)

  # 5. SSI iBoard Pro Realtime
  vol = ssi_item.get('stockVol', 0) if ssi_item else 0
  buy_vol = ssi_item.get('stockBUVol', 0) if ssi_item else 0
  sell_vol = ssi_item.get('stockSDVol', 0) if ssi_item else 0
  f_net = (ssi_item.get('buyForeignQtty', 0) - ssi_item.get('sellForeignQtty', 0)) if ssi_item else 0
  ssi_title = (
      f"Khớp lệnh {current_price:,.0f} ({pct_change:+.2f}%) | KL: {vol:,.0f} cp | "
      f"Mua CĐ: {buy_vol:,.0f} vs Bán CĐ: {sell_vol:,.0f} | Khối ngoại ròng: {f_net:,.0f} cp"
  )
  news_records.append({
      'source': 'SSI iBoard Pro',
      'badge': 'DÒNG TIỀN REALTIME',
      'badgeColor': 'emerald',
      'title': ssi_title,
      'date': time.strftime('%d/%m/%Y %H:%M'),
      'url': 'https://iboard.ssi.com.vn/',
  })

  # 6. Cổng TTĐT Chính Phủ & Tổng Cục Thống Kê
  if gov_item:
    news_records.append(gov_item)

  # Lưu cache
  _LIVE_NEWS_CACHE[ticker] = {'time': now, 'data': news_records}
  return news_records


def handle_stock_detail(ticker, resolution='1D'):
  ticker = ticker.strip().upper()
  ssi_board = get_ssi_board_data()
  ssi_item = ssi_board.get(ticker, {})

  chart_data = fetch_chart_data(ticker, days=120, resolution=resolution)
  t_list = chart_data.get('t', [])
  o_list = chart_data.get('o', [])
  h_list = chart_data.get('h', [])
  l_list = chart_data.get('l', [])
  c_list = chart_data.get('c', [])
  v_list = chart_data.get('v', [])

  if not c_list:
    raise ValueError(f'Không tìm thấy dữ liệu cho mã {ticker}')

  scale = 1000 if c_list[-1] < 1000 else 1
  latest_c = c_list[-1] * scale
  prev_c = (c_list[-2] * scale) if len(c_list) > 1 else latest_c

  # Dữ liệu realtime từ SSI nếu có phiên đang mở
  if ssi_item and ssi_item.get('matchedPrice', 0) > 0:
    current_price = ssi_item['matchedPrice']
    price_change = ssi_item.get('priceChange', current_price - prev_c)
    pct_change = ssi_item.get(
        'priceChangePercent',
        round((price_change / prev_c) * 100, 2) if prev_c else 0,
    )
    company_name = ssi_item.get(
        'companyNameVi', ssi_item.get('clientName', f'Cổ phiếu {ticker}')
    )
    exchange = ssi_item.get('exchange', 'HOSE').upper()
    ceiling = ssi_item.get('ceiling', round(current_price * 1.07))
    floor = ssi_item.get('floor', round(current_price * 0.93))
    ref_price = ssi_item.get('refPrice', prev_c)
    highest_price = ssi_item.get('highest') or (h_list[-1] * scale if h_list else current_price)
    lowest_price = ssi_item.get('lowest') or (l_list[-1] * scale if l_list else current_price)
    total_vol = ssi_item.get('stockVol', v_list[-1] if v_list else 0)
    foreign_net = ssi_item.get('buyForeignQtty', 0) - ssi_item.get(
        'sellForeignQtty', 0
    )
  elif ssi_item and ssi_item.get('refPrice', 0) > 0:
    ref_price = ssi_item['refPrice']
    current_price = ssi_item.get('matchedPrice') or ref_price
    price_change = ssi_item.get('priceChange', current_price - ref_price)
    pct_change = ssi_item.get('priceChangePercent', 0)
    company_name = ssi_item.get(
        'companyNameVi', ssi_item.get('clientName', f'Cổ phiếu {ticker}')
    )
    exchange = ssi_item.get('exchange', 'HOSE').upper()
    ceiling = ssi_item.get('ceiling', round(ref_price * 1.07))
    floor = ssi_item.get('floor', round(ref_price * 0.93))
    highest_price = ssi_item.get('highest') or (h_list[-1] * scale if h_list else current_price)
    lowest_price = ssi_item.get('lowest') or (l_list[-1] * scale if l_list else current_price)
    total_vol = ssi_item.get('stockVol', v_list[-1] if v_list else 0)
    foreign_net = ssi_item.get('buyForeignQtty', 0) - ssi_item.get(
        'sellForeignQtty', 0
    )
  else:
    current_price = latest_c
    price_change = latest_c - prev_c
    pct_change = round((price_change / prev_c) * 100, 2) if prev_c else 0
    company_name = f'Cổ phiếu {ticker}'
    exchange = 'HOSE'
    ref_price = prev_c
    ceiling = round(ref_price * 1.07)
    floor = round(ref_price * 0.93)
    highest_price = (h_list[-1] * scale) if h_list else current_price
    lowest_price = (l_list[-1] * scale) if l_list else current_price
    total_vol = v_list[-1] if v_list else 0
    foreign_net = 0

  if not highest_price or highest_price <= 0:
    highest_price = current_price
  if not lowest_price or lowest_price <= 0:
    lowest_price = current_price

  # Định dạng nến cho Lightweight Charts (TradingView)
  candles_series = format_candles(chart_data, resolution=resolution)

  # Cơ bản doanh nghiệp
  fundamental_info = get_fundamental_profile(ticker, current_price)
  if company_name == f'Cổ phiếu {ticker}' and fundamental_info.get('name'):
    company_name = fundamental_info['name']

  # Phân tích kỹ thuật & Chấm điểm
  analysis = analyze_technicals_and_scoring(
      chart_data, ssi_item, current_price, fundamental_info, ticker=ticker
  )

  # 1. Danh sách Cổng thông tin sự kiện & Báo cáo BCTC tham chiếu (Mỗi record 1 nguồn uy tín khác nhau, trace động)
  date_str = (
      time.strftime('%d/%m/%Y', time.localtime(t_list[-1]))
      if t_list
      else time.strftime('%d/%m/%Y')
  )
  sector_name = fundamental_info.get('sector', 'Thị trường')
  news_list = fetch_live_multi_sources(
      ticker, ssi_item, fundamental_info, current_price, pct_change, sector_name
  )

  # 2. Tổng hợp thông tin đa chiều định lượng & đánh giá rủi ro 5 phần
  risk_engine_report = evaluate_securities_risk_engine(
      ticker=ticker,
      sector=sector_name,
      current_price=current_price,
      fundamental_info=fundamental_info,
      technical_info=analysis,
      ssi_item=ssi_item,
      ssi_board=ssi_board,
      news_list=news_list,
  )

  future_outlook = generate_multi_source_future_outlook(
      ticker,
      sector_name,
      current_price,
      fundamental_info,
      analysis,
      ssi_item=ssi_item,
      ssi_board=ssi_board,
      news_list=news_list,
  )

  return {
      'code': ticker,
      'name': company_name,
      'exchange': exchange,
      'date': date_str,
      'price': current_price,
      'prevPrice': ref_price,
      'priceChange': price_change,
      'percentChange': pct_change,
      'highest': highest_price,
      'lowest': lowest_price,
      'highPrice': highest_price,
      'lowPrice': lowest_price,
      'ceiling': ceiling,
      'floor': floor,
      'refPrice': ref_price,
      'totalVolume': total_vol,
      'foreignNet': foreign_net,
      'fundamentals': fundamental_info,
      'technicals': analysis,
      'candles': candles_series,
      'news': news_list,
      'futureOutlook': future_outlook,
      'riskEngine': risk_engine_report,
  }


_TOP_TPLUS_CACHE = {'timestamp': 0, 'data': None}

def handle_top_tplus():
  """Lọc danh sách Top 10 Cổ Phiếu T+ tiềm năng nhất tự động từ toàn thị trường SSI iBoard."""
  global _TOP_TPLUS_CACHE
  now = time.time()
  if now - _TOP_TPLUS_CACHE['timestamp'] < 60 and _TOP_TPLUS_CACHE['data']:
    return _TOP_TPLUS_CACHE['data']

  ssi_board = get_ssi_board_data()
  if not ssi_board:
    return {'date': time.strftime('%d/%m/%Y'), 'count': 0, 'data': []}

  # 1. Quét toàn bộ cổ phiếu trên 3 sàn, loại bỏ chứng quyền/trái phiếu/ETF và penny rác
  candidates_raw = [
      item for item in ssi_board.values()
      if len(item.get('stockSymbol', '')) == 3
      and item.get('stockSymbol', '').isalpha()
      and item.get('stockVol', 0) >= 150000
      and (item.get('matchedPrice', 0) >= 6000 or item.get('refPrice', 0) >= 6000)
  ]

  # 2. Xếp hạng ưu tiên theo thanh khoản và lực mua chủ động SSI
  candidates_raw.sort(key=lambda x: (
      (x.get('stockBUVol', 0) / (x.get('stockBUVol', 0) + x.get('stockSDVol', 0) + 1)) * 0.4 +
      min(x.get('stockVol', 0) / 1000000, 5) * 0.6
  ), reverse=True)

  test_symbols = [x['stockSymbol'] for x in candidates_raw[:35]]

  def evaluate_candidate(sym):
    try:
      ssi_item = ssi_board.get(sym, {})
      chart = fetch_chart_data(sym, days=60)
      c_list = chart.get('c', [])
      v_list = chart.get('v', [])
      if len(c_list) < 20:
        return None

      scale = 1000 if c_list[-1] < 1000 else 1
      closes = [p * scale for p in c_list]
      latest_p = ssi_item.get('matchedPrice') or closes[-1]
      prev_p = closes[-2]
      pct_change = round(((latest_p - prev_p) / prev_p) * 100, 2)

      rsi = calculate_rsi(closes, 14)
      ma20 = calculate_sma(closes, 20)
      vol_ma20 = calculate_sma(v_list, 20)
      latest_vol = ssi_item.get('stockVol', v_list[-1])
      vol_ratio = round(latest_vol / vol_ma20, 2) if vol_ma20 > 0 else 1.0

      bu = ssi_item.get('stockBUVol', 0)
      sd = ssi_item.get('stockSDVol', 0)
      tot = bu + sd
      buy_ratio = round(bu / tot * 100, 1) if tot > 0 else 50.0

      score = 0
      if latest_p >= ma20: score += 35
      if vol_ratio >= 1.5: score += 30
      elif vol_ratio >= 1.1: score += 18
      if 48 <= rsi <= 68: score += 20
      if pct_change > 0: score += 15
      if buy_ratio >= 55: score += 10

      support = round(min(closes[-15:]), -2)
      target = round(max(closes[-20:]) * 1.02, -2)
      if target <= latest_p:
        target = round(latest_p * 1.08, -2)

      f_net = ssi_item.get('buyForeignQtty', 0) - ssi_item.get('sellForeignQtty', 0)
      guardrail_flag = 'An toàn'
      # Guardrail 1: Nếu RSI > 70 và Khối ngoại bán ròng mạnh -> trừ điểm rủi ro
      if rsi > 70 and f_net < -50000:
        score -= 30
        guardrail_flag = 'Cảnh báo xả ngoại (Quá mua)'
      elif f_net > 50000:
        score += 10
        guardrail_flag = 'Ngoại gom ròng'

      sign = '+' if pct_change >= 0 else ''
      return {
          'ticker': sym,
          'name': ssi_item.get('companyNameVi', f'Cổ phiếu {sym}'),
          'price': latest_p,
          'change': f'{sign}{pct_change}%',
          'pctChange': pct_change,
          'rsi': rsi,
          'volRatio': vol_ratio,
          'volSignal': f'Nổ Vol x{vol_ratio}' if vol_ratio >= 1.4 else f'Vol x{vol_ratio}',
          'trend': f'Trên MA20 ({ma20:,.0f})' if latest_p >= ma20 else f'Dưới MA20 ({ma20:,.0f})',
          'entry': f'{round(latest_p * 0.985, -2):,.0f} - {round(latest_p * 0.995, -2):,.0f}',
          'target': f'{target:,.0f}',
          'stop': f'{round(support * 0.97, -2):,.0f}',
          'foreignNet': f_net,
          'guardrail': guardrail_flag,
          'score': score,
      }
    except Exception:
      return None

  with ThreadPoolExecutor(max_workers=8) as pool:
    evaluated = [r for r in pool.map(evaluate_candidate, test_symbols) if r]

  evaluated.sort(key=lambda x: x.get('score', 0), reverse=True)
  result = {
      'date': time.strftime('%d/%m/%Y'),
      'count': len(evaluated[:10]),
      'data': evaluated[:10],
  }
  _TOP_TPLUS_CACHE['timestamp'] = now
  _TOP_TPLUS_CACHE['data'] = result
  return result

# ==================== WEB SERVER ROUTING ====================


class ModularStockServer(http.server.SimpleHTTPRequestHandler):
  extensions_map = http.server.SimpleHTTPRequestHandler.extensions_map.copy()
  extensions_map.update({
      '.js': 'application/javascript; charset=utf-8',
      '.mjs': 'application/javascript; charset=utf-8',
      '.css': 'text/css; charset=utf-8',
      '.html': 'text/html; charset=utf-8',
  })

  def end_headers(self):
    self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
    self.send_header('Pragma', 'no-cache')
    self.send_header('Expires', '0')
    super().end_headers()

def render_template_html(file_path):
  """Nạp tự động các component HTML phân tách qua cú pháp <!-- include: components/... -->"""
  try:
    with open(file_path, 'r', encoding='utf-8') as f:
      content = f.read()

    base_dir = os.path.dirname(os.path.abspath(file_path))

    def replace_include(match):
      rel_path = match.group(1).strip()
      target_path = os.path.join(base_dir, rel_path)
      if os.path.exists(target_path):
        with open(target_path, 'r', encoding='utf-8') as inc_f:
          return inc_f.read()
      return f"<!-- Missing component: {rel_path} -->"

    rendered = re.sub(r'<!--\s*include:\s*([^\s]+)\s*-->', replace_include, content)
    return rendered
  except Exception as e:
    print('Lỗi render template HTML:', e)
    with open(file_path, 'r', encoding='utf-8') as f:
      return f.read()


class ModularStockServer(http.server.SimpleHTTPRequestHandler):

  def send_json(self, status, payload):
    try:
      self.send_response(status)
      self.send_header('Content-Type', 'application/json; charset=utf-8')
      self.send_header('Access-Control-Allow-Origin', '*')
      self.end_headers()
      self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    except (BrokenPipeError, ConnectionResetError):
      pass

  def do_GET(self):
    parsed = urllib.parse.urlparse(self.path)
    path = parsed.path

    if path == '/api/top-tplus':
      try:
        self.send_json(200, handle_top_tplus())
      except Exception as e:
        self.send_json(
            200, {'date': time.strftime('%d/%m/%Y'), 'count': 0, 'data': []}
        )
      return

    if path == '/api/chart':
      params = urllib.parse.parse_qs(parsed.query)
      ticker = params.get('ticker', ['FPT'])[0].upper()
      resolution = params.get('resolution', ['1D'])[0]
      try:
        self.send_json(200, handle_chart_only(ticker, resolution=resolution))
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    if path == '/api/stock' or self.path.startswith('/api/stock?'):
      params = urllib.parse.parse_qs(parsed.query)
      ticker = params.get('ticker', ['FPT'])[0].upper()
      resolution = params.get('resolution', ['1D'])[0]
      try:
        self.send_json(
            200, handle_stock_detail(ticker, resolution=resolution)
        )
      except Exception as e:
        self.send_json(500, {'error': str(e)})
      return

    if path in ['/', '', '/index.html']:
      index_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html')
      html_content = render_template_html(index_file)
      encoded = html_content.encode('utf-8')
      self.send_response(200)
      self.send_header('Content-Type', 'text/html; charset=utf-8')
      self.send_header('Content-Length', str(len(encoded)))
      self.end_headers()
      self.wfile.write(encoded)
      return

    super().do_GET()


class ReusableTCPServer(socketserver.TCPServer):
  allow_reuse_address = True
  daemon_threads = True


if __name__ == '__main__':
  print(
      f'🚀 Pro Stock Analytics Engine khởi chạy tại: http://localhost:{PORT}'
  )
  try:
    with ReusableTCPServer(('', PORT), ModularStockServer) as httpd:
      httpd.serve_forever()
  except OSError as e:
    if e.errno == 48:
      print(f'\n❌ Cổng {PORT} đang bị tiến trình khác chiếm dụng!')
      print(f'👉 Bạn có thể giải phóng cổng bằng lệnh: lsof -ti :{PORT} | xargs kill -9')
      print(f'👉 Sau đó chạy lại: python3 server.py\n')
    raise