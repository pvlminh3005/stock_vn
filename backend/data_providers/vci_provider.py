"""
Stock RT - VCI (Vietcap) Data Provider
Cung cấp dữ liệu báo cáo tài chính hàng quý, bảng cân đối, dòng tiền và lịch sử định giá.
"""
import io
import json
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from backend.constants.config import (
    DB_PATH,
    VCI_HISTORY_KEEP_QUARTERS,
    _VCI_RATIO_FIELDS,
    _VCI_BS_FIELDS,
    _VCI_CF_FIELDS,
)
from backend.utils.network import vnstock_call
from backend.utils.ohlc_helpers import period_key, expected_latest_report_period

def _latest(series, periods):
  """Giá trị của kỳ gần nhất có dữ liệu."""
  for p in reversed(periods):
    if p in series and series[p] is not None:
      return series[p], p
  return None, None

def _vci_quarterly_report(symbol, report_type, fields):
  """
  Đọc báo cáo theo quý từ VCI (vnstock), trả về {tên_trường: {kỳ 'YYYY-Qn': giá trị}}.
  Dùng API nội bộ _get_report(limit=200) vì Finance.ratio() công khai chỉ trả 4 kỳ đầu tiên.
  """
  from vnstock.explorer.vci.financial import Finance as VCIFinance
  df = vnstock_call(lambda: VCIFinance(symbol=symbol, period='quarter')._get_report(
      report_type=report_type, lang='vi', mode='final', style='readable',
      show_log=False, period='quarter', limit=200, get_all=False,
  ))
  if df is None or df.empty or 'item_id' not in df.columns:
    return {}
  period_cols = [c for c in df.columns if period_key(c)]
  out = {}
  for _, row in df.iterrows():
    key = fields.get(row['item_id'])
    if not key:
      continue
    series = out.setdefault(key, {})
    for col in period_cols:
      try:
        val = float(row[col])
      except (TypeError, ValueError):
        continue
      if val != val:
        continue
      # Một số khoản mục bị lặp (dòng tổng và dòng chi tiết): giữ giá trị tuyệt đối lớn nhất
      if col not in series or abs(val) > abs(series[col]):
        series[col] = val
  return out

def fetch_vci_financial_history(symbol):
  """Tải lịch sử chỉ số định giá, bảng cân đối và dòng tiền theo quý từ VCI."""
  old_stdout, old_stderr = sys.stdout, sys.stderr
  sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
  try:
    with ThreadPoolExecutor(max_workers=3) as pool:
      f_ratio = pool.submit(_vci_quarterly_report, symbol, 'ratio', _VCI_RATIO_FIELDS)
      f_bs = pool.submit(_vci_quarterly_report, symbol, 'balance_sheet', _VCI_BS_FIELDS)
      f_cf = pool.submit(_vci_quarterly_report, symbol, 'cash_flow', _VCI_CF_FIELDS)
      data = {}
      partial = False
      for fut in (f_ratio, f_bs, f_cf):
        try:
          part = fut.result()
        except BaseException:
          part = None
        if part is None:
          partial = True
        data.update(part or {})
    periods = sorted({p for series in data.values() for p in series}, key=period_key)
    if not periods or 'pe' not in data:
      return None
    periods = periods[-VCI_HISTORY_KEEP_QUARTERS:]
    return {
        'periods': periods,
        'series': {k: {p: v[p] for p in periods if p in v} for k, v in data.items()},
        'latestPeriod': periods[-1],
        'partial': partial,
    }
  except Exception:
    return None
  finally:
    sys.stdout, sys.stderr = old_stdout, old_stderr

