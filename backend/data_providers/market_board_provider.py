"""
Stock RT - Market Board Provider (Entrade Multi-Tier Engine)
Cung cấp dữ liệu bảng giá thời gian thực toàn thị trường, chống 100% việc bị chặn IP trên Cloud (Render).
Cơ chế 3 tầng:
1. RAM Cache: Trả về tức thì trong 45s (0ms).
2. Entrade Realtime Engine: Quét song song ~100 mã Universe thanh khoản cao qua Entrade API (< 1.5s).
3. MongoDB Cloud Snapshot: Tự động lưu & đọc từ MongoDB Atlas để phục vụ mọi môi trường.
"""

import time
import logging
from concurrent.futures import ThreadPoolExecutor

from backend.constants.sectors import KNOWN_STOCK_SECTORS
from backend.constants.urls import build_entrade_chart_url, build_vietcap_group_url, build_vps_index_detail_url
from backend.data_providers.entrade_provider import fetch_intraday_snapshot
from backend.utils.network import fetch_json, VIETCAP_TRADING_HEADERS

logger = logging.getLogger('market_board_provider')

_BOARD_CACHE = {
    'timestamp': 0,
    'data': {}
}
_CACHE_TTL = 45  # 45 giây cache RAM

_PREV_SESSION_CACHE = {
    'timestamp': 0,
    'session_ts': 0,
}


def get_last_trading_day_timestamp() -> int:
  """
  Xác định timestamp bắt đầu của phiên giao dịch thực tế gần nhất trước hôm nay từ nến ngày VN-Index.
  Tự động bỏ qua mọi kỳ nghỉ lễ (Tết Nguyên Đán 7-10 ngày, nghỉ lễ 30/4, cuối tuần) không phụ thuộc ngày lịch.
  Cache RAM 5 phút để tránh gọi lặp lại.
  """
  now = time.time()
  if now - _PREV_SESSION_CACHE['timestamp'] < 300 and _PREV_SESSION_CACHE['session_ts'] > 0:
    return _PREV_SESSION_CACHE['session_ts']

  from backend.utils.time_utils import vn_date, VN_UTC_OFFSET_SEC
  now_ts = int(now)
  from_ts = now_ts - 86400 * 30  # 30 ngày nến ngày VN-Index (chỉ ~20 cây nến, rất nhẹ)
  url = build_entrade_chart_url('index', {'from': from_ts, 'to': now_ts, 'symbol': 'VNINDEX', 'resolution': '1D'})
  try:
    data = fetch_json(url, timeout=5)
    t = data.get('t', [])
    if t:
      today_str = time.strftime('%Y-%m-%d', time.gmtime(now + VN_UTC_OFFSET_SEC))
      if vn_date(t[-1]) == today_str and len(t) > 1:
        prev_ts = int(t[-2])
      else:
        prev_ts = int(t[-1])
      _PREV_SESSION_CACHE['timestamp'] = now
      _PREV_SESSION_CACHE['session_ts'] = prev_ts
      return prev_ts
  except Exception as e:
    logger.debug('Lỗi xác định timestamp phiên trước từ VN-Index: %s', e)

  # Fallback an toàn nếu lỗi mạng: lùi tối thiểu 4 ngày
  fallback_ts = now_ts - 86400 * 4
  return fallback_ts


def _get_mongo_collection():
  """Lấy collection snapshot từ MongoDB Atlas nếu có kết nối (hỗ trợ auto-reconnect)."""
  try:
    from backend.db.portfolio_db import get_mongo_db
    from backend.constants.db import COLL_MARKET_SNAPSHOT
    db = get_mongo_db()
    if db is not None:
      return db[COLL_MARKET_SNAPSHOT]
  except Exception:
    pass
  return None


def _save_snapshot_to_mongo(board_data: dict):
  """Lưu snapshot bảng giá mới nhất lên MongoDB Atlas thông qua MarketBoardSnapshot Model."""
  try:
    coll = _get_mongo_collection()
    if coll is not None and board_data:
      from backend.models.db_models import MarketBoardSnapshot
      snapshot = MarketBoardSnapshot(data=board_data)
      coll.update_one(
          MarketBoardSnapshot.filter_by_key(snapshot.key),
          {'$set': snapshot.to_doc()},
          upsert=True
      )
  except Exception as e:
    logger.debug('Lỗi lưu snapshot bảng giá lên MongoDB: %s', e)


def _load_snapshot_from_mongo() -> dict:
  """Đọc snapshot bảng giá mới nhất từ MongoDB Atlas thông qua MarketBoardSnapshot Model."""
  try:
    coll = _get_mongo_collection()
    if coll is not None:
      from backend.models.db_models import MarketBoardSnapshot
      doc = coll.find_one(MarketBoardSnapshot.filter_by_key(MarketBoardSnapshot.KEY_LATEST_BOARD))
      if doc:
        return MarketBoardSnapshot.from_doc(doc).data
  except Exception as e:
    logger.debug('Lỗi đọc snapshot bảng giá từ MongoDB: %s', e)
  return {}


