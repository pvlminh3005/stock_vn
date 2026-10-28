"""
Stock RT - Screener Engine (VSR Smart Screener)
Động cơ sàng lọc định lượng phễu 2 tầng:
1. Tầng 1: Lọc Universe cổ phiếu đầu ngành thanh khoản cao & an toàn pháp lý.
2. Tầng 2: Phân loại 2 nhóm cơ hội rõ ràng:
   - ⚡ BÙNG NỔ CHÂN SÓNG (BREAKOUT_T0): 100% Full size
   - 🎯 GOM PULLBACK T1-T2 (PULLBACK_T1_T2): 30-50% Size thăm dò
3. Tích hợp 4 chốt chặn an toàn:
   - Chuẩn hóa Volume Run-rate thời gian thực trong ngày
   - Bộ lọc Upper Wick (< 38%) chống nến cụt đầu sau 14h00
   - Khóa Net R:R >= 1.5 và Dư địa >= 3.5%
   - Cân bằng hạn ngạch Quota (Tối đa 8 mã: 5 Bùng nổ + 3 Pullback)
"""

import datetime
import time
from concurrent.futures import ThreadPoolExecutor

from backend.domain.portfolio_bundler import KNOWN_STOCK_SECTORS, get_stock_sector
from backend.domain.technicals import analyze_technicals_and_scoring
from backend.domain.regime import evaluate_market_regime
from backend.data_providers.ssi_provider import get_ssi_board_data
from backend.data_providers.entrade_provider import fetch_chart_data


def is_market_hours(now=None):
  """Kiểm tra xem thời điểm hiện tại có nằm trong giờ khớp lệnh TTCK Việt Nam không."""
  if now is None:
    now = datetime.datetime.now()
  # Thứ 7 (5) và Chủ nhật (6) đóng cửa
  if now.weekday() >= 5:
    return False
  t = now.time()
  morning = datetime.time(9, 15) <= t <= datetime.time(11, 35)
  afternoon = datetime.time(12, 55) <= t <= datetime.time(15, 5)
  return morning or afternoon


def get_session_elapsed_ratio(now=None):
  """
  Tính tỷ lệ thời gian giao dịch đã trôi qua trong ngày (0.12 - 1.0).
  - Phiên sáng: 9h00 - 11h30 (150 phút)
  - Phiên chiều: 13h00 - 14h45 (105 phút)
  - Tổng cộng cả phiên: 255 phút
  """
  if now is None:
    now = datetime.datetime.now()
  if not is_market_hours(now):
    return 1.0
  t = now.time()
  cur_mins = t.hour * 60 + t.minute

  if cur_mins < 9 * 60 + 15:
    return 0.12
  elif 9 * 60 + 15 <= cur_mins <= 11 * 60 + 30:
    elapsed = max(20, cur_mins - 9 * 60)
    return min(1.0, elapsed / 255.0)
  elif 11 * 60 + 30 < cur_mins < 13 * 60:
    return 150.0 / 255.0  # ~58.8%
  elif 13 * 60 <= cur_mins <= 14 * 60 + 45:
    elapsed = 150 + (cur_mins - 13 * 60)
    return min(1.0, elapsed / 255.0)
  else:
    return 1.0


def calculate_volume_run_rate(current_vol, avg_vol_20, now=None):
  """Tính tốc độ thanh khoản dự phóng cả ngày so với TB20 phiên."""
  if not avg_vol_20 or avg_vol_20 <= 0:
    return 1.0
  elapsed = max(0.12, get_session_elapsed_ratio(now))
  projected_vol = current_vol / elapsed
  return round(projected_vol / avg_vol_20, 2)


def calculate_upper_wick_ratio(high, low, close):
  """Tính tỷ lệ râu nến trên so với tổng chiều dài nến ngày."""
  if high <= low or high <= 0:
    return 0.0
  range_day = high - low
  upper_wick = max(0.0, high - close)
  return round(upper_wick / range_day, 2)