def get_vci_financial_history(symbol):
  """
  Lịch sử VCI có cache SQLite: dùng lại nếu tải trong 1 ngày, hoặc trong 7 ngày và đã có kỳ BCTC
  quá hạn công bố gần nhất (mùa BCTC sẽ tự tải lại khi kỳ mới đến hạn).
  """
  sym = symbol.upper()
  now = int(time.time())
  expected = expected_latest_report_period()
  try:
    with sqlite3.connect(DB_PATH) as conn:
      row = conn.execute(
          'SELECT payload, latest_period, updated_at FROM vci_history WHERE symbol = ?', (sym,)
      ).fetchone()
    if row:
      payload, latest_period, updated_at = row
      age = now - updated_at
      period_ok = expected is None or (period_key(latest_period) or (0, 0)) >= expected
      if age < 86400 or (age < 604800 and period_ok):
        return json.loads(payload)
  except Exception as e:
    print(f'Lỗi đọc cache vci_history {sym}:', e)

  hist = fetch_vci_financial_history(sym)
  # Không cache bản thiếu để lần sau tải lại đủ
  if hist and not hist.get('partial'):
    try:
      with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            'INSERT OR REPLACE INTO vci_history (symbol, payload, latest_period, updated_at) VALUES (?, ?, ?, ?)',
            (sym, json.dumps(hist), hist['latestPeriod'], now),
        )
    except Exception as e:
      print(f'Lỗi ghi cache vci_history {sym}:', e)
  return hist

def summarize_vci_history(hist):
  """Rút trích số liệu kỳ gần nhất từ lịch sử VCI: EPS/BVPS đã điều chỉnh số cổ phiếu, ROE TTM, nợ vay, thanh khoản."""
  if not hist:
    return None
  periods = hist['periods']
  s = hist['series']
  pe, pe_period = _latest(s.get('pe', {}), periods)
  pb, _ = _latest(s.get('pb', {}), periods)
  ps, _ = _latest(s.get('ps', {}), periods)
  gross_m, _ = _latest(s.get('grossMargin', {}), periods)
  net_m, _ = _latest(s.get('netMargin', {}), periods)
  cap, _ = _latest(s.get('marketCap', {}), periods)
  shares, _ = _latest(s.get('shares', {}), periods)
  roe, _ = _latest(s.get('roe', {}), periods)
  # Giá tham chiếu kỳ = vốn hóa / số cổ phiếu lưu hành; EPS & BVPS suy ra cùng nguồn với P/E, P/B
  ref_price = cap / shares if cap and shares else None
  eps = ref_price / pe if ref_price and pe else None
  bvps = ref_price / pb if ref_price and pb else None

  def _bs(key):
    val, _ = _latest(s.get(key, {}), periods)
    return val or 0.0

  cash, short_inv = _bs('cash'), _bs('shortInvestments')
  short_debt, long_debt, equity = _bs('shortBorrowings'), _bs('longBorrowings'), _bs('equity')
  cfo_series = s.get('cfo', {})
  cfo_periods = [p for p in periods if p in cfo_series][-4:]
  cfo_ttm = sum(cfo_series[p] for p in cfo_periods) if len(cfo_periods) == 4 else None
  cfo_latest = cfo_series[cfo_periods[-1]] if cfo_periods else None

  roe_series = s.get('roe', {})
  roe_periods = [p for p in periods if p in roe_series]
  roe_4q_ago = roe_series[roe_periods[-5]] if len(roe_periods) >= 5 else None

  return {
      'period': pe_period,
      'pe': pe,
      'pb': pb,
      'ps': ps,
      'grossMargin': gross_m,
      'netMargin': net_m,
      'eps': eps,
      'bvps': bvps,
      'roe': roe * 100 if roe is not None else None,
      'roe4QAgo': roe_4q_ago * 100 if roe_4q_ago is not None else None,
      'borrowDE': ((short_debt + long_debt) / equity) if equity > 0 else None,
      'cash': cash,
      'shortInvestments': short_inv,
      'shortBorrowings': short_debt,
      'cfoTtm': cfo_ttm,
      'cfoLatest': cfo_latest,
      'npl': _latest(s.get('npl', {}), periods)[0],
      'nplCoverage': _latest(s.get('nplCoverage', {}), periods)[0],
      'casa': _latest(s.get('casa', {}), periods)[0],
  }