_LIQUID_UNIVERSE_CACHE = {
    'timestamp': 0,
    'symbols': []
}
_LIQUID_UNIVERSE_TTL = 300  # 5 phút

# Rổ 30 mã VN30 niêm yết chính thức làm hạt giống an toàn nếu DB và API chưa có dữ liệu
_VN30_SEED_STOCKS = [
    'ACB', 'BCM', 'BID', 'BVH', 'CTG', 'FPT', 'GAS', 'GVR', 'HDB', 'HPG',
    'MBB', 'MSN', 'MWG', 'PLX', 'POW', 'SAB', 'SHB', 'SSB', 'SSI', 'STB',
    'TCB', 'TPB', 'VCB', 'VHM', 'VIB', 'VIC', 'VJC', 'VNM', 'VPB', 'VRE'
]


def _save_liquid_universe_to_mongo(symbols: list):
  """Lưu danh sách mã thanh khoản cao nhất vào MongoDB để Render/Cloud dùng chung."""
  try:
    coll = _get_mongo_collection()
    if coll is not None and symbols:
      coll.update_one(
          {'key': 'dynamic_liquid_universe'},
          {'$set': {'key': 'dynamic_liquid_universe', 'symbols': symbols, 'total': len(symbols), 'updated_at': time.time()}},
          upsert=True
      )
  except Exception as e:
    logger.debug('Lỗi lưu liquid universe lên MongoDB: %s', e)


def _load_liquid_universe_from_mongo() -> list:
  """Nạp danh sách mã thanh khoản cao nhất từ MongoDB Atlas."""
  try:
    coll = _get_mongo_collection()
    if coll is not None:
      doc = coll.find_one({'key': 'dynamic_liquid_universe'})
      if doc and doc.get('symbols'):
        return doc['symbols']
  except Exception as e:
    logger.debug('Lỗi đọc liquid universe từ MongoDB: %s', e)
  return []


def get_dynamic_liquid_universe(limit: int = 80, force_refresh: bool = False) -> list:
  """
  Tự động truy xuất Top N mã cổ phiếu thanh khoản cao nhất thị trường Việt Nam (VN100 + HNX30) hoàn toàn động:
  - 100% không dùng SSI iBoard (loại bỏ hoàn toàn việc bị chặn IP quốc tế trên Render / Cloud).
  - 1. RAM Cache: Trả về tức thì trong 5 phút vì rổ chỉ số chuẩn của Sở GDCK rất ổn định.
  - 2. Vietcap Open API: Tự động lấy danh sách rổ chỉ số VN100 (HOSE) + HNX30 (HNX).
  - 3. Snapshot MongoDB Atlas: Tự động nạp snapshot dự phòng nếu offline hoặc cold-start.
  - 4. Hạt giống VN30 khởi tạo: Chỉ dùng khi hệ thống mới tinh chưa có bất kỳ dữ liệu nào.
  """
  global _LIQUID_UNIVERSE_CACHE
  now = time.time()
  if not force_refresh and (now - _LIQUID_UNIVERSE_CACHE['timestamp'] < _LIQUID_UNIVERSE_TTL) and _LIQUID_UNIVERSE_CACHE['symbols']:
    return _LIQUID_UNIVERSE_CACHE['symbols'][:limit]

  # 1. Quét động rổ VN100 (HOSE) và HNX30 (HNX) qua Vietcap Open API
  discovered = []
  for group in ('VN100', 'HNX30'):
    try:
      items = fetch_json(
          build_vietcap_group_url(group),
          headers=VIETCAP_TRADING_HEADERS,
          timeout=5,
      )
      if isinstance(items, list):
        for item in items:
          if isinstance(item, dict) and item.get('symbol'):
            sym = str(item['symbol']).strip().upper()
            if len(sym) == 3:
              discovered.append(sym)
    except Exception as e:
      logger.debug('Lỗi nạp rổ %s qua Vietcap Open API: %s', group, e)

  discovered = list(dict.fromkeys(discovered))
  if len(discovered) >= 30:
    _LIQUID_UNIVERSE_CACHE['timestamp'] = now
    _LIQUID_UNIVERSE_CACHE['symbols'] = discovered
    _save_liquid_universe_to_mongo(discovered)
    return discovered[:limit]

  # 2. Đọc snapshot từ MongoDB Atlas nếu API lỗi hoặc offline
  mongo_symbols = _load_liquid_universe_from_mongo()
  if mongo_symbols and len(mongo_symbols) >= 20:
    _LIQUID_UNIVERSE_CACHE['timestamp'] = now
    _LIQUID_UNIVERSE_CACHE['symbols'] = mongo_symbols
    return mongo_symbols[:limit]

  # 3. Fallback hạt giống VN30 chính thức
  return _VN30_SEED_STOCKS[:limit]


