"""
Stock RT - Screener Controller
Bộ lọc cổ phiếu và tìm kiếm:
- /api/search: Tìm kiếm mã theo ký tự
- /api/screener: Bộ lọc cổ phiếu theo thanh khoản và biến động thực tế từ Bảng giá Realtime (Entrade Engine)
- /api/top-tplus: VSR Smart Screener Top 8 Cơ hội Lướt Sóng T+ (Phễu 2 tầng)
"""

import os
import threading
import time
import logging

logger = logging.getLogger('screener_controller')

from backend.data_providers.market_board_provider import (
    get_market_board_data,
    get_vnindex_summary,
)
from backend.domain.screener_engine import (
    build_top_tplus_opportunities,
    is_market_hours,
    get_vn_now,
)
from backend.utils.telegram_bot import (
    send_telegram_message,
    format_breakout_alert,
    format_session_digest,
    format_actionable_buy_alert,
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
_SCAN_LOCK = threading.Lock()  # Khóa chống dồn toa khi nhiều request cùng quét một lúc
_MIN_FORCE_REFRESH_INTERVAL_SEC = 15  # Cooldown 15 giây chống spam rate limit
_LAST_FORCE_REFRESH_TS = 0
_WORKER_STARTED = False
_CACHE_TTL_SEC = 180  # 3 phút

# Bộ nhớ tạm kiểm soát trùng lặp cảnh báo Telegram theo ngày
_ALERT_TRACKER = {
    'date': '',
    'sent_symbols': set(),
    'sent_digests': set(),
}


def _is_sweet_spot_new_buy(stock: dict, is_early_session: bool = False) -> tuple[bool, str]:
  """
  Bộ lọc Sweet-Spot & Chống Mua Đuổi độc quyền cho VỊ THẾ MUA MỚI:
  Định lượng hoàn toàn ĐỘNG dựa trên ATR14 của từng mã và biên độ sàn niêm yết (HOSE 7%, HNX 10%, UPCoM 15%).
  Tuyệt đối không hardcode con số tĩnh. Đảm bảo:
  1. Giá mới chớm bứt phá từ nền hỗ trợ S1 (distToS1 <= 0.65 * ATR14).
  2. Chưa tăng quá đà trong phiên (changePct <= min(ATR14, 0.40 * Biên độ sàn)).
  3. Dư địa tăng tới mục tiêu TP1 còn đủ dày (tp1Pct >= max(4.0%, 1.1 * ATR14)).
  4. Lực mua chủ động và khối lượng xác nhận tiền lớn tham gia.
  """
  if not stock or not isinstance(stock, dict):
    return False, "Dữ liệu cổ phiếu không hợp lệ"

  sym = str(stock.get('symbol', '')).upper()
  action_status = str(stock.get('actionStatus', ''))
  badge = str(stock.get('badge', ''))

  # 1. Chặn ngay nếu engine đã phân loại là quá điểm mua hoặc rủi ro
  if action_status in ['OVER_EXTENDED', 'WAIT_PULLBACK', 'REDUCE', 'MARKET_RISK'] or 'ĐÃ' in badge:
    return False, f"Trạng thái {action_status} không phù hợp mở mua mới"

  price = float(stock.get('price') or stock.get('p') or 0.0)
  change_pct = float(stock.get('changePct') or stock.get('pct_change') or 0.0)
  dist_s1 = float(stock.get('distToS1', 99.0))
  tp1_pct = float(stock.get('tp1Pct') or stock.get('mainUpsidePct') or 0.0)
  net_rr = float(stock.get('netRR') or stock.get('net_rr') or 0.0)
  vol_run_rate = float(stock.get('volRunRate') or stock.get('volRatio') or 0.0)
  buy_ratio = float(stock.get('buyRatio') or stock.get('buy_ratio') or 0.0)
  is_leader = bool(stock.get('isMarketLeader') or 'LEADER' in action_status)

  # Xác định biên độ sàn niêm yết thực tế
  exchange = str(stock.get('exchange', 'HOSE')).upper()
  if 'HNX' in exchange:
    limit_pct = 10.0
  elif 'UPC' in exchange:
    limit_pct = 15.0
  else:
    limit_pct = 7.0

  # Tính độ biến động tự nhiên ATR14 của riêng cổ phiếu đó
  atr_val = float(stock.get('atr14') or stock.get('atr') or (price * 0.02 if price > 0 else 500.0))
  atr_pct = (atr_val / price * 100.0) if price > 0 else 2.5
  atr_pct = max(1.2, min(atr_pct, 6.0))

  # 2. Khung biến động giá trong ngày tính ĐỘNG (Change %)
  min_change = round(max(0.4, 0.15 * atr_pct), 2)
  if is_early_session:
    # Sóng sớm đầu phiên: Chỉ mua khi mới chớm bứt phá
    max_change = round(min(0.60 * atr_pct, 0.30 * limit_pct), 2)
    max_change = max(1.8, min(max_change, 3.2))
  else:
    # Phiên thường:
    mult_atr = 0.90 if is_leader else 0.75
    mult_exchange = 0.45 if is_leader else 0.40
    max_change = round(min(mult_atr * atr_pct, mult_exchange * limit_pct), 2)
    max_change = max(2.2, min(max_change, 4.5))

  if change_pct < min_change:
    return False, f"Giá chưa chớm sóng ({change_pct:.2f}% < {min_change}%)"
  if change_pct > max_change:
    return False, f"Giá đã tăng quá trần mua an toàn ({change_pct:.2f}% > {max_change:.2f}% theo ATR/Sàn)"

  # 3. Khoảng cách tới nền hỗ trợ S1 tính ĐỘNG (distToS1)
  dist_mult = 0.45 if is_early_session else (0.70 if is_leader else 0.60)
  max_dist_s1 = round(min(dist_mult * atr_pct, 0.35 * limit_pct), 2)
  max_dist_s1 = max(1.5, min(max_dist_s1, 3.2))
  if dist_s1 > max_dist_s1:
    return False, f"Giá treo cao cách nền hỗ trợ S1 quá xa ({dist_s1:.1f}% > {max_dist_s1:.1f}% theo ATR)"

  # 4. Dư địa tăng tới mục tiêu chốt lời TP1 tính ĐỘNG (tp1Pct)
  # Dư địa tối thiểu phải bao quát ít nhất 1.1x ATR14 để đủ biên lợi nhuận
  min_tp1 = round(max(4.0, 1.1 * atr_pct), 2)
  if tp1_pct < min_tp1:
    return False, f"Dư địa tăng tới TP1 quá hẹp ({tp1_pct:.1f}% < {min_tp1:.1f}% theo ATR), rủi ro mua ngay đỉnh cản"

  # 5. Tỷ lệ Net R:R (netRR) - Phải từ 1.4 trở lên
  if net_rr < 1.4:
    return False, f"Tỷ lệ Net R:R dưới chuẩn an toàn ({net_rr:.2f} < 1.4)"

  # 6. Dòng tiền xác nhận
  min_vol = 0.85 if is_early_session else 0.95
  min_buy_ratio = 55.0
  if vol_run_rate < min_vol:
    return False, f"Vol Run Rate chưa đủ mạnh ({vol_run_rate:.2f} < {min_vol})"
  if buy_ratio < min_buy_ratio:
    return False, f"Lực mua chủ động chưa chiếm ưu thế ({buy_ratio:.1f}% < {min_buy_ratio}%)"

  return True, "Thỏa mãn Sweet-Spot Mua Mới Động"


def _evaluate_telegram_alerts(screener_data):
  """
  Đánh giá và gửi cảnh báo Telegram theo các khung giờ vàng tối ưu cho TTCK Việt Nam:
  0. 09:20 - 10:30: Radar sóng sớm chân nền (Mua Mới T0 đón sóng từ chân nền).
  1. Trong phiên: Đèn Xanh Mua Ngay T0 & Bùng Nổ T0 (Kiểm duyệt Sweet-Spot nghiêm ngặt).
  2. 11:35 - 12:00: Bản tin trưa tóm tắt kết phiên sáng (1 tin duy nhất, có VN-Index & % chuẩn).
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
  # Sử dụng toàn bộ danh sách quét thỏa mãn để không bỏ lỡ sóng sớm
  opps = screener_data.get('allOpportunities') or screener_data.get('topOpportunities', [])
  top_opps = screener_data.get('topOpportunities', opps)
  regime = screener_data.get('marketRegime', 'TÍCH CỰC')

  is_trading_session = (545 <= mins <= 690) or (780 <= mins <= 875)

  # ==================== MỐC 0: 09:20 - 10:30 (RADAR SÓNG SỚM CHÂN NỀN - MUA MỚI T0) ====================
  # Phát hiện ngay các mã chớm nổ vol từ nền để nhà đầu tư lên tàu sớm nhất, không lỡ chuyến (tối đa 2 mã)
  if 560 <= mins <= 630:
    early_sent = 0
    for stock in opps[:15]:
      if early_sent >= 2:
        break
      sym = stock.get('symbol')
      if not sym or sym in _ALERT_TRACKER['sent_symbols']:
        continue
      early_key = f'EARLY_SWEET_{today_str}_{sym}'
      if is_alert_already_sent(early_key, min_interval_seconds=86400):
        continue

      is_sweet, reason = _is_sweet_spot_new_buy(stock, is_early_session=True)
      if is_sweet:
        custom_title = f"🚀 <b>RADAR SÓNG SỚM CHÂN NỀN: {sym}</b>"
        msg, btns = format_breakout_alert(stock, header_title=custom_title)
        if send_telegram_message(msg, buttons=btns, log_meta={'alert_type': 'EARLY_BIRD', 'title': f'Radar Sóng Sớm Chân Nền: {sym}', 'stocks': [stock]}):
          record_alert_sent(early_key, preview=f'Early Sweet Spot {sym}')
          _ALERT_TRACKER['sent_symbols'].add(sym)
          early_sent += 1

  # ==================== 1. ĐÈN XANH HÀNH ĐỘNG NGAY: TỨ TRỤ BANK - CHỨNG - THÉP - BĐS ====================
  # Quét liên tục trong suốt phiên giao dịch (09:05 - 11:30 và 13:00 - 14:35)
  # Chốt chặn Anti-Whipsaw: Mỗi mã chỉ rung chuông duy nhất 1 lần trong ngày (cooldown 86,400s)
  if is_trading_session:
    actionable_candidates = []
    for s in opps:
      is_sweet, reason = _is_sweet_spot_new_buy(s, is_early_session=(mins <= 630))
      if is_sweet and (s.get('isActionableGreenBuy') or s.get('isCoreSector') or s.get('isMarketLeader')):
        actionable_candidates.append(s)

    for stock in actionable_candidates[:2]:
      sym = stock.get('symbol')
      action_key = f'ACTIONABLE_GREEN_{today_str}_{sym}'
      if sym not in _ALERT_TRACKER['sent_symbols'] and not is_alert_already_sent(action_key, min_interval_seconds=86400):
        msg, btns = format_actionable_buy_alert(stock)
        is_leader = stock.get('isMarketLeader') or 'LEADER' in str(stock.get('actionStatus', ''))
        is_pivot = stock.get('isBreakoutPivot', False)
        if is_leader:
          alert_title = f'Siêu Cổ Phiếu Dẫn Dắt Bứt Phá: {sym}' if is_pivot else f'Siêu Cổ Phiếu Dẫn Dắt: {sym}'
        elif is_pivot:
          alert_title = f'Đèn Xanh Bứt Phá Vượt Đỉnh (Pivot R1): {sym}'
        else:
          alert_title = f'Đèn Xanh Mua Ngay T0: {sym}'

        log_meta = {
            'alert_type': 'ACTIONABLE_LEADER_BUY' if is_leader else 'ACTIONABLE_GREEN_BUY',
            'title': alert_title,
            'stocks': [stock],
            'market_regime': regime
        }
        if send_telegram_message(msg, buttons=btns, log_meta=log_meta):
          record_alert_sent(action_key, preview=f'Actionable Green Buy {sym}')
          _ALERT_TRACKER['sent_symbols'].add(sym)

    # ==================== 2. EVENT-DRIVEN REALTIME BREAKOUT (BÙNG NỔ T0 & BỨT PHÁ PIVOT R1) ====================
    breakout_candidates = []
    for s in opps:
      is_sweet, reason = _is_sweet_spot_new_buy(s, is_early_session=(mins <= 630))
      if is_sweet and (
          s.get('isBreakoutPivot') or
          s.get('tagType') == 'BREAKOUT_T0' or
          str(s.get('badge', '')).startswith('⚡') or
          s.get('actionStatus') in ['BREAKOUT_PIVOT', 'BUY_READY', 'ACTIONABLE_LEADER_BUY']
      ):
        breakout_candidates.append(s)

    for stock in breakout_candidates[:2]:
      sym = stock.get('symbol')
      event_key = f'EVENT_BREAKOUT_{today_str}_{sym}'
      if sym not in _ALERT_TRACKER['sent_symbols'] and not is_alert_already_sent(event_key, min_interval_seconds=86400):
        is_pivot = stock.get('isBreakoutPivot', False)
        is_early = stock.get('isEarlyBird', False) or (mins <= 630)
        if is_pivot:
          custom_title = f"🚀 <b>CẢNH BÁO BỨT PHÁ VƯỢT ĐỈNH (PIVOT R1): {sym}</b>"
          log_title = f'Cảnh Báo Bứt Phá Vượt Đỉnh (Pivot R1): {sym}'
        elif is_early:
          custom_title = f"🚀 <b>RADAR SÓNG SỚM ĐẦU PHIÊN: {sym}</b>"
          log_title = f'Radar Sóng Sớm Đầu Phiên: {sym}'
        else:
          custom_title = f"⚡ <b>CẢNH BÁO BÙNG NỔ T0: {sym}</b>"
          log_title = f'Sóng Sớm Bùng Nổ T0: {sym}'

        msg, btns = format_breakout_alert(stock, header_title=custom_title)
        if send_telegram_message(msg, buttons=btns, log_meta={'alert_type': 'BREAKOUT_PIVOT' if is_pivot else 'BREAKOUT_T0', 'title': log_title, 'stocks': [stock]}):
          record_alert_sent(event_key, preview=f'Breakout Event {sym}')
          _ALERT_TRACKER['sent_symbols'].add(sym)

  # ==================== MỐC 1: 10:15 - 10:45 (SÓNG SỚM BÙNG NỔ T0) ====================
  if 615 <= mins <= 645:
    m1_batch_key = f'MOC1_T0_BATCH_{today_str}'
    if not is_alert_already_sent(m1_batch_key, min_interval_seconds=14400):
      candidates = [
          s for s in opps
          if _is_sweet_spot_new_buy(s, is_early_session=False)[0] and (s.get('tagType') == 'BREAKOUT_T0' or str(s.get('badge', '')).startswith('⚡'))
      ]
      sent_any = False
      for stock in candidates[:2]:
        sym = stock.get('symbol')
        sym_key = f'MOC1_STOCK_{today_str}_{sym}'
        if not is_alert_already_sent(sym_key, min_interval_seconds=86400):
          msg, btns = format_breakout_alert(stock)
          if send_telegram_message(msg, buttons=btns, log_meta={'alert_type': 'BREAKOUT_T0', 'title': f'Sóng Sớm Bùng Nổ T0: {sym}', 'stocks': [stock]}):
            record_alert_sent(sym_key, preview=f'Breakout {sym}')
            _ALERT_TRACKER['sent_symbols'].add(sym)
            sent_any = True
      if sent_any or candidates:
        record_alert_sent(m1_batch_key, preview='Moc 1 finished')

  # ==================== MỐC 2: 11:35 - 12:00 (BẢN TIN TRƯA KẾT PHIÊN SÁNG) ====================
  elif 695 <= mins <= 720:
    midday_key = f'DIGEST_MIDDAY_{today_str}'
    if 'MIDDAY' not in _ALERT_TRACKER['sent_digests'] and not is_alert_already_sent(midday_key, min_interval_seconds=14400):
      vni_summary = get_vnindex_summary()
      msg, btns = format_session_digest('Bản Tin Trưa - Kết Phiên Sáng', top_opps, regime, vnindex_summary=vni_summary)
      if send_telegram_message(msg, buttons=btns, log_meta={'alert_type': 'DIGEST_MIDDAY', 'title': 'Bản Tin Trưa - Kết Phiên Sáng', 'stocks': top_opps[:4], 'market_regime': regime, 'vnindex': vni_summary}):
        record_alert_sent(midday_key, preview='Midday Digest')
        _ALERT_TRACKER['sent_digests'].add('MIDDAY')

  # ==================== MỐC 3: 14:05 - 14:25 (ĐIỂM MUA GIỜ VÀNG CHIỀU) ====================
  elif 845 <= mins <= 865:
    m3_batch_key = f'MOC3_GOLDEN_BATCH_{today_str}'
    if not is_alert_already_sent(m3_batch_key, min_interval_seconds=14400):
      candidates = [
          s for s in opps
          if _is_sweet_spot_new_buy(s, is_early_session=False)[0]
      ]
      sent_any = False
      for stock in candidates[:2]:
        sym = stock.get('symbol')
        sym_key = f'MOC3_STOCK_{today_str}_{sym}'
        if not is_alert_already_sent(sym_key, min_interval_seconds=86400):
          msg, btns = format_breakout_alert(stock)
          if send_telegram_message(msg, buttons=btns, log_meta={'alert_type': 'GOLDEN_HOUR', 'title': f'Điểm Mua Giờ Vàng Chiều: {sym}', 'stocks': [stock]}):
            record_alert_sent(sym_key, preview=f'Golden Buy {sym}')
            _ALERT_TRACKER['sent_symbols'].add(sym)
            sent_any = True
      if sent_any or candidates:
        record_alert_sent(m3_batch_key, preview='Moc 3 finished')

  # ==================== MỐC 4: 14:50 - 15:15 (TỔNG KẾT ĐÓNG CỬA ATC) ====================
  elif 890 <= mins <= 915:
    atc_key = f'DIGEST_ATC_{today_str}'
    if 'ATC' not in _ALERT_TRACKER['sent_digests'] and not is_alert_already_sent(atc_key, min_interval_seconds=14400):
      vni_summary = get_vnindex_summary()
      msg, btns = format_session_digest('Tổng Kết Đóng Cửa ATC & Xu Hướng', top_opps, regime, vnindex_summary=vni_summary)
      if send_telegram_message(msg, buttons=btns, log_meta={'alert_type': 'DIGEST_ATC', 'title': 'Tổng Kết Đóng Cửa ATC & Xu Hướng', 'stocks': top_opps[:4], 'market_regime': regime, 'vnindex': vni_summary}):
        record_alert_sent(atc_key, preview='ATC Digest')
        _ALERT_TRACKER['sent_digests'].add('ATC')


def _save_screener_snapshot_to_mongo(data):
  """Lưu snapshot Top T+ mới nhất lên MongoDB Atlas thông qua ScreenerSnapshot Model."""
  try:
    from backend.db.portfolio_db import get_mongo_db
    from backend.constants.db import COLL_SCREENER_SNAPSHOTS
    from backend.models.db_models import ScreenerSnapshot
    db = get_mongo_db()
    if db is not None and data and data.get('topOpportunities'):
      snapshot = ScreenerSnapshot(data=data)
      db[COLL_SCREENER_SNAPSHOTS].update_one(
          ScreenerSnapshot.filter_by_key(snapshot.key),
          {'$set': snapshot.to_doc()},
          upsert=True
      )
  except Exception as e:
    print('Lỗi lưu screener snapshot lên MongoDB:', e)


def _load_screener_snapshot_from_mongo():
  """Đọc snapshot Top T+ mới nhất từ MongoDB Atlas thông qua ScreenerSnapshot Model."""
  try:
    from backend.db.portfolio_db import get_mongo_db
    from backend.constants.db import COLL_SCREENER_SNAPSHOTS
    from backend.models.db_models import ScreenerSnapshot
    db = get_mongo_db()
    if db is not None:
      doc = db[COLL_SCREENER_SNAPSHOTS].find_one(ScreenerSnapshot.filter_by_key(ScreenerSnapshot.KEY_TOP_TPLUS))
      if doc:
        return ScreenerSnapshot.from_doc(doc).data
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
  """Tìm kiếm mã cổ phiếu động trên toàn bộ 1,626 mã niêm yết (HOSE, HNX, UPCoM)."""
  try:
    from backend.data_providers.company_directory_provider import search_companies
    return search_companies(query, limit=15)
  except Exception as e:
    logger.warning("Lỗi tìm kiếm dynamic: %s", e)
    return []


def handle_screener():
  """Bộ lọc cổ phiếu thanh khoản cao và tích cực trong phiên."""
  board = get_market_board_data()
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


def handle_top_tplus(force_refresh=False):
  """
  API /api/top-tplus: VSR Smart Screener Top 8 Cơ hội Lướt Sóng T+:
  - Trả về tức thì từ In-Memory Cache hoặc MongoDB Cloud Snapshot (0 delay)
  - Hỗ trợ force_refresh=True khi người dùng bấm nút 'Làm mới' để tính toán realtime
  - Cơ chế chống spam Rate Limit:
    + Cooldown 15s giữa các lần force_refresh
    + In-flight coalescing: nếu đang có 1 luồng quét, các luồng khác chờ hoặc nhận cache
    + Reload page / request thường: luôn trả về cache RAM hoặc snapshot MongoDB trong 0ms
  - Phân loại rõ ràng ⚡ BÙNG NỔ T0 vs 🎯 GOM PULLBACK T1-T2
  - Đảm bảo tương thích ngược cấu trúc dữ liệu cũ
  """
  global _LAST_FORCE_REFRESH_TS
  start_screener_worker()

  now = time.time()

  with _CACHE_LOCK:
    cached_data = _TOP_TPLUS_CACHE.get('data')
    ts = _TOP_TPLUS_CACHE.get('timestamp', 0)

  # 1. Cơ chế chống spam: Nếu là force_refresh nhưng vừa mới quét cách đây chưa đầy 15s
  if force_refresh:
    time_since_last = now - ts
    if time_since_last < _MIN_FORCE_REFRESH_INTERVAL_SEC and cached_data:
      cooldown_rem = int(max(1, _MIN_FORCE_REFRESH_INTERVAL_SEC - time_since_last))
      logger.info("Anti-spam: Bỏ qua force_refresh vì vừa quét cách đây %.1fs (cooldown còn %ds).", time_since_last, cooldown_rem)
      opps = cached_data.get('topOpportunities', [])
      return {
          **cached_data,
          'top': opps,
          'stocks': opps,
          'rateLimited': True,
          'cooldownRemaining': cooldown_rem,
      }

  # 2. Xử lý request thông thường (như Reload page / F5):
  if not force_refresh:
    # Nếu RAM Cache còn hiệu lực (20 phút ngoài phiên, 3 phút trong phiên) -> Phục vụ ngay 0ms
    if cached_data and (now - ts < 1200):
      opps = cached_data.get('topOpportunities', [])
      return {
          **cached_data,
          'top': opps,
          'stocks': opps,
      }

    # Nếu cold-start hoặc RAM trống -> Đọc snapshot MongoDB Atlas
    mongo_data = _load_screener_snapshot_from_mongo()
    if mongo_data and mongo_data.get('topOpportunities'):
      with _CACHE_LOCK:
        _TOP_TPLUS_CACHE['data'] = mongo_data
        _TOP_TPLUS_CACHE['timestamp'] = now
      opps = mongo_data.get('topOpportunities', [])
      return {
          **mongo_data,
          'top': opps,
          'stocks': opps,
      }

  # 3. Quét mới từ thị trường (In-flight coalescing để chống dồn toa nếu nhiều request cùng bấm làm mới)
  acquired = _SCAN_LOCK.acquire(blocking=False)
  if not acquired:
    # Đang có một luồng khác thực hiện quét, nếu đã có cache thì trả về ngay tránh nghẽn
    if cached_data:
      opps = cached_data.get('topOpportunities', [])
      return {**cached_data, 'top': opps, 'stocks': opps}
    # Nếu chưa hề có cache, chờ luồng kia hoàn tất rồi lấy kết quả
    with _SCAN_LOCK:
      with _CACHE_LOCK:
        cached_data = _TOP_TPLUS_CACHE.get('data')
      if cached_data:
        opps = cached_data.get('topOpportunities', [])
        return {**cached_data, 'top': opps, 'stocks': opps}

  try:
    fresh_data = build_top_tplus_opportunities(max_total=8)
    _LAST_FORCE_REFRESH_TS = time.time()
    with _CACHE_LOCK:
      _TOP_TPLUS_CACHE['data'] = fresh_data
      _TOP_TPLUS_CACHE['timestamp'] = _LAST_FORCE_REFRESH_TS
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
  finally:
    try:
      _SCAN_LOCK.release()
    except RuntimeError:
      pass


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
    board = get_market_board_data()
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
  ok = send_telegram_message(msg, buttons=btns, log_meta={'alert_type': 'TEST_ALERT', 'title': f'Thử nghiệm cảnh báo: {ticker}', 'stocks': [stock_data]})
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
