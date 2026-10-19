"""
Stock RT - Market Regime & Breadth Engine
Chấm Regime thị trường theo 5 điều kiện (Risk-on, Neutral, Defensive, No-new-risk)
dựa trên VN-Index, độ rộng thị trường (Top 200 ADTV20), thanh khoản và phân kỳ chỉ số - độ rộng.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from backend.constants.config import (
    VN_UTC_OFFSET_SEC,
    REGIME_LEVELS,
)
from backend.utils.time_utils import vn_date
from backend.data_providers.entrade_provider import fetch_chart_data
from backend.data_providers.ssi_provider import get_ssi_board_data
from backend.domain.technicals import get_vnindex_series

BREADTH_UNIVERSE_SIZE = 200
BREADTH_AD_UNIVERSE_SIZE = 100
BREADTH_CANDIDATE_SIZE = 300
BREADTH_HISTORY_DAYS = 50
BREADTH_FIRST_LOAD_WAIT_SEC = 20

_BREADTH_UNIVERSE = {'date': None, 'data': None, 'loading': False}
_BREADTH_LOCK = threading.Lock()
_BREADTH_READY = threading.Event()
_REGIME_CACHE = {'time': 0, 'data': None}


def _load_breadth_universe(ssi_board, today):
  """Tải nến ngày của các mã ứng viên, chọn Top theo ADTV20 (giá trị giao dịch bình quân 20 phiên đã hoàn thành)."""
  try:
    stocks = [
        v for v in ssi_board.values()
        if v.get('stockType') == 's' and len(str(v.get('stockSymbol', ''))) == 3
    ]
    # Lọc ứng viên theo giá trị giao dịch phiên hiện tại; trước giờ mở cửa thì lấy toàn bộ mã HOSE
    traded = sorted(
        (v for v in stocks if (v.get('nmTotalTradedValue') or 0) > 0),
        key=lambda v: -(v.get('nmTotalTradedValue') or 0),
    )
    if len(traded) >= BREADTH_UNIVERSE_SIZE:
      candidates = [v['stockSymbol'] for v in traded[:BREADTH_CANDIDATE_SIZE]]
    else:
      candidates = [v['stockSymbol'] for v in stocks if v.get('exchange') == 'HOSE']

    def _fetch(sym):
      try:
        d = fetch_chart_data(sym, days=BREADTH_HISTORY_DAYS, resolution='1D')
        closes = d.get('c', [])
        if len(closes) < 21:
          return None
        scale = 1000 if closes[-1] < 1000 else 1
        dates = [vn_date(t) for t in d.get('t', [])]
        closes = [c * scale for c in closes]
        vols = d.get('v', [])
        # Chỉ giữ phiên đã hoàn thành (bỏ nến hôm nay nếu Entrade đã có)
        if dates and dates[-1] == today:
          dates, closes, vols = dates[:-1], closes[:-1], vols[:-1]
        if len(closes) < 21:
          return None
        adtv = sum(c * v for c, v in zip(closes[-20:], vols[-20:])) / 20.0
        return {'sym': sym, 'dates': dates, 'closes': closes, 'adtv': adtv}
      except Exception:
        return None

    with ThreadPoolExecutor(max_workers=8) as pool:
      rows = [r for r in pool.map(_fetch, candidates) if r]
    rows.sort(key=lambda r: -r['adtv'])
    universe = rows[:BREADTH_UNIVERSE_SIZE]
    with _BREADTH_LOCK:
      _BREADTH_UNIVERSE['date'] = today
      _BREADTH_UNIVERSE['data'] = universe
  except Exception as e:
    print('Lỗi tải universe độ rộng thị trường:', e)
  finally:
    with _BREADTH_LOCK:
      _BREADTH_UNIVERSE['loading'] = False
    _BREADTH_READY.set()


def get_breadth_universe(ssi_board):
  """Trả về (universe, ngày tạo universe). Universe được tải nền một lần mỗi ngày (không chặn request);

  trong lúc tải lại cho ngày mới vẫn dùng tạm universe ngày trước. Chưa có gì thì trả về (None, None).
  """
  today = time.strftime('%Y-%m-%d', time.gmtime(time.time() + VN_UTC_OFFSET_SEC))
  with _BREADTH_LOCK:
    if _BREADTH_UNIVERSE['date'] != today and not _BREADTH_UNIVERSE['loading'] and ssi_board:
      _BREADTH_UNIVERSE['loading'] = True
      threading.Thread(target=_load_breadth_universe, args=(ssi_board, today), daemon=True).start()
    first_load = _BREADTH_UNIVERSE['data'] is None and _BREADTH_UNIVERSE['loading']
  if first_load:
    _BREADTH_READY.wait(BREADTH_FIRST_LOAD_WAIT_SEC)
  with _BREADTH_LOCK:
    return _BREADTH_UNIVERSE['data'], _BREADTH_UNIVERSE['date']


def warm_up_market_data():
  """Tải trước bảng giá và universe độ rộng khi khởi động server để request đầu tiên có đủ regime."""
  try:
    get_breadth_universe(get_ssi_board_data())
  except Exception as e:
    print('Lỗi warm-up dữ liệu thị trường:', e)


def _sma_at(values, end, period):
  """SMA kết thúc tại vị trí end (không bao gồm end)."""
  window = values[max(0, end - period):end]
  return sum(window) / len(window) if len(window) == period else None


def evaluate_market_regime(ssi_board):
  """Chấm Regime thị trường theo 5 điều kiện (mỗi điều kiện đạt = 1 điểm):

    1. VN-Index > MA50 và độ dốc MA20 >= 0
    2. VN-Index > MA200
    3. >= 50% số mã trên MA20 (Top 200 mã ADTV20)
    4. Thanh khoản VN-Index 5 phiên >= 90% trung bình 20 phiên
    5. Không có phân kỳ chỉ số - độ rộng (rolling 5 phiên có >= 2 phiên VN-Index tăng > 0.3% nhưng A/D Top 100 < 0.8)
  Điều kiện thiếu dữ liệu tính là KHÔNG ĐẠT (thận trọng) và được ghi rõ.
  VN-Index tính theo phiên đã đóng cửa gần nhất; độ rộng dùng giá khớp realtime so với MA20 các phiên đã hoàn thành.
  """
  now = time.time()
  if _REGIME_CACHE['data'] and now - _REGIME_CACHE['time'] < 120:
    return _REGIME_CACHE['data']

  vni = get_vnindex_series()
  today = time.strftime('%Y-%m-%d', time.gmtime(now + VN_UTC_OFFSET_SEC))
  dates, closes, vols = vni.get('dates', []), vni.get('closes', []), vni.get('volumes', [])
  if dates and dates[-1] == today:
    dates, closes, vols = dates[:-1], closes[:-1], vols[:-1]

  conditions = []

  def _add(name, met, detail):
    conditions.append({'name': name, 'met': met, 'detail': detail})

  n = len(closes)
  last = closes[-1] if closes else 0
  ma20 = _sma_at(closes, n, 20)
  ma20_prev = _sma_at(closes, n - 5, 20)
  ma50 = _sma_at(closes, n, 50)
  ma200 = _sma_at(closes, n, 200)

  if ma50 is not None and ma20 is not None and ma20_prev is not None:
    slope = ma20 - ma20_prev
    _add('VN-Index > MA50 & MA20 dốc lên', last > ma50 and slope >= 0,
         f'VN-Index {last:,.1f} vs MA50 {ma50:,.1f}; MA20 {ma20:,.1f} ({slope:+,.1f} so với 5 phiên trước)')
  else:
    _add('VN-Index > MA50 & MA20 dốc lên', None, 'Chưa đủ dữ liệu VN-Index')

  if ma200 is not None:
    _add('VN-Index > MA200', last > ma200, f'VN-Index {last:,.1f} vs MA200 {ma200:,.1f}')
  else:
    _add('VN-Index > MA200', None, f'Chưa đủ 200 phiên VN-Index (có {n} phiên)')

  universe, universe_date = get_breadth_universe(ssi_board)
  stale_note = f' (universe ngày {universe_date}, đang cập nhật)' if universe and universe_date != today else ''
  if universe:
    above = 0
    counted = 0
    for u in universe:
      ma = _sma_at(u['closes'], len(u['closes']), 20)
      item = (ssi_board or {}).get(u['sym'], {})
      price = item.get('matchedPrice') or u['closes'][-1]
      if ma:
        counted += 1
        above += 1 if price > ma else 0
    pct = round(above / counted * 100, 1) if counted else 0.0
    _add('>= 50% mã trên MA20 (Top 200 ADTV)', pct >= 50.0, f'{above}/{counted} mã ({pct}%) trên MA20{stale_note}')
  else:
    _add('>= 50% mã trên MA20 (Top 200 ADTV)', None, 'Đang tải dữ liệu độ rộng thị trường, chưa đủ dữ liệu')

  if len(vols) >= 20:
    v5 = sum(vols[-5:]) / 5.0
    v20 = sum(vols[-20:]) / 20.0
    ratio = v5 / v20 if v20 else 0
    _add('Thanh khoản 5 phiên >= 90% TB20', ratio >= 0.9, f'KL 5 phiên bằng {ratio * 100:.0f}% TB20')
  else:
    _add('Thanh khoản 5 phiên >= 90% TB20', None, 'Chưa đủ dữ liệu khối lượng VN-Index')

  if universe and n >= 6:
    top = universe[:BREADTH_AD_UNIVERSE_SIZE]
    stock_maps = [dict(zip(u['dates'], u['closes'])) for u in top]
    divergent_days = []
    for i in range(n - 5, n):
      d, d_prev = dates[i], dates[i - 1]
      vni_chg = (closes[i] - closes[i - 1]) / closes[i - 1] * 100 if closes[i - 1] else 0
      adv = sum(1 for m in stock_maps if d in m and d_prev in m and m[d] > m[d_prev])
      dec = sum(1 for m in stock_maps if d in m and d_prev in m and m[d] < m[d_prev])
      ad_ratio = adv / dec if dec else float('inf')
      if vni_chg > 0.3 and ad_ratio < 0.8:
        divergent_days.append(f'{d} (VN-Index {vni_chg:+.2f}%, A/D {adv}/{dec})')
    has_div = len(divergent_days) >= 2
    detail = (
        f"Phân kỳ {len(divergent_days)}/5 phiên: {'; '.join(divergent_days)}" if divergent_days
        else 'Không có phiên phân kỳ trong 5 phiên gần nhất'
    )
    _add('Không phân kỳ chỉ số - độ rộng', not has_div,
         detail + ' (chưa kiểm tra tiêu chí đóng góp điểm của nhóm vốn hóa lớn)')
  else:
    _add('Không phân kỳ chỉ số - độ rộng', None, 'Chưa đủ dữ liệu độ rộng để kiểm tra phân kỳ')

  score = sum(1 for c in conditions if c['met'])
  missing = [c['name'] for c in conditions if c['met'] is None]
  regime, coefficient = 'NO_NEW_RISK', 0.0
  for min_score, name, coef in REGIME_LEVELS:
    if score >= min_score:
      regime, coefficient = name, coef
      break

  summary = f"Regime {regime} ({score}/5 điều kiện, hệ số risk budget {coefficient}) theo phiên {dates[-1] if dates else '--'}"
  if missing:
    summary += f"; thiếu dữ liệu: {', '.join(missing)} (tính là không đạt)"

  result = {
      'regime': regime,
      'score': score,
      'coefficient': coefficient,
      'conditions': conditions,
      'asOf': dates[-1] if dates else '',
      'missing': missing,
      'summary': summary,
  }
  if not missing and not stale_note:
    _REGIME_CACHE['time'] = now
    _REGIME_CACHE['data'] = result
  return result