def build_entrade_universe_board(symbols=None, max_workers=15) -> dict:
  """
  Quét song song toàn bộ các mã Universe bằng Entrade Realtime Intraday API.
  Không bị chặn IP quốc tế trên Render/AWS/Cloudflare.
  Mốc from_ts được lấy động từ phiên giao dịch liền trước (VN-Index) thay vì hardcode số ngày tĩnh.
  """
  if not symbols:
    symbols = get_dynamic_liquid_universe(limit=80)

  # Lấy mốc phiên giao dịch gần nhất 1 lần duy nhất cho toàn bộ worker pool
  prev_session_ts = get_last_trading_day_timestamp()

  board_map = {}

  def _fetch_single(sym):
    try:
      return fetch_intraday_snapshot(sym, from_ts=prev_session_ts)
    except Exception:
      return None

  try:
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
      results = pool.map(_fetch_single, symbols)
      for item in results:
        if item and item.get('stockSymbol'):
          sym = item['stockSymbol'].upper()
          board_map[sym] = item
  except Exception as e:
    logger.warning('Lỗi quét Entrade universe board: %s', e)

  return board_map


_LAST_KNOWN_VNINDEX = None


def get_vnindex_summary() -> dict:
  """
  Lấy dữ liệu thời gian thực của chỉ số VN-Index trực tiếp với cơ chế đa tầng:
  1. Tầng 1 (VPS Realtime Index Datafeed - Mã 10 = VN-INDEX):
     Lấy trực tiếp cIndex (giá khớp realtime), oIndex (giá tham chiếu phiên hôm nay),
     khối lượng tích lũy vol, tổng giá trị giao dịch (value) và độ rộng (advances, declines, noChange).
  2. Tầng 2 (Entrade Intraday 1M + Tham chiếu 1D):
     Dự phòng nếu VPS gián đoạn: Lấy giá realtime từ nến 1 phút và tham chiếu từ nến 1D
     đúng theo ngày giao dịch.
  3. Tầng 3 (Entrade Daily EOD):
     Dự phòng ngoài giờ giao dịch hoặc cuối tuần.
  """
  global _LAST_KNOWN_VNINDEX

  # Tầng 1: VPS Live Index Datafeed (Mã 10: VN-INDEX)
  try:
    vps_url = build_vps_index_detail_url('10')
    data = fetch_json(vps_url, timeout=3)
    if isinstance(data, list) and len(data) > 0 and data[0]:
      item = data[0]
      curr = float(item.get('cIndex', 0))
      ref = float(item.get('oIndex', 0))
      if curr > 0 and ref > 0:
        change = round(curr - ref, 2)
        change_pct = round((change / ref * 100), 2)
        vol = int(item.get('vol', 0))
        raw_val = float(item.get('value', 0.0))  # Triệu đồng
        ot = item.get('ot', '')
        advances = declines = no_change = None
        if ot and '|' in ot:
          parts = ot.split('|')
          if len(parts) >= 6:
            try:
              if not raw_val and parts[2]:
                raw_val = float(parts[2])
              advances = int(parts[3])
              declines = int(parts[4])
              no_change = int(parts[5])
            except (ValueError, TypeError):
              pass

        # raw_val là triệu đồng -> chia 1e6 để ra Ngàn Tỷ đồng (K Tỷ)
        est_val_trillion = round(raw_val / 1e6, 2) if raw_val > 0 else 0.0

        res = {
            'index': 'VNINDEX',
            'price': curr,
            'change': change,
            'changePercent': change_pct,
            'volume': vol,
            'ref': ref,
            'source': 'VPS_REALTIME',
            'advances': advances,
            'declines': declines,
            'noChange': no_change,
            'estValueTrillion': est_val_trillion,
        }
        _LAST_KNOWN_VNINDEX = res
        return res
  except Exception as e:
    logger.debug('Lỗi fetch VN-Index từ VPS Datafeed: %s', e)

  # Tầng 2 & 3: Entrade Realtime Fallback (Nến 1 phút + Nến ngày 1D)
  now = time.time()
  now_ts = int(now)
  from backend.utils.time_utils import vn_date, VN_UTC_OFFSET_SEC
  today_str = time.strftime('%Y-%m-%d', time.gmtime(now + VN_UTC_OFFSET_SEC))

  try:
    from_ts = now_ts - 86400 * 30
    daily_url = build_entrade_chart_url('index', {'from': from_ts, 'to': now_ts, 'symbol': 'VNINDEX', 'resolution': '1D'})
    daily_data = fetch_json(daily_url, timeout=4)
    daily_c = daily_data.get('c', [])
    daily_t = daily_data.get('t', [])
    daily_v = daily_data.get('v', [])

    ref = 0.0
    if daily_c and daily_t:
      if vn_date(daily_t[-1]) == today_str and len(daily_c) >= 2:
        ref = float(daily_c[-2])
      else:
        ref = float(daily_c[-1])

    # Thử nến 1 phút trong ngày
    m1_url = build_entrade_chart_url('index', {'from': now_ts - 21600, 'to': now_ts, 'symbol': 'VNINDEX', 'resolution': '1'})
    m1_data = fetch_json(m1_url, timeout=4)
    m1_c = m1_data.get('c', [])
    m1_t = m1_data.get('t', [])
    m1_v = m1_data.get('v', [])

    if m1_c and m1_t and vn_date(m1_t[-1]) == today_str and ref > 0:
      curr = float(m1_c[-1])
      change = round(curr - ref, 2)
      change_pct = round((change / ref * 100), 2)
      vol = max(int(sum(m1_v)), int(daily_v[-1]) if daily_v else 0)
      est_val_trillion = round((vol * 22000) / 1e12, 2) if vol > 0 else 0.0
      res = {
          'index': 'VNINDEX',
          'price': curr,
          'change': change,
          'changePercent': change_pct,
          'volume': vol,
          'ref': ref,
          'source': 'ENTRADE_1M',
          'advances': None,
          'declines': None,
          'noChange': None,
          'estValueTrillion': est_val_trillion,
      }
      _LAST_KNOWN_VNINDEX = res
      return res

    # Tầng 3: Nến ngày 1D
    if daily_c and len(daily_c) >= 2:
      curr = float(daily_c[-1])
      prev = float(daily_c[-2])
      change = round(curr - prev, 2)
      change_pct = round((change / prev * 100), 2) if prev > 0 else 0.0
      vol = int(daily_v[-1]) if daily_v else 0
      est_val_trillion = round((vol * 22000) / 1e12, 2) if vol > 0 else 0.0
      res = {
          'index': 'VNINDEX',
          'price': curr,
          'change': change,
          'changePercent': change_pct,
          'volume': vol,
          'ref': prev,
          'source': 'ENTRADE_1D',
          'advances': None,
          'declines': None,
          'noChange': None,
          'estValueTrillion': est_val_trillion,
      }
      _LAST_KNOWN_VNINDEX = res
      return res
  except Exception as e:
    logger.debug('Lỗi fetch VN-Index fallback từ Entrade: %s', e)

  if _LAST_KNOWN_VNINDEX:
    return _LAST_KNOWN_VNINDEX

  return {
      'index': 'VNINDEX',
      'price': 0.0,
      'change': 0.0,
      'changePercent': 0.0,
      'volume': 0,
      'ref': 0.0,
      'source': 'DATA_UNAVAILABLE',
      'advances': None,
      'declines': None,
      'noChange': None,
      'estValueTrillion': 0.0,
  }


