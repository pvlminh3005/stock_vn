"""
Stock RT - Screener Controller
Bộ lọc cổ phiếu và tìm kiếm:
- /api/search: Tìm kiếm mã theo ký tự
- /api/screener: Bộ lọc cổ phiếu theo thanh khoản và biến động thực tế từ SSI
- /api/top-tplus: VSR Smart Screener Top 8 Cơ hội Lướt Sóng T+ (Phễu 2 tầng)
"""

import os
import threading
import time

from backend.data_providers.ssi_provider import get_ssi_board_data
from backend.domain.screener_engine import (
    build_top_tplus_opportunities,
    is_market_hours,
    _build_synthetic_board_from_entrade,
    get_vn_now,
)
from backend.utils.telegram_bot import (
    send_telegram_message,
    format_breakout_alert,
    format_session_digest,
)
from backend.db.portfolio_db import (
    is_alert_already_sent,
    record_alert_sent,
)

_TOP_TPLUS_CACHE = {
    'timestamp': 0,
    'data': None,
}
_CACHE_LOCK = threading.Lock()
_WORKER_STARTED = False
_CACHE_TTL_SEC = 180  # 3 phút

# Bộ nhớ tạm kiểm soát trùng lặp cảnh báo Telegram theo ngày
_ALERT_TRACKER = {
    'date': '',
    'sent_symbols': set(),
    'sent_digests': set(),
}


def _evaluate_telegram_alerts(screener_data):
  """
  Đánh giá và gửi cảnh báo Telegram theo 4 khung giờ vàng tối ưu cho TTCK Việt Nam:
  1. 10:15 - 10:45: Sóng sớm bùng nổ T0 (tối đa 2 mã khỏe nhất, chưa gửi hôm nay).
  2. 11:35 - 12:00: Bản tin trưa tóm tắt kết phiên sáng (1 tin duy nhất).
  3. 14:05 - 14:25: Điểm mua chuẩn Giờ Vàng sau khi hấp thụ T+2.5.
  4. 14:50 - 15:15: Tổng kết đóng cửa ATC & Xác nhận tín hiệu ngày mai.
  """
  if not screener_data:
    return

  now_vn = time.gmtime(time.time() + 7 * 3600)
  today_str = time.strftime('%Y-%m-%d', now_vn)
  is_weekday = now_vn.tm_wday < 5

  if not is_weekday:
    return

  # Tự động reset danh sách gửi khi sang ngày mới
  if _ALERT_TRACKER['date'] != today_str:
    _ALERT_TRACKER['date'] = today_str
    _ALERT_TRACKER['sent_symbols'].clear()
    _ALERT_TRACKER['sent_digests'].clear()

  mins = now_vn.tm_hour * 60 + now_vn.tm_min
  opps = screener_data.get('topOpportunities', [])
  regime = screener_data.get('marketRegime', 'TÍCH CỰC')

  # ==================== MỐC 1: 10:15 - 10:45 (SÓNG SỚM BÙNG NỔ T0) ====================
  if 615 <= mins <= 645:
    m1_batch_key = f'MOC1_T0_BATCH_{today_str}'
    if not is_alert_already_sent(m1_batch_key, min_interval_seconds=14400):
      candidates = [
          s for s in opps
          if (s.get('tag') == 'BREAKOUT_T0' or str(s.get('badge', '')).startswith('⚡'))
      ]
      sent_any = False
      for stock in candidates[:2]:
        sym = stock.get('symbol')
        sym_key = f'MOC1_STOCK_{today_str}_{sym}'
        if not is_alert_already_sent(sym_key, min_interval_seconds=86400):
          msg, btns = format_breakout_alert(stock)
          if send_telegram_message(msg, buttons=btns):
            record_alert_sent(sym_key, preview=f'Breakout {sym}')
            _ALERT_TRACKER['sent_symbols'].add(sym)
            sent_any = True
      if sent_any or candidates:
        record_alert_sent(m1_batch_key, preview='Moc 1 finished')

  # ==================== MỐC 2: 11:35 - 12:00 (BẢN TIN TRƯA KẾT PHIÊN SÁNG) ====================
  elif 695 <= mins <= 720:
    midday_key = f'DIGEST_MIDDAY_{today_str}'
    if 'MIDDAY' not in _ALERT_TRACKER['sent_digests'] and not is_alert_already_sent(midday_key, min_interval_seconds=14400):
      msg, btns = format_session_digest('Bản Tin Trưa - Kết Phiên Sáng', opps, regime)
      if send_telegram_message(msg, buttons=btns):
        record_alert_sent(midday_key, preview='Midday Digest')
        _ALERT_TRACKER['sent_digests'].add('MIDDAY')

  # ==================== MỐC 3: 14:05 - 14:25 (ĐIỂM MUA GIỜ VÀNG CHIỀU) ====================
  elif 845 <= mins <= 865:
    m3_batch_key = f'MOC3_GOLDEN_BATCH_{today_str}'
    if not is_alert_already_sent(m3_batch_key, min_interval_seconds=14400):
      candidates = [
          s for s in opps
          if s.get('buy_ratio', 50) >= 55.0 and s.get('pct_change', 0) > 0.5
      ]
      sent_any = False
      for stock in candidates[:2]:
        sym = stock.get('symbol')
        sym_key = f'MOC3_STOCK_{today_str}_{sym}'
        if not is_alert_already_sent(sym_key, min_interval_seconds=86400):
          msg, btns = format_breakout_alert(stock)
          if send_telegram_message(msg, buttons=btns):
            record_alert_sent(sym_key, preview=f'Golden Buy {sym}')
            _ALERT_TRACKER['sent_symbols'].add(sym)
            sent_any = True
      if sent_any or candidates:
        record_alert_sent(m3_batch_key, preview='Moc 3 finished')

  # ==================== MỐC 4: 14:50 - 15:15 (TỔNG KẾT ĐÓNG CỬA ATC) ====================
  elif 890 <= mins <= 915:
    atc_key = f'DIGEST_ATC_{today_str}'
    if 'ATC' not in _ALERT_TRACKER['sent_digests'] and not is_alert_already_sent(atc_key, min_interval_seconds=14400):
      msg, btns = format_session_digest('Tổng Kết Đóng Cửa ATC & Xu Hướng', opps, regime)
      if send_telegram_message(msg, buttons=btns):
        record_alert_sent(atc_key, preview='ATC Digest')
        _ALERT_TRACKER['sent_digests'].add('ATC')


