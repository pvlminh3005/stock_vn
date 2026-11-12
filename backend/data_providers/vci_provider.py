"""
Stock RT - VCI (Vietcap) Data Provider
Cung cấp dữ liệu báo cáo tài chính hàng quý, bảng cân đối, dòng tiền và lịch sử định giá từ Vietcap IQ API.
"""
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from backend.constants.config import (
    VCI_HISTORY_KEEP_QUARTERS,
    _VCI_RATIO_FIELDS,
    _VCI_BS_FIELDS,
    _VCI_CF_FIELDS,
)
from backend.constants.urls import (
    build_vietcap_financial_statement_url,
    build_vietcap_statistics_url,
)
from backend.utils.network import fetch_json, VIETCAP_IQ_HEADERS
from backend.utils.ohlc_helpers import period_key, expected_latest_report_period


def _get_vci_mongo():
  """Lấy collection vci_history từ MongoDB Atlas (hỗ trợ auto-reconnect)."""
  try:
    from backend.db.portfolio_db import get_mongo_db
    from backend.constants.db import COLL_VCI_HISTORY
    db = get_mongo_db()
    if db is not None:
      return db[COLL_VCI_HISTORY]
  except Exception:
    pass
  return None

def _latest(series, periods):
  """Giá trị của kỳ gần nhất có dữ liệu."""
  for p in reversed(periods):
    if p in series and series[p] is not None:
      return series[p], p
  return None, None

def _parse_vietcap_quarters(rows, fields, quarter_key='lengthReport'):
  """Chuẩn hóa danh sách các kỳ quý từ Vietcap IQ JSON sang {tên_trường: {kỳ 'YYYY-Qn': giá trị}}."""
  out = {}
  for row in rows:
    if not isinstance(row, dict):
      continue
    yr = row.get('yearReport')
    qt = row.get(quarter_key)
    try:
      yr_int = int(yr)
      qt_int = int(qt)
    except (TypeError, ValueError):
      continue
    if qt_int not in (1, 2, 3, 4):
      continue
    col = f'{yr_int}-Q{qt_int}'
    if not period_key(col):
      continue
    for src_key, target_key in fields.items():
      raw_val = row.get(src_key)
      if raw_val is None:
        continue
      try:
        val = float(raw_val)
      except (TypeError, ValueError):
        continue
      if not math.isfinite(val):
        continue
      series = out.setdefault(target_key, {})
      if col not in series or abs(val) > abs(series[col]):
        series[col] = val
  return out


def _vci_quarterly_report(symbol, report_type, fields):
  """
  Đọc báo cáo theo quý trực tiếp từ Vietcap IQ API, trả về {tên_trường: {kỳ 'YYYY-Qn': giá trị}}.
  Trả về None nếu lỗi mạng hoặc API lỗi (để tránh lưu cache thiếu dữ liệu).
  """
  try:
    if report_type == 'ratio':
      resp = fetch_json(
          build_vietcap_statistics_url(symbol),
          headers=VIETCAP_IQ_HEADERS,
          timeout=8,
      )
      if not isinstance(resp, dict) or resp.get('status') != 200 or not isinstance(resp.get('data'), list):
        return None
      return _parse_vietcap_quarters(resp['data'], fields, quarter_key='quarter')

    section = 'BALANCE_SHEET' if report_type == 'balance_sheet' else 'CASH_FLOW'
    resp = fetch_json(
        build_vietcap_financial_statement_url(symbol, section),
        headers=VIETCAP_IQ_HEADERS,
        timeout=8,
    )
    data = resp.get('data') if isinstance(resp, dict) else None
    quarters = data.get('quarters') if isinstance(data, dict) else None
    if not isinstance(resp, dict) or resp.get('status') != 200 or not isinstance(quarters, list):
      return None
    return _parse_vietcap_quarters(quarters, fields, quarter_key='lengthReport')
  except Exception:
    return None


def fetch_vci_financial_history(symbol):
  """Tải lịch sử chỉ số định giá, bảng cân đối và dòng tiền theo quý từ Vietcap IQ (VCI)."""
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
        except Exception:
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

def get_vci_financial_history(symbol):
  """
  Lịch sử VCI có cache MongoDB: dùng lại nếu tải trong 1 ngày, hoặc trong 7 ngày và đã có kỳ BCTC
  quá hạn công bố gần nhất (mùa BCTC sẽ tự tải lại khi kỳ mới đến hạn).
  """
  sym = symbol.upper()
  now = int(time.time())
  expected = expected_latest_report_period()
  coll = _get_vci_mongo()

  if coll is not None:
    try:
      from backend.models.db_models import VciHistoryItem
      doc = coll.find_one(VciHistoryItem.filter_by_symbol(sym))
      if doc:
        item = VciHistoryItem.from_doc(doc)
        from backend.utils.datetime_helpers import to_timestamp_int
        payload = item.payload
        latest_period = item.latest_period
        updated_at = to_timestamp_int(item.updated_at)
        age = now - updated_at
        period_ok = expected is None or (period_key(latest_period) or (0, 0)) >= expected
        if age < 86400 or (age < 604800 and period_ok):
          if isinstance(payload, dict):
            return payload
          elif isinstance(payload, str):
            return json.loads(payload)
    except Exception as e:
      print(f'Lỗi đọc cache vci_history {sym}:', e)

  hist = fetch_vci_financial_history(sym)
  # Không cache bản thiếu để lần sau tải lại đủ
  if hist and not hist.get('partial') and coll is not None:
    try:
      from backend.models.db_models import VciHistoryItem
      item = VciHistoryItem(
          symbol=sym,
          payload=hist,
          latest_period=hist.get('latestPeriod', ''),
          updated_at=now
      )
      coll.update_one(
          VciHistoryItem.filter_by_symbol(sym),
          {'$set': item.to_doc()},
          upsert=True
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