def evaluate_single_stock_opportunity(symbol, ssi_item, regime=None, now=None):
  """Đánh giá chi tiết 1 mã cổ phiếu xem có đạt chuẩn Bùng Nổ T0 hoặc Gom Pullback T1-T2."""
  if now is None:
    now = datetime.datetime.now()
  try:
    p = ssi_item.get('matchedPrice') or ssi_item.get('refPrice', 0)
    ref = ssi_item.get('refPrice', p)
    if not p or p <= 0:
      return None

    high = ssi_item.get('highest') or p
    low = ssi_item.get('lowest') or p
    vol = ssi_item.get('stockVol', 0)
    traded_val = ssi_item.get('nmTotalTradedValue', 0)
    buy_vol = ssi_item.get('buyVol', 0)
    sell_vol = ssi_item.get('sellVol', 0)
    total_bs = buy_vol + sell_vol
    buy_ratio = round((buy_vol / total_bs) * 100, 1) if total_bs > 0 else 50.0

    change = ssi_item.get('priceChange', p - ref)
    pct_change = ssi_item.get('priceChangePercent', round((change / ref * 100), 2) if ref else 0.0)

    exchange = ssi_item.get('exchange', 'HOSE').upper()
    chart = fetch_chart_data(symbol, days=90, resolution='1D', ssi_item=ssi_item)

    # Fallback dữ liệu nến phiên gần nhất nếu ngoài giờ giao dịch hoặc sáng sớm chưa có khớp lệnh
    if (not vol or vol == 0) and chart and chart.get('v') and len(chart['v']) > 0:
      vol = chart['v'][-1]
      traded_val = vol * p
      if chart.get('h') and chart['h'][-1] > 0:
        raw_h = chart['h'][-1]
        high = raw_h * 1000 if raw_h < 500 else raw_h
      if chart.get('l') and chart['l'][-1] > 0:
        raw_l = chart['l'][-1]
        low = raw_l * 1000 if raw_l < 500 else raw_l
      if len(chart.get('c', [])) >= 2:
        raw_prev = chart['c'][-2]
        prev_c = raw_prev * 1000 if raw_prev < 500 else raw_prev
        raw_curr = chart['c'][-1]
        curr_c = raw_curr * 1000 if raw_curr < 500 else raw_curr
        p = curr_c
        change = p - prev_c
        pct_change = round((change / prev_c * 100), 2) if prev_c else 0.0

    # Lọc thanh khoản tối thiểu: Giá trị giao dịch >= 3 tỷ VNĐ (hoặc 100k CP)
    if traded_val < 3_000_000_000 and vol < 100_000:
      return None

    tech = analyze_technicals_and_scoring(chart, ssi_item, p, {}, ticker=symbol, exchange=exchange, regime=regime)

    s1 = tech.get('support', round(p * 0.96, -2))
    r1 = tech.get('resistance', round(p * 1.08, -2))
    r2 = tech.get('resistance2', round(p * 1.15, -2))
    atr = tech.get('atr14', round(p * 0.02, 1))
    st = tech.get('supertrend', {})
    is_bullish = st.get('isBullish', False)
    is_flip_buy = st.get('isFlipBuy', False)
    ema9 = tech.get('ema9', p)
    vol_ma20 = tech.get('volMa20', 100_000)

    vol_run_rate = calculate_volume_run_rate(vol, vol_ma20, now)
    upper_wick = calculate_upper_wick_ratio(high, low, p)
    dist_s1 = round(((p - s1) / s1) * 100.0, 1) if s1 > 0 else 0.0

    # Target sóng và Cắt lỗ cấu trúc
    target1 = r1 if r1 > p else round(p * 1.05, -2)
    target_blended = round((0.4 * target1 + 0.6 * r2) if r2 > target1 else target1, -2)
    stop_loss = round(min(s1 - 0.4 * atr, p - 1.2 * atr), -2)
    if stop_loss >= p:
      stop_loss = round(p - 1.2 * atr, -2)

    downside = max(100.0, (p - stop_loss) + (0.003 * p))
    upside_blended = max(100.0, (target_blended - p) - (0.003 * p))
    residual_upside_pct = round(((target_blended - p) / p) * 100, 1) if p > 0 else 0.0
    net_rr = round(upside_blended / downside, 2)

    # Chốt chặn rủi ro 1: R/R tối thiểu >= 1.2 và Dư địa sóng >= 3.0%
    if net_rr < 1.2 or residual_upside_pct < 3.0:
      return None

    # Chốt chặn rủi ro 2: Nến không bị bán cụt đầu (Upper wick <= 0.45)
    if upper_wick > 0.45 and pct_change < 4.0:
      return None

    name = ssi_item.get('companyNameVi', ssi_item.get('clientName', symbol))
    sector = get_stock_sector(symbol, name)

    # ==================== NHÁNH 1: BÙNG NỔ CHÂN SÓNG T0 ====================
    is_breakout = False
    if pct_change >= 0.5 and p >= ema9:
      # Điều kiện: Mới chuyển xanh hôm nay HOẶC bứt phá từ nền
      if is_flip_buy or (is_bullish and 0.0 <= dist_s1 <= 4.2 and vol_run_rate >= 0.9):
        is_breakout = True

    # ==================== NHÁNH 2: GOM PULLBACK T1-T2 ====================
    is_pullback = False
    ma20 = tech.get('ma20', s1)
    atr_support = round(high - 1.2 * atr, -2)
    # Mức giá đảo chiều định lượng P_reversal: max(S1, MA20, High - 1.2*ATR)
    reversal_price = round(max(s1, ma20, atr_support), -2)
    if reversal_price > p:
      reversal_price = round(min(p, s1), -2)

    if not is_breakout and is_bullish:
      # Giá đỏ nhẹ hoặc giằng co sát nền, vol cạn kiệt
      if -2.5 <= pct_change <= 0.6 and -1.8 <= dist_s1 <= 3.2 and vol_run_rate <= 1.3:
        is_pullback = True

    if not is_breakout and not is_pullback:
      return None

    # Tính điểm xếp hạng cơ hội (Opportunity Composite Score)
    score = (net_rr * 15.0) + (buy_ratio * 0.3) + (vol_run_rate * 8.0) - (abs(dist_s1) * 2.0)
    if is_breakout:
      score += 15.0

    if is_breakout:
      tag_type = 'BREAKOUT_T0'
      badge = '⚡ BÙNG NỔ CHÂN SÓNG'
      badge_color = 'emerald'
      alloc_advice = 'Vị thế Mua mới: 100% Full size (10-15% NAV)'
      alloc_pct = 100
      timing_note = f'Nổ Vol x{vol_run_rate:.1f} TB20, Mua CĐ {buy_ratio}%, cách nền +{dist_s1}%. Vào lệnh chủ động.'
      entry_zone = f'{s1:,.0f} - {round(min(s1 + 0.4 * atr, p * 1.005), -2):,.0f} đ'
    else:
      tag_type = 'PULLBACK_T1_T2'
      badge = '🎯 GOM PULLBACK T1-T2'
      badge_color = 'amber'
      alloc_advice = 'Vị thế Thăm dò: Tối đa 30-50% size (5-7% NAV)'
      alloc_pct = 40
      timing_note = f'Vùng đón lõng P_rev {reversal_price:,.0f} đ, Vol {vol_run_rate:.1f}x TB20 (cạn cung). Ưu tiên gom giá đỏ.'
      entry_zone = f'{reversal_price:,.0f} - {round(min(reversal_price + 0.3 * atr, p * 1.005), -2):,.0f} đ'

    # ==================== ĐÁNH GIÁ 3 KHÓA AN TOÀN & ĐÈN XANH HÀNH ĐỘNG ====================
    is_weekday = now.weekday() < 5
    cur_mins = now.hour * 60 + now.minute
    # Khóa 1: Khung giờ giao dịch phiên sáng hoặc đầu chiều trước 13:45
    is_in_trading_hours = is_market_hours(now)
    is_pre_1345 = is_weekday and is_in_trading_hours and (cur_mins < 13 * 60 + 45)

    # Khóa 2: Biên độ - Chống đu đỉnh (Giá chạy quá xa nền)
    is_overextended = False
    if is_breakout and (dist_s1 > 3.2 or pct_change > 4.5):
      is_overextended = True
    elif is_pullback and (dist_s1 > 2.2 or pct_change > 2.0):
      is_overextended = True

    # Khóa 3: Thị trường chung (VN-Index Kill-Switch)
    is_market_adverse = regime in ('DOWN_TREND', 'DISTRIBUTION', 'RISK_OFF')

    sl_pct = round(((stop_loss - p) / p) * 100, 1)
    tp1_pct = round(((target1 - p) / p) * 100, 1)

    if is_market_adverse:
      action_status = 'MARKET_RISK'
      action_label = '⚠️ THỊ TRƯỜNG RỦI RO'
      action_badge_color = 'rose'
      action_guide = 'VN-Index chịu áp lực bán lớn. Tạm dừng mở vị thế mua để bảo vệ vốn.'
    elif is_overextended:
      action_status = 'OVER_EXTENDED'
      action_label = '⛔ ĐÃ CHẠY XA'
      action_badge_color = 'rose'
      action_guide = f'Giá đã tăng +{pct_change:.1f}% (cách nền +{dist_s1:.1f}%). Tuyệt đối không FOMO đu đỉnh.'
    elif is_pre_1345:
      action_status = 'WAITING_CONFIRMATION'
      action_label = '⏳ CHỜ PHIÊN CHIỀU'
      action_badge_color = 'amber'
      action_guide = f'Đang giữ nhịp sóng (+{pct_change:.1f}%). Chờ sau 13:45 hấp thụ hàng T+ trước khi chốt giải ngân.'
    else:
      action_status = 'BUY_READY'
      action_label = '🟢 MUA NGAY'
      action_badge_color = 'emerald'
      if is_breakout:
        action_guide = f'Đã xác nhận sau 13:45, Vol nổ x{vol_run_rate:.1f} TB20. Vào lệnh mua mới 100% size (10-15% NAV).'
      else:
        action_guide = f'Test nền chuẩn, cạn kiệt vol, rủi ro thấp. Gom thăm dò 30-50% size sát vùng {s1:,.0f} đ.'

    return {
        'symbol': symbol,
        'name': name,
        'sector': sector,
        'exchange': exchange,
        'price': p,
        'refPrice': ref,
        'change': change,
        'changePct': pct_change,
        'volume': vol,
        'tradedValue': traded_val,
        'buyRatio': buy_ratio,
        'volRunRate': vol_run_rate,
        'support': s1,
        'resistance': r1,
        'target1': target1,
        'target2': r2,
        'stopLoss': stop_loss,
        'netRR': net_rr,
        'residualUpsidePct': residual_upside_pct,
        'distToS1': dist_s1,
        'tagType': tag_type,
        'badge': badge,
        'badgeColor': badge_color,
        'entryZone': entry_zone,
        'allocAdvice': alloc_advice,
        'allocPct': alloc_pct,
        'timingNote': timing_note,
        'opportunityScore': round(score, 1),
        'actionStatus': action_status,
        'actionLabel': action_label,
        'actionBadgeColor': action_badge_color,
        'actionGuide': action_guide,
        'slPct': sl_pct,
        'tp1Pct': tp1_pct,
        'reversalPrice': reversal_price,
        'isSectorWave': False,
        'sectorLeader': None,
    }
  except Exception as e:
    return None