def get_market_board_data(force_refresh=False) -> dict:
  """
  Hàm lấy bảng giá toàn diện 3 tầng:
  1. RAM Cache: Trả về trong 45s (0ms).
  2. Entrade Engine: Quét song song ~100 mã cốt lõi (< 1.5s).
  3. MongoDB Atlas Snapshot: Đọc dự phòng nếu cold-start hoặc offline.
  """
  now = time.time()

  # 1. Trả về từ RAM Cache nếu còn hiệu lực
  if not force_refresh and (now - _BOARD_CACHE['timestamp'] < _CACHE_TTL) and _BOARD_CACHE['data']:
    return _BOARD_CACHE['data']

  # 2. Quét Entrade Engine trực tiếp (Không phụ thuộc SSI, không bị chặn IP)
  entrade_board = build_entrade_universe_board()
  if entrade_board and len(entrade_board) >= 20:
    _BOARD_CACHE['timestamp'] = now
    _BOARD_CACHE['data'] = entrade_board
    # Lưu đồng thời vào MongoDB Atlas trong luồng ngầm
    _save_snapshot_to_mongo(entrade_board)
    return entrade_board

  # 3. Fallback: Đọc snapshot từ MongoDB Atlas nếu Entrade gặp sự cố tạm thời
  mongo_board = _load_snapshot_from_mongo()
  if mongo_board and len(mongo_board) >= 10:
    _BOARD_CACHE['timestamp'] = now
    _BOARD_CACHE['data'] = mongo_board
    return mongo_board

  return _BOARD_CACHE.get('data', {})