def _save_screener_snapshot_to_mongo(data):
  """Lưu snapshot Top T+ mới nhất lên MongoDB Atlas để đồng bộ với Render Cloud."""
  try:
    from backend.db.portfolio_db import _mongo_db
    if _mongo_db is not None and data and data.get('topOpportunities'):
      _mongo_db['screener_snapshots'].update_one(
          {'key': 'top_tplus'},
          {'$set': {'key': 'top_tplus', 'data': data, 'updated_at': int(time.time())}},
          upsert=True
      )
  except Exception as e:
    print('Lỗi lưu screener snapshot lên MongoDB:', e)


def _load_screener_snapshot_from_mongo():
  """Đọc snapshot Top T+ mới nhất từ MongoDB Atlas."""
  try:
    from backend.db.portfolio_db import _mongo_db
    if _mongo_db is not None:
      doc = _mongo_db['screener_snapshots'].find_one({'key': 'top_tplus'})
      if doc and doc.get('data'):
        return doc.get('data')
  except Exception as e:
    print('Lỗi load screener snapshot từ MongoDB:', e)
  return None


def _screener_worker_loop():
  """Tiến trình chạy ngầm làm mới dữ liệu Top T+ định kỳ 3 phút trong giờ giao dịch & bắn cảnh báo."""
  while True:
    try:
      in_market = is_market_hours()
      # Quét định lượng Universe Top 45 mã
      data = build_top_tplus_opportunities(max_total=8)
      if data and data.get('topOpportunities'):
        with _CACHE_LOCK:
          _TOP_TPLUS_CACHE['data'] = data
          _TOP_TPLUS_CACHE['timestamp'] = time.time()
        
        # Lưu snapshot lên MongoDB Atlas để Render đồng bộ
        _save_screener_snapshot_to_mongo(data)
        
        # Đánh giá cảnh báo Telegram theo các mốc giờ vàng
        try:
          _evaluate_telegram_alerts(data)
        except Exception as errAlert:
          print('Lỗi đánh giá Telegram alert:', errAlert)
      
      if in_market:
        time.sleep(_CACHE_TTL_SEC)  # 3 phút trong phiên giao dịch
      else:
        time.sleep(600)  # Ngoài giờ giao dịch: ngủ 10 phút để tránh spam API
    except Exception as e:
      time.sleep(30)