def build_top_tplus_opportunities(max_total=8):
  """
  Quét Universe các mã đầu ngành thanh khoản cao và phân loại Top 8 cơ hội T+:
  - Tối đa 8 mã tổng cộng
  - Cân bằng Quota: Tối đa 5 mã Bùng nổ + 3 mã Gom Pullback
  """
  ssi_board = get_ssi_board_data()
  if not ssi_board:
    return {'updatedAt': time.strftime('%H:%M:%S %d/%m/%Y'), 'totalScanned': 0, 'topOpportunities': []}

  regime = evaluate_market_regime(ssi_board)

  # Chọn lọc Universe Top 45 mã chất lượng từ danh mục đầu ngành có thanh khoản
  universe_symbols = list(KNOWN_STOCK_SECTORS.keys())
  in_trading = is_market_hours()
  if in_trading:
    board_symbols = [
        sym for sym in universe_symbols
        if sym in ssi_board and (ssi_board[sym].get('nmTotalTradedValue') or 0) > 0
    ]
    board_symbols.sort(key=lambda s: -(ssi_board[s].get('nmTotalTradedValue') or 0))
  else:
    board_symbols = [sym for sym in universe_symbols if sym in ssi_board]

  if not board_symbols:
    board_symbols = [sym for sym in universe_symbols if sym in ssi_board]

  scan_list = board_symbols[:45]

  results = []
  with ThreadPoolExecutor(max_workers=10) as executor:
    futures = [
        executor.submit(evaluate_single_stock_opportunity, sym, ssi_board.get(sym, {}), regime)
        for sym in scan_list
    ]
    for fut in futures:
      res = fut.result()
      if res:
        results.append(res)

  breakouts = [r for r in results if r['tagType'] == 'BREAKOUT_T0']
  pullbacks = [r for r in results if r['tagType'] == 'PULLBACK_T1_T2']

  # Nhận diện sóng ngành đồng thuận (Sector Sympathy Play): Leader nổ -> Đàn em đón lõng tại P_reversal
  breakout_sectors = {}
  for bo in breakouts:
    sec = bo.get('sector')
    if sec and sec not in breakout_sectors:
      breakout_sectors[sec] = bo.get('symbol')

  for pb in pullbacks:
    sec = pb.get('sector')
    if sec and sec in breakout_sectors:
      leader_sym = breakout_sectors[sec]
      pb['isSectorWave'] = True
      pb['sectorLeader'] = leader_sym
      pb['opportunityScore'] += 12.0  # Thưởng điểm ưu tiên đón sóng ngành
      pb['badge'] = f'🎯 SÓNG {sec.upper()}'
      rev_p = pb.get('reversalPrice', pb.get('support', pb.get('price')))
      pb['timingNote'] = f'Sóng ngành cùng Leader {leader_sym}. Vùng đón lõng {rev_p:,.0f} đ.'
      if pb.get('actionStatus') == 'BUY_READY':
        pb['actionGuide'] = f'Sóng ngành {sec} (Leader {leader_sym} nổ vol). {pb["symbol"]} đang ở vùng đón lõng {rev_p:,.0f} đ, cạn vol.'

  # Xếp hạng từng nhóm theo Opportunity Score giảm dần
  breakouts.sort(key=lambda x: -x['opportunityScore'])
  pullbacks.sort(key=lambda x: -x['opportunityScore'])

  # Cân bằng hạn ngạch Quota: Tối đa 5 Bùng nổ + 3 Pullback
  max_bo = 5
  max_pb = 3

  selected_bo = breakouts[:max_bo]
  selected_pb = pullbacks[:max_pb]

  # Bù trừ hạn ngạch nếu 1 bên không đủ
  total_selected = len(selected_bo) + len(selected_pb)
  if total_selected < max_total:
    rem = max_total - total_selected
    if len(breakouts) > len(selected_bo):
      selected_bo.extend(breakouts[len(selected_bo):len(selected_bo) + rem])
    elif len(pullbacks) > len(selected_pb):
      selected_pb.extend(pullbacks[len(selected_pb):len(selected_pb) + rem])

  final_list = selected_bo + selected_pb
  # Sắp xếp danh sách cuối cùng theo Score để mã tiềm năng nhất lên đầu
  final_list.sort(key=lambda x: -x['opportunityScore'])
  final_list = final_list[:max_total]

  return {
      'updatedAt': time.strftime('%H:%M:%S %d/%m/%Y'),
      'marketRegime': regime.get('status', 'NEUTRAL') if isinstance(regime, dict) else 'NEUTRAL',
      'totalScanned': len(scan_list),
      'countBreakout': len([x for x in final_list if x['tagType'] == 'BREAKOUT_T0']),
      'countPullback': len([x for x in final_list if x['tagType'] == 'PULLBACK_T1_T2']),
      'topOpportunities': final_list,
  }
