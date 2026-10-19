"""
Stock RT - Quản lý Lưu trữ Cơ sở Dữ liệu SQLite & Bộ nhớ Cache
"""
import os
import sqlite3
import time
from backend.constants.config import DB_PATH

_MEM_FUNDAMENTALS_CACHE = {}

def init_all_db():
  """Khởi tạo toàn bộ các bảng trong SQLite fundamentals.db."""
  try:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
      # 1. Bảng fundamentals
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
          ('report_period', "TEXT DEFAULT ''"),
      ]:
        try:
          conn.execute(f"ALTER TABLE fundamentals ADD COLUMN {col} {col_def}")
        except Exception:
          pass

      # 2. Bảng vci_history
      conn.execute("""
        CREATE TABLE IF NOT EXISTS vci_history (
            symbol TEXT PRIMARY KEY,
            payload TEXT,
            latest_period TEXT,
            updated_at INTEGER
        )
      """)
  except Exception as e:
    print('Lỗi khởi tạo DB SQLite:', e)

# Khởi tạo tự động khi import module
init_all_db()
init_db = init_all_db

def get_cached_fundamental(symbol):
  """Lấy hồ sơ cơ bản từ cache bộ nhớ hoặc SQLite."""
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
          ' interest_coverage, ocf_status, nim, ldr, report_period FROM fundamentals WHERE symbol = ?',
          (sym,),
      )
      row = cur.fetchone()
      if row:
        updated_at = row[10]
        if time.time() - updated_at < 604800:
          has_advanced = (len(row) > 13 and (row[12] or row[13] or (len(row) > 17 and row[17]))) or (len(row) > 16 and row[16])
          if not has_advanced or not row[19]:
            # Bản ghi cũ thiếu dữ liệu nâng cao hoặc chưa lưu kỳ BCTC, trả về None để fetch mới
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
              'reportPeriod': row[19],
              'isAudited': bool(row[2] or row[3] or row[4] or row[5]),
          }
          _MEM_FUNDAMENTALS_CACHE[sym] = (data, updated_at)
          return data
  except Exception as e:
    print(f'Lỗi đọc cache SQLite {sym}:', e)

  return None

def save_cached_fundamental(symbol, data):
  """Lưu hồ sơ cơ bản vào cache bộ nhớ và SQLite."""
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
                ocf, gross_margin, net_margin, interest_coverage, ocf_status, nim, ldr,
                report_period
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
              data.get('reportPeriod', ''),
          ),
      )
  except Exception as e:
    print(f'Lỗi ghi cache SQLite {sym}:', e)