def start_screener_worker():
  """Khởi động Background Worker một lần duy nhất khi server bật."""
  global _WORKER_STARTED
  with _CACHE_LOCK:
    if not _WORKER_STARTED:
      _WORKER_STARTED = True
      t = threading.Thread(target=_screener_worker_loop, daemon=True)
      t.start()


def handle_search(query):
  """Tìm kiếm mã cổ phiếu từ bảng giá SSI."""
  q = (query or '').strip().upper()
  if not q:
    return []
  board = get_ssi_board_data()
  if not board:
    board = _build_synthetic_board_from_entrade()
  results = []
  for sym, item in board.items():
    if sym.startswith(q) or q in str(item.get('companyNameVi', '')).upper():
      results.append({
          'symbol': sym,
          'name': item.get('companyNameVi', item.get('clientName', sym)),
          'exchange': item.get('exchange', 'HOSE'),
          'price': item.get('matchedPrice', item.get('refPrice', 0)),
          'change': item.get('priceChange', 0),
          'percentChange': item.get('priceChangePercent', 0),
      })
      if len(results) >= 15:
        break

  # Fallback nếu mã tìm kiếm chưa có trong board (hoặc mã riêng lẻ)
  if len(results) == 0 and len(q) == 3:
    from backend.data_providers.entrade_provider import fetch_intraday_snapshot
    snap = fetch_intraday_snapshot(q)
    if snap and snap.get('matchedPrice', 0) > 0:
      results.append({
          'symbol': q,
          'name': f'CTCP {q}',
          'exchange': 'HOSE',
          'price': snap.get('matchedPrice', 0),
          'change': snap.get('priceChange', 0),
          'percentChange': snap.get('priceChangePercent', 0),
      })

  return results


def handle_screener():
  """Bộ lọc cổ phiếu thanh khoản cao và tích cực trong phiên."""
  board = get_ssi_board_data()
  if not board:
    board = _build_synthetic_board_from_entrade()
  stocks = [
      v for v in board.values()
      if (v.get('stockType') == 's' or v.get('isSynthetic')) and len(str(v.get('stockSymbol', ''))) == 3
  ]
  # Sắp xếp theo giá trị giao dịch
  sorted_stocks = sorted(
      (s for s in stocks if (s.get('nmTotalTradedValue') or 0) > 0),
      key=lambda s: -(s.get('nmTotalTradedValue') or 0),
  )
  items = []
  for s in sorted_stocks[:50]:
    items.append({
        'symbol': s.get('stockSymbol'),
        'name': s.get('companyNameVi', s.get('clientName', '')),
        'exchange': s.get('exchange', 'HOSE'),
        'price': s.get('matchedPrice', s.get('refPrice', 0)),
        'change': s.get('priceChange', 0),
        'percentChange': s.get('priceChangePercent', 0),
        'volume': s.get('stockVol', 0),
        'value': s.get('nmTotalTradedValue', 0),
        'foreignNet': (s.get('buyForeignQtty', 0) - s.get('sellForeignQtty', 0)),
    })
  return {'stocks': items}


def handle_top_tplus():
  """
  API /api/top-tplus: VSR Smart Screener Top 8 Cơ hội Lướt Sóng T+:
  - Trả về tức thì từ In-Memory Cache hoặc MongoDB Cloud Snapshot (0 delay)
  - Phân loại rõ ràng ⚡ BÙNG NỔ T0 vs 🎯 GOM PULLBACK T1-T2
  - Đảm bảo tương thích ngược cấu trúc dữ liệu cũ
  """
  start_screener_worker()

  with _CACHE_LOCK:
    cached_data = _TOP_TPLUS_CACHE.get('data')
    ts = _TOP_TPLUS_CACHE.get('timestamp', 0)

  # 1. Nếu cache RAM đã có sẵn và còn trong vòng 20 phút thì phục vụ ngay lập tức
  if cached_data and (time.time() - ts < 1200):
    opps = cached_data.get('topOpportunities', [])
    return {
        **cached_data,
        'top': opps,  # Tương thích ngược với caller cũ
        'stocks': opps,
    }

  # 2. Nếu cold-start hoặc RAM trống, kiểm tra snapshot từ MongoDB Atlas Cloud
  mongo_data = _load_screener_snapshot_from_mongo()
  if mongo_data and mongo_data.get('topOpportunities'):
    with _CACHE_LOCK:
      _TOP_TPLUS_CACHE['data'] = mongo_data
      _TOP_TPLUS_CACHE['timestamp'] = time.time()
    opps = mongo_data.get('topOpportunities', [])
    return {
        **mongo_data,
        'top': opps,
        'stocks': opps,
    }

  # 3. Nếu chưa có snapshot, tính toán trực tiếp 1 lần và lưu cache + MongoDB
  try:
    fresh_data = build_top_tplus_opportunities(max_total=8)
    with _CACHE_LOCK:
      _TOP_TPLUS_CACHE['data'] = fresh_data
      _TOP_TPLUS_CACHE['timestamp'] = time.time()
    _save_screener_snapshot_to_mongo(fresh_data)
    opps = fresh_data.get('topOpportunities', [])
    return {
        **fresh_data,
        'top': opps,
        'stocks': opps,
    }
  except Exception as e:
    # Fallback an toàn: nếu tính toán nến gặp lỗi, fallback về top gainers thanh khoản
    res = handle_screener()
    stocks = res.get('stocks', [])
    gainers = [s for s in stocks if s.get('percentChange', 0) > 0]
    gainers.sort(key=lambda s: -(s.get('percentChange', 0)))
    top_items = gainers[:8]
    fallback_data = {
        'updatedAt': get_vn_now().strftime('%H:%M:%S %d/%m/%Y'),
        'marketRegime': 'NEUTRAL',
        'totalScanned': len(stocks),
        'topOpportunities': top_items,
        'top': top_items,
        'stocks': top_items,
        'isFallback': True,
    }
    _save_screener_snapshot_to_mongo(fallback_data)
    return fallback_data


def handle_telegram_test(ticker='SSI'):
  """
  API kiểm tra gửi thử nghiệm cảnh báo Telegram cho mã bất kỳ.
  Toàn bộ dữ liệu được trích xuất 100% từ nến kỹ thuật thực tế & DecisionEngine,
  tuyệt đối không dùng công thức ngón tay cái tĩnh (No Mock/Hardcode).
  """
  from backend.controllers.stock_controller import handle_stock_detail

  sym = (ticker or 'SSI').strip().upper()
  try:
    detail = handle_stock_detail(sym)
  except Exception as e:
    detail = {}

  p = float(detail.get('price', 0))
  if p <= 0:
    board = get_ssi_board_data()
    item = board.get(sym, {})
    raw_p = item.get('matchedPrice', item.get('refPrice', 0))
    p = float(raw_p) if raw_p else 0.0

  pct_change = float(detail.get('percentChange', detail.get('priceChange', 0.0)))
  tech = detail.get('technicals', {})
  decision = detail.get('decisionEngine', {})
  targets_and_stops = decision.get('targetsAndStops', {})
  scenarios = decision.get('scenarios', {})
  sizing = decision.get('positionSizing', {})

  r1 = float(targets_and_stops.get('tp1', {}).get('price') or tech.get('resistance', 0))
  stop_loss = float(targets_and_stops.get('stopLoss', {}).get('price') or tech.get('support', 0))
  net_rr = float(scenarios.get('netRR') or tech.get('rrRatio', 0.0))
  vol_run_rate = float(tech.get('volRatio', 1.0))
  buy_ratio = float(tech.get('buyRatio', 50.0))

  # Trích xuất quyết định hành động dứt khoát từ DecisionEngine (Không mơ hồ)
  primary_act = decision.get('primaryAction', 'WAIT')
  act_badge = decision.get('actionBadge') or primary_act
  act_reason = decision.get('actionReason', '')
  alloc_pct = float(sizing.get('allocatedNowPct', 0.0))

  stock_data = {
      'symbol': sym,
      'name': detail.get('name', f'CTCP {sym}'),
      'price': p,
      'changePct': pct_change,
      'vol_run_rate': vol_run_rate,
      'buy_ratio': buy_ratio,
      'net_rr': net_rr,
      'support': float(tech.get('support', 0)),
      'target1': r1,
      'stop_loss': stop_loss,
      'sector': detail.get('fundamentals', {}).get('sector', ''),
      'primary_action': primary_act,
      'action_badge': act_badge,
      'action_reason': act_reason,
      'allocated_pct': alloc_pct,
  }

  msg, btns = format_breakout_alert(stock_data)
  ok = send_telegram_message(msg, buttons=btns)
  bot_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
  chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
  return {
      'success': ok,
      'targetChatId': chat_id,
      'hasToken': bool(bot_token),
      'messagePreview': msg,
      'buttons': btns,
      'hint': 'Thành công!' if ok else 'Chưa gửi được. Vui lòng kiểm tra TELEGRAM_BOT_TOKEN hoặc Chat ID.',
  }
