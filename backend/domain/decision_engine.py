"""
Stock RT - Unified & Multi-Perspective Decision Engine
Động cơ ra quyết định phân tách 2 chiều độc lập:
1. Chiều Khung Thời Gian (Horizon):
   - ⚡ Lướt Sóng T+ (2-7 phiên): Momentum, Order Flow (buyRatio), Vol Ratio, EMA9/21, RSI phân kỳ.
   - 💎 Trung & Dài Hạn (3-12+ tháng): FA Score, ROE, Dòng tiền CFO, Biên an toàn P/E multiple.

2. Chiều Vị Thế Nhà Đầu Tư (Position Status):
   - 🛒 Vị Thế MUA MỚI (Chưa sở hữu): Focus vào điểm vào (Entry), R/R, điều kiện bùng nổ/tích lũy.
     Các hành động: BUY (Mua nền/Breakout/Bắt nảy) / WAIT (Chờ tạo nền/Không mua đuổi) / AVOID.
   - 💼 Vị Thế ĐANG NẮM GIỮ (Đã có hàng): Focus vào quản trị rủi ro & gồng lãi.
     Các hành động: HOLD (Gồng lãi + Trailing Stop) / ADD (Gia tăng) / REDUCE (Chốt lời 30-50%) / SELL (Cắt lỗ).
"""

from backend.constants.config import (
    T_PLUS_RISK_BUDGET_PCT,
    SINGLE_STOCK_NAV_CAP_PCT,
)


def evaluate_tplus_strategy(
    ticker,
    exchange_clean,
    current_price,
    tech,
    reg,
    risk,
):
  """Động cơ Lướt sóng T+ (2-7 phiên) phân tách Mua Mới vs Đang Nắm Giữ."""
  ma20 = tech.get('ma20', current_price)
  ema9 = tech.get('ema9', current_price)
  ema21 = tech.get('ema21', current_price)
  rsi = tech.get('rsi', 50.0)
  rsi_div = tech.get('rsiDivergence', {})
  has_bull_div = rsi_div.get('hasBullishDivergence', False)
  div_detail = rsi_div.get('detail', '')

  vol_ratio = tech.get('volRatio', 1.0)
  buy_ratio = tech.get('buyRatio', 50.0)
  day_change_pct = tech.get('dayChangePct', 0.0)
  rs_info = tech.get('rs', {})
  rs_score = rs_info.get('rsScore', 50)
  atr14 = tech.get('atr14', round(current_price * 0.02, 1))

  st = tech.get('supertrend', {})
  st_bullish = st.get('isBullish', False)
  st_flip_buy = st.get('isFlipBuy', False)
  st_flip_sell = st.get('isFlipSell', False)
  st_band = st.get('bandPrice', round(current_price * 0.95, -2))

  support_s1 = tech.get('support', round(current_price * 0.96, -2))
  resist_r1 = tech.get('resistance', round(current_price * 1.08, -2))
  resist_r2 = tech.get('resistance2', round(current_price * 1.15, -2))

  # Cắt lỗ T+ bám sát cấu trúc nến & ATR
  structural_stop = support_s1 - (0.5 * atr14)
  if structural_stop >= current_price:
    structural_stop = current_price - atr14
  stop_loss_price = round(min(structural_stop, current_price - 1.5 * atr14), -2)

  downside_val = max(1.0, current_price - stop_loss_price)
  downside_pct = round((downside_val / current_price) * 100, 1) if current_price > 0 else 3.5

  upside_r1_val = max(0.0, resist_r1 - current_price)
  upside_r1_pct = round((upside_r1_val / current_price) * 100, 1) if current_price > 0 else 6.0

  net_upside = max(0.0, (resist_r1 - current_price) - (0.004 * current_price))
  net_downside = (current_price - stop_loss_price) + (0.004 * current_price)
  rr_ratio = round(net_upside / net_downside, 2) if net_downside > 0 else 1.0

  dist_to_s1 = round(((current_price - support_s1) / support_s1) * 100.0, 1) if support_s1 > 0 else 0.0

  # Hard rules T+
  tail_lock_risk = risk.get('tailLockRisk', False)
  tail_lock_reasons = risk.get('tailLockReasons', [])
  has_legal = risk.get('fundamentalRisk', {}).get('hasLegalDisputes', False)

  hard_rules = []
  if tail_lock_risk:
    hard_rules.append(f"🚨 RỦI RO KẸT SÀN T+: Nguy cơ mất thanh khoản trắng bên mua ({'; '.join(tail_lock_reasons)}). Tuyệt đối cấm lướt T+.")
  if has_legal:
    hard_rules.append("⚠️ PHÁP LÝ NGHIÊM TRỌNG: Cổ phiếu có biến cố pháp lý/lãnh đạo chưa xác minh. Tránh rủi ro kẹt hàng chiều T+2.")

  # Chấm điểm xung lực T+ (Kết hợp Volume, Price, EMA và SuperTrend)
  tplus_score = 45
  if buy_ratio >= 55:
    tplus_score += 15
  elif buy_ratio >= 50:
    tplus_score += 8
  elif buy_ratio < 42:
    tplus_score -= 15

  if vol_ratio >= 1.25 and day_change_pct > 0:
    tplus_score += 15
  elif vol_ratio >= 1.1 and day_change_pct > 0:
    tplus_score += 8
  elif vol_ratio >= 1.4 and day_change_pct < -1.5:
    tplus_score -= 18

  if current_price >= ema9:
    tplus_score += 10
  if ema9 >= ema21:
    tplus_score += 8

  # Tín hiệu SuperTrend Ribbon (Xanh Vào / Hồng Ra)
  if st_flip_buy:
    tplus_score += 15
  elif st_bullish:
    tplus_score += 8
  else:
    tplus_score -= 10

  if has_bull_div:
    tplus_score += 15
  elif 45 <= rsi <= 65:
    tplus_score += 8
  elif rsi > 72:
    tplus_score -= 15
  elif rsi < 32:
    tplus_score += 5

  tplus_score = int(max(10, min(95, tplus_score)))

  # Sizing
  floor_cap = 15.0 if 'HOSE' in exchange_clean else (10.5 if 'HNX' in exchange_clean else 7.2)
  regime_coef = reg.get('coefficient', 0.75)
  risk_budget_pct = round(T_PLUS_RISK_BUDGET_PCT * regime_coef, 2)
  nominal_nav_pct = round((risk_budget_pct / downside_pct) * 100.0, 1) if downside_pct > 0 else 0.0
  max_nav_pct = round(min(floor_cap, SINGLE_STOCK_NAV_CAP_PCT, nominal_nav_pct), 1)
  pilot_nav_pct = round(max_nav_pct * 0.4, 1)
  pyramid_nav_pct = round(max_nav_pct * 0.6, 1)

  # Entry đa tầng T+
  entry_a_min = support_s1
  entry_a_max = round(min(support_s1 + 0.4 * atr14, current_price * 1.005), -2)
  entry_b_min = round(max(ema9, current_price), -2)
  entry_b_max = round(entry_b_min * 1.015, -2)

  # Trailing stop
  holding_tech = tech.get('positionHolding', {})
  base_trailing = holding_tech.get('trailingStop', stop_loss_price)
  trailing_stop = max(base_trailing, st_band) if (st_bullish and st_band > 0) else base_trailing
  trailing_stop_display = f'{trailing_stop:,.0f} đ'

  # =========================================================================
  # 1. NHÁNH VỊ THẾ MUA MỚI (CHƯA CÓ HÀNG)
  # =========================================================================
  new_action = 'WAIT'
  new_badge = 'QUAN SÁT TÍN HIỆU T+'
  new_subtag = 'WAIT_FLOW'
  new_reason = f'Cổ phiếu đang giằng co chưa có tín hiệu dòng tiền bùng nổ hoặc điểm mua an toàn (Mua CĐ {buy_ratio}%, Vol x{vol_ratio} TB20).'
  if not st_bullish:
    new_reason += f' Dải xu hướng SuperTrend đang HỒNG (Downtrend - dải cản {st_band:,.0f} đ), ưu tiên chờ đảo chiều.'
  new_alloc = 0.0

  if tail_lock_risk or has_legal:
    new_action = 'WAIT'
    new_badge = 'CẤM MUA MỚI (RỦI RO CAO)'
    new_subtag = 'AVOID_RISK'
    new_reason = 'Phát hiện nguy cơ kẹt sàn mất thanh khoản hoặc biến cố pháp lý. Tuyệt đối không mở vị thế mua mới.'
    new_alloc = 0.0
  elif st_flip_buy and buy_ratio >= 48:
    new_action = 'BUY'
    new_badge = 'MUA THEO XU HƯỚNG T+ (XANH VÀO)'
    new_subtag = 'BUY_ON_SUPERTREND'
    new_reason = (
        f"Chỉ báo SuperTrend đảo chiều xác nhận tín hiệu XANH VÀO quanh {current_price:,.0f} đ "
        f"(dải đệm hỗ trợ tại {st_band:,.0f} đ). Lực mua chủ động {buy_ratio}%, Net R:R 1:{rr_ratio}. "
        f"Mở vị thế đánh sóng ngắn hạn theo dải xu hướng."
    )
    new_alloc = pilot_nav_pct
  elif has_bull_div or (rsi < 35 and dist_to_s1 <= 3.0 and buy_ratio >= 48):
    new_action = 'BUY'
    new_badge = 'BẮT NẢY KỸ THUẬT (REVERSAL)'
    new_subtag = 'BUY_ON_REVERSAL'
    new_reason = (
        f"{div_detail or f'RSI vào vùng quá bán ({rsi})'} sát hỗ trợ cứng S1 ({support_s1:,.0f} đ). "
        f"Lực cầu hấp thụ tốt (mua chủ động {buy_ratio}%), Net R:R 1:{rr_ratio}. Mở vị thế thăm dò bắt nhịp hồi T+."
    )
    new_alloc = pilot_nav_pct
  elif vol_ratio >= 1.25 and buy_ratio >= 53 and day_change_pct > 0.5:
    new_action = 'BUY'
    new_badge = 'MUA BÙNG NỔ (BREAKOUT)'
    new_subtag = 'BUY_ON_BREAKOUT'
    new_reason = (
        f"Dòng tiền lớn xác nhận với khối lượng x{vol_ratio} TB20, lực mua chủ động chiếm {buy_ratio}%, "
        f"giá tăng {day_change_pct:+.2f}% giữ trên EMA9 ({ema9:,.0f} đ). Đạt chuẩn đánh sóng T+."
    )
    new_alloc = pilot_nav_pct
  elif (current_price >= ema9 or current_price >= ma20) and dist_to_s1 <= 3.5 and 45 <= rsi <= 66 and buy_ratio >= 50 and rr_ratio >= 1.4:
    new_action = 'BUY'
    new_badge = 'MUA NỀN (PULLBACK T+)'
    new_subtag = 'BUY_ON_PULLBACK'
    new_reason = (
        f"Giá giữ vững trên EMA9 ({ema9:,.0f} đ), sát nền hỗ trợ S1 (+{dist_to_s1}%), RSI tích lũy đẹp ({rsi}). "
        f"Net R:R 1:{rr_ratio} đạt chuẩn giải ngân ngắn hạn."
    )
    new_alloc = pilot_nav_pct
  elif rsi > 70 or dist_to_s1 > 4.5:
    new_action = 'WAIT'
    new_badge = 'KHÔNG MUA ĐUỔI / CHỜ RETEST'
    new_subtag = 'WAIT_OVEREXTENDED'
    new_reason = (
        f"Giá hiện tại đã cách nền hỗ trợ S1 {dist_to_s1}% (>4.0%) hoặc RSI chạm {rsi} (vùng quá mua). "
        f"Mua mới lúc này có rủi ro dính nhịp rung lắc chỉnh T+2. Chờ test lại quanh {entry_a_max:,.0f} đ."
    )
    new_alloc = 0.0

  # =========================================================================
  # 2. NHÁNH VỊ THẾ ĐANG NẮM GIỮ (ĐÃ CÓ HÀNG)
  # =========================================================================
  hold_action = 'HOLD'
  hold_badge = 'TIẾP TỤC NẮM GIỮ (GỒNG LÃI)'
  hold_subtag = 'HOLD_TPLUS'
  hold_reason = f"Đà tăng ngắn hạn trên EMA9 ({ema9:,.0f} đ) duy trì tốt, chưa xuất hiện nến phân phối nguy hiểm. Tiếp tục gồng lãi, nâng mốc chặn lãi theo {trailing_stop_display}."
  hold_alloc = max_nav_pct

  if tail_lock_risk:
    hold_action = 'SELL'
    hold_badge = 'THOÁT HÀNG KHẨN CẤP (KẸT SÀN)'
    hold_subtag = 'EXIT_TAIL_LOCK'
    hold_reason = 'Phát hiện nguy cơ kẹt sàn mất thanh khoản nghiêm trọng. Ưu tiên đặt lệnh bán sớm để bảo toàn vốn khi còn bên mua.'
    hold_alloc = 0.0
  elif current_price <= stop_loss_price:
    hold_action = 'SELL'
    hold_badge = 'CẮT LỖ BẢO TOÀN VỐN'
    hold_subtag = 'CUT_LOSS_TPLUS'
    hold_reason = f'Giá đã xuyên thủng ngưỡng phòng thủ T+ ({stop_loss_price:,.0f} đ, -{downside_pct}%). Kỷ luật thoát toàn bộ vị thế.'
    hold_alloc = 0.0
  elif st_flip_sell:
    hold_action = 'SELL'
    hold_badge = 'THOÁT HÀNG / BẢO TOÀN LÃI (HỒNG RA)'
    hold_subtag = 'EXIT_SUPERTREND'
    hold_reason = (
        f"Chỉ báo SuperTrend vừa kích hoạt tín hiệu HỒNG RA (gãy dải hỗ trợ động quanh {st_band:,.0f} đ). "
        f"Ưu tiên chốt lời / thoát hàng để bảo toàn lợi nhuận và hạn chế rủi ro điều chỉnh T+."
    )
    hold_alloc = 0.0
  elif holding_tech.get('type') == 'danger' and holding_tech.get('action') == 'CẮT LỖ DỨT KHOÁT':
    hold_action = 'SELL'
    hold_badge = 'CẮT LỖ DỨT KHOÁT'
    hold_subtag = 'EXIT_TECHNICAL'
    hold_reason = f"Xuất hiện tín hiệu nến đảo chiều giảm mạnh và phe bán chiếm {100-buy_ratio:.1f}%. Thoát vị thế T+."
    hold_alloc = 0.0
  elif rsi > 72 or (rsi > 68 and buy_ratio < 45) or (holding_tech.get('type') == 'warning' and 'HẠ TỶ TRỌNG' in holding_tech.get('decision', '')):
    hold_action = 'REDUCE'
    hold_badge = 'HẠ TỶ TRỌNG (CHỐT LỜI 30-50%)'
    hold_subtag = 'TRIM_TPLUS'
    hold_reason = f'RSI ({rsi}) chạm vùng quá mua T+ hoặc tiệm cận cản {resist_r1:,.0f} đ (+{upside_r1_pct}%). Chủ động chốt lời 30-50% bảo vệ thành quả, giữ phần còn lại gồng theo trailing stop.'
    hold_alloc = round(max_nav_pct * 0.5, 1)
  elif vol_ratio >= 1.4 and buy_ratio >= 58 and day_change_pct >= 2.0 and current_price >= ema9:
    hold_action = 'ADD'
    hold_badge = 'MUA GIA TĂNG (+30% VỊ THẾ)'
    hold_subtag = 'PYRAMID_ADD'
    hold_reason = f'Dòng tiền cá mập bùng nổ vượt trội (Mua CĐ {buy_ratio}%, Vol x{vol_ratio} TB20), cho phép mua gia tăng vị thế khi đã có sẵn đệm lãi.'
    hold_alloc = max_nav_pct

  return {
      'horizon': 'Lướt sóng T+ (2-7 phiên)',
      'score': tplus_score,
      'pilotNavPct': pilot_nav_pct,
      'maxNavPct': max_nav_pct,
      'entryMin': entry_a_min,
      'entryMax': entry_a_max,
      'buyZone': f'{entry_a_min:,.0f} - {entry_a_max:,.0f} đ',
      'target': resist_r1,
      'targetDisplay': f'{resist_r1:,.0f} đ (+{upside_r1_pct}%)',
      'target2': resist_r2,
      'target2Display': f'{resist_r2:,.0f} đ',
      'takeProfit': f'{resist_r1:,.0f} - {resist_r2:,.0f} đ',
      'stopLoss': stop_loss_price,
      'stopLossDisplay': f'{stop_loss_price:,.0f} đ (-{downside_pct}%)',
      'trailingStop': trailing_stop,
      'trailingStopDisplay': trailing_stop_display,
      'sellPartialDisplay': f'Bán 50% quanh {resist_r1:,.0f} đ',
      'netRR': rr_ratio,
      'distSupportPct': dist_to_s1,
      'indicators': {
          'buyRatio': buy_ratio,
          'volRatio': vol_ratio,
          'rsi': rsi,
          'ema9': ema9,
          'ema21': ema21,
          'ma20': ma20,
          'hasBullishDivergence': has_bull_div,
          'divergenceDetail': div_detail,
      },
      'entries': [
          {
              'name': 'Entry T+ Thăm dò (Pullback)',
              'zone': f'{entry_a_min:,.0f} - {entry_a_max:,.0f} đ',
              'tactic': 'Gom quanh hỗ trợ ngắn hạn / EMA9',
              'allocationPct': pilot_nav_pct,
          },
          {
              'name': 'Entry T+ Bùng nổ (Breakout)',
              'zone': f'{entry_b_min:,.0f} - {entry_b_max:,.0f} đ',
              'tactic': 'Gia tăng khi dòng tiền quét cản với vol lớn',
              'allocationPct': pyramid_nav_pct,
          },
      ],
      'hardRules': {
          'triggeredCount': len(hard_rules),
          'rules': hard_rules,
          'isClean': len(hard_rules) == 0,
      },
      # Phân tách 2 góc nhìn vị thế
      'newEntry': {
          'action': new_action,
          'badge': new_badge,
          'subtag': new_subtag,
          'reason': new_reason,
          'allocatedNowPct': new_alloc,
          'targetDisplay': f'{resist_r1:,.0f} đ (+{upside_r1_pct}%)',
          'stopLossDisplay': f'{stop_loss_price:,.0f} đ (-{downside_pct}%)',
          'netRR': rr_ratio,
          'coreQuestions': {
              'why': [
                  f"Lực mua chủ động trong phiên đạt {buy_ratio}% với khối lượng x{vol_ratio} TB20.",
                  f"Xung lực RSI {rsi}" + (f" (Phát hiện phân kỳ dương đảo chiều)" if has_bull_div else f", giá vận động quanh EMA9 ({ema9:,.0f} đ)."),
                  f"Tỷ lệ Net R:R ngắn hạn đạt 1:{rr_ratio} với mục tiêu gần {resist_r1:,.0f} đ (+{upside_r1_pct}%).",
              ],
              'whyNotBuyNow': (
                  "Mã hiện tại ĐỦ ĐIỀU KIỆN MUA MỚI T+. Vào lệnh tuân thủ tỷ trọng và cắt lỗ."
                  if new_action == 'BUY'
                  else (
                      f"Giá đã tăng cách nền {dist_to_s1}% hoặc RSI chạm {rsi} (vùng quá mua). Mua đuổi lúc này có rủi ro kẹt hàng chiều T+2."
                      if new_action == 'WAIT' and (rsi > 70 or dist_to_s1 > 4.0)
                      else f"Chưa có tín hiệu dòng tiền bứt phá rõ nét (Phe bán còn chiếm {100-buy_ratio:.1f}%). Kiên nhẫn chờ điểm nổ vol."
                  )
              ),
              'whatWillChangeSignal': (
                  f"Tín hiệu sẽ chốt lời nếu giá vượt {resist_r1:,.0f} đ, hoặc cắt lỗ nếu thủng {stop_loss_price:,.0f} đ."
                  if new_action == 'BUY'
                  else f"Tín hiệu sẽ chuyển sang BUY T+ khi xuất hiện phiên nổ vol > 1.25x TB20 kèm lực mua chủ động > 53%, hoặc test thành công hỗ trợ {support_s1:,.0f} đ."
              ),
          },
      },
      'holding': {
          'action': hold_action,
          'badge': hold_badge,
          'subtag': hold_subtag,
          'reason': hold_reason,
          'allocatedNowPct': hold_alloc,
          'trailingStopDisplay': trailing_stop_display,
          'targetDisplay': f'{resist_r1:,.0f} đ (+{upside_r1_pct}%)',
          'coreQuestions': {
              'why': [
                  f"Vị thế đang được bảo vệ bởi Trailing Stop động tại {trailing_stop_display}.",
                  f"Xung lực nến và khối lượng phiên: Mua CĐ {buy_ratio}%, Vol x{vol_ratio} TB20.",
                  f"Kháng cự chốt lời gần nhất: {resist_r1:,.0f} đ (+{upside_r1_pct}%).",
              ],
              'whyNotBuyNow': (
                  f"Đang nắm giữ: Chờ tín hiệu vượt cản {resist_r1:,.0f} đ để kích hoạt điểm mua gia tăng (ADD), không mua đuổi khi RSI > 68."
              ),
              'whatWillChangeSignal': (
                  f"Kích hoạt chốt lời chủ động 30-50% nếu giá chạm {resist_r1:,.0f} đ; Thoát hết nếu đóng cửa thủng {trailing_stop_display}."
              ),
          },
      },
      # Mặc định top-level cho T+
      'action': new_action,
      'badge': new_badge,
      'subtag': new_subtag,
      'reason': new_reason,
      'allocatedNowPct': new_alloc,
  }


def evaluate_midterm_strategy(
    ticker,
    exchange_clean,
    current_price,
    fund,
    tech,
    reg,
    risk,
):
  """Động cơ Trung & Dài Hạn (3-12+ tháng) phân tách Mua Mới vs Đang Nắm Giữ."""
  fa_score = fund.get('faScore', 50)
  roe = fund.get('roe', 0.0)
  profit_growth = fund.get('profitGrowth', 0.0)
  debt_to_equity = fund.get('debtToEquity', 0.0)
  cfo_status = fund.get('ocfStatus', '')
  pe = fund.get('pe', 0.0)
  pb = fund.get('pb', 0.0)

  mid_term_val = tech.get('midTerm', {})
  valuation_band = mid_term_val.get('valuationBand') or {}
  fair_mid = valuation_band.get('fairMid') or (round(current_price * 1.15, -2) if fa_score >= 65 else current_price)
  fair_low = valuation_band.get('fairLow') or round(fair_mid * 0.9, -2)
  fair_high = valuation_band.get('fairHigh') or round(fair_mid * 1.15, -2)

  margin_of_safety_pct = round(((fair_mid - current_price) / current_price) * 100, 1) if current_price > 0 else 0.0

  regime_name = reg.get('regime', 'NEUTRAL')
  regime_score = reg.get('score', 3)
  dc_score = risk.get('dcScore', 100)
  has_legal = risk.get('fundamentalRisk', {}).get('hasLegalDisputes', False)
  has_dilution = risk.get('fundamentalRisk', {}).get('hasDilutionRisk', False)

  hard_rules_mid = []
  if dc_score < 70:
    hard_rules_mid.append(f"🔍 DỮ LIỆU CHƯA ĐẦY ĐỦ: Điểm tin cậy BCTC {dc_score}/100 (< 70). Cần kiểm toán đầy đủ trước khi đầu tư dài hạn.")
  if 'Cảnh báo' in cfo_status:
    hard_rules_mid.append("⚠️ DÒNG TIỀN KINH DOANH ÂM: Dòng tiền thuần từ HĐKD (CFO) âm liên tục, chất lượng lợi nhuận thấp.")
  if has_legal:
    hard_rules_mid.append("⚠️ RỦI RO PHÁP LÝ / QUẢN TRỊ: Doanh nghiệp có vướng mắc pháp lý trọng yếu.")
  if has_dilution:
    hard_rules_mid.append("⚠️ RỦI RO PHA LOÃNG: Phát hiện kế hoạch phát hành thêm cổ phiếu làm loãng EPS.")
  if regime_name == 'NO_NEW_RISK':
    hard_rules_mid.append(f"⛔ VĨ MÔ SUY THOÁI: Thị trường chung trong trạng thái rủi ro cao ({regime_score}/5 tiêu chí). Hạn chế tích sản quy mô lớn.")

  qual_score = fa_score
  if roe >= 18.0:
    qual_score = min(100, qual_score + 8)
  if profit_growth >= 15.0:
    qual_score = min(100, qual_score + 6)
  if margin_of_safety_pct >= 20.0:
    qual_score = min(100, qual_score + 10)
  elif margin_of_safety_pct < 0.0:
    qual_score = max(20, qual_score - 12)
  if debt_to_equity > 2.0:
    qual_score = max(20, qual_score - 8)

  support_w = tech.get('support2', round(current_price * 0.88, -2))
  stop_inval = round(support_w * 0.95, -2)

  # 1. NHÁNH MUA MỚI TRUNG HẠN
  if qual_score >= 65 and margin_of_safety_pct >= 10.0 and dc_score >= 70 and not has_legal and regime_name != 'NO_NEW_RISK':
    new_mid_action = 'BUY'
    new_mid_badge = 'TÍCH SẢN / GOM DẦN'
    new_mid_subtag = 'ACCUMULATE_VALUE'
    new_mid_reason = (
        f"Doanh nghiệp cơ bản tốt (FA {fa_score}/100, ROE {roe:.1f}%), "
        f"thị giá đang chiết khấu hấp dẫn dưới giá trị hợp lý {fair_mid:,.0f} đ (Biên an toàn +{margin_of_safety_pct}%). Thích hợp gom tích sản."
    )
    new_mid_alloc = 10.0
  else:
    new_mid_action = 'WAIT'
    new_mid_badge = 'CHỜ CHIẾT KHẤU ĐỊNH GIÁ'
    new_mid_subtag = 'WAIT_VALUATION'
    new_mid_reason = f"Biên an toàn hiện tại (+{margin_of_safety_pct}%) chưa đủ hấp dẫn để gom mới, hoặc thị trường đang phòng thủ. Chờ chiết khấu sâu hơn về vùng {fair_low:,.0f} đ."
    new_mid_alloc = 0.0

  # 2. NHÁNH ĐANG NẮM GIỮ TRUNG HẠN
  if has_legal or ('Cảnh báo' in cfo_status and fa_score < 40):
    hold_mid_action = 'SELL'
    hold_mid_badge = 'THOÁT VỊ THẾ DOANH NGHIỆP'
    hold_mid_subtag = 'EXIT_FUNDAMENTAL'
    hold_mid_reason = 'Luận điểm cơ bản doanh nghiệp bị suy thoái nghiêm trọng (dòng tiền âm hoặc vướng pháp lý). Thoát vị thế trung hạn.'
    hold_mid_alloc = 0.0
  elif margin_of_safety_pct < -15.0 and pe > 25.0:
    hold_mid_action = 'REDUCE'
    hold_mid_badge = 'HẠ TỶ TRỌNG (ĐỊNH GIÁ CAO)'
    hold_mid_subtag = 'TRIM_OVERVALUED'
    hold_mid_reason = f'Thị giá đã vượt quá xa định giá BCTC hợp lý (P/E {pe:.1f}x, biên định giá {margin_of_safety_pct}%). Chủ động chốt lời dần.'
    hold_mid_alloc = 5.0
  else:
    hold_mid_action = 'HOLD'
    hold_mid_badge = 'TIẾP TỤC NẮM GIỮ GIÁ TRỊ'
    hold_mid_subtag = 'HOLD_VALUE'
    hold_mid_reason = f"Doanh nghiệp duy trì nền tảng tài chính ổn định (ROE {roe:.1f}%), định giá quanh vùng hợp lý ({fair_mid:,.0f} đ). Tiếp tục nắm giữ đồng hành cùng doanh nghiệp."
    hold_mid_alloc = 15.0

  return {
      'horizon': 'Trung & Dài hạn (3-12+ tháng)',
      'score': qual_score,
      'entryMin': fair_low,
      'entryMax': fair_mid,
      'buyZone': f'{fair_low:,.0f} - {fair_mid:,.0f} đ',
      'target': fair_mid,
      'targetDisplay': f'{fair_mid:,.0f} đ (+{margin_of_safety_pct}%)',
      'target1Display': f'{fair_mid:,.0f} đ',
      'targetHigh': fair_high,
      'target2Display': f'{fair_high:,.0f} đ',
      'fairLow': fair_low,
      'stopLoss': stop_inval,
      'stopLossDisplay': f'{stop_inval:,.0f} đ (Vô hiệu hóa tuần)',
      'riskThresholdDisplay': f'< {stop_inval:,.0f} đ',
      'mocGiaTang': f'Vượt cản {fair_mid:,.0f} đ với vol lớn',
      'mocHaTyTrong': f'Đóng nến tuần dưới {stop_inval:,.0f} đ',
      'kyVongChuKy': f'+{margin_of_safety_pct:.1f}%' if margin_of_safety_pct > 0 else f'Hết biên an toàn ({margin_of_safety_pct:.1f}%)',
      'marginOfSafetyPct': margin_of_safety_pct,
      'pe': pe,
      'pb': pb,
      'roe': roe,
      'cfoStatus': cfo_status,
      'hardRules': {
          'triggeredCount': len(hard_rules_mid),
          'rules': hard_rules_mid,
          'isClean': len(hard_rules_mid) == 0,
      },
      'newEntry': {
          'action': new_mid_action,
          'badge': new_mid_badge,
          'subtag': new_mid_subtag,
          'reason': new_mid_reason,
          'allocatedNowPct': new_mid_alloc,
          'targetDisplay': f'{fair_mid:,.0f} đ (+{margin_of_safety_pct}%)',
          'stopLossDisplay': f'{stop_inval:,.0f} đ',
          'coreQuestions': {
              'why': [
                  f"Chất lượng tài chính doanh nghiệp: FA {fa_score}/100, ROE {roe:.1f}%, P/E {pe:.1f}x.",
                  f"Định giá BCTC hợp lý: {fair_mid:,.0f} đ (Biên an toàn {margin_of_safety_pct:+1.1f}%).",
                  f"Bối cảnh vĩ mô / Market Regime: {regime_name} ({regime_score}/5 tiêu chí đạt chuẩn).",
              ],
              'whyNotBuyNow': (
                  "Cổ phiếu ĐẠT CHUẨN TÍCH SẢN TRUNG HẠN. Giải ngân từng phần theo kế hoạch phân bổ vốn."
                  if new_mid_action == 'BUY'
                  else f"Biên an toàn định giá (+{margin_of_safety_pct}%) chưa đủ lớn (> 10%), hoặc thị trường đang ở pha phòng thủ. Kiên nhẫn chờ nhịp chiết khấu sâu."
              ),
              'whatWillChangeSignal': (
                  f"Tín hiệu sẽ chốt lời khi thị giá chạm vùng P/E đỉnh {fair_high:,.0f} đ, hoặc thoái vốn nếu BCTC quý tới suy giảm LNST > 25%."
                  if new_mid_action == 'BUY'
                  else f"Tín hiệu sẽ chuyển sang BUY TÍCH SẢN khi thị giá điều chỉnh về vùng chiết khấu {fair_low:,.0f} đ, tạo biên an toàn > 15%."
              ),
          },
      },
      'holding': {
          'action': hold_mid_action,
          'badge': hold_mid_badge,
          'subtag': hold_mid_subtag,
          'reason': hold_mid_reason,
          'allocatedNowPct': hold_mid_alloc,
          'invalidationDisplay': f'{stop_inval:,.0f} đ',
          'targetDisplay': f'{fair_mid:,.0f} đ (+{margin_of_safety_pct}%)',
          'coreQuestions': {
              'why': [
                  f"Doanh nghiệp cơ bản tốt (ROE {roe:.1f}%, FA {fa_score}/100).",
                  f"Định giá quanh vùng hợp lý ({fair_mid:,.0f} đ), chưa có dấu hiệu suy thoái nghiêm trọng.",
                  f"Ngưỡng vô hiệu hóa xu hướng tuần: {stop_inval:,.0f} đ.",
              ],
              'whyNotBuyNow': "Đang nắm giữ trung hạn: Không bình quân giá vội vàng khi chưa về vùng chiết khấu sâu.",
              'whatWillChangeSignal': f"Hạ tỷ trọng khi giá vượt {fair_high:,.0f} đ (P/E quá cao) hoặc thoái lui dứt khoát nếu thủng {stop_inval:,.0f} đ.",
          },
      },
      # Mặc định top-level
      'action': new_mid_action,
      'badge': new_mid_badge,
      'subtag': new_mid_subtag,
      'reason': new_mid_reason,
      'allocatedNowPct': new_mid_alloc,
  }


def evaluate_unified_decision(
    ticker,
    exchange,
    current_price,
    fundamental_info,
    technical_info,
    regime=None,
    risk_engine_report=None,
):
  """Tổng hợp và phân tách 2 chiều: Lướt sóng T+ vs Trung/Dài Hạn x Mua Mới vs Đang Nắm Giữ."""
  exchange_clean = (exchange or 'HOSE').upper()
  fund = fundamental_info or {}
  tech = technical_info or {}
  reg = regime or {}
  risk = risk_engine_report or {}

  # Chạy 2 động cơ độc lập
  tplus_data = evaluate_tplus_strategy(
      ticker=ticker,
      exchange_clean=exchange_clean,
      current_price=current_price,
      tech=tech,
      reg=reg,
      risk=risk,
  )

  midterm_data = evaluate_midterm_strategy(
      ticker=ticker,
      exchange_clean=exchange_clean,
      current_price=current_price,
      fund=fund,
      tech=tech,
      reg=reg,
      risk=risk,
  )

  # Cấu trúc Quality & Timing
  quality_output = {
      'score': midterm_data['score'],
      'label': 'Sức khỏe tài chính tốt' if midterm_data['score'] >= 65 else 'Cần thận trọng / Trung bình',
      'faScore': fund.get('faScore', 50),
      'roe': fund.get('roe', 0.0),
      'profitGrowth': fund.get('profitGrowth', 0.0),
      'debtToEquity': fund.get('debtToEquity', 0.0),
      'cfoStatus': fund.get('ocfStatus', ''),
      'pe': fund.get('pe', 0.0),
      'pb': fund.get('pb', 0.0),
      'fairMid': midterm_data['target'],
      'marginOfSafetyPct': midterm_data['marginOfSafetyPct'],
  }

  timing_output = {
      'score': tplus_data['score'],
      'label': 'Xung lực T+ mạnh' if tplus_data['score'] >= 65 else 'Chờ xác nhận thêm tín hiệu',
      'taScore': tech.get('taScore', 50),
      'rsi': tech.get('rsi', 50.0),
      'ma20': tech.get('ma20', current_price),
      'ema9': tech.get('ema9', current_price),
      'ema21': tech.get('ema21', current_price),
      'volRatio': tech.get('volRatio', 1.0),
      'buyRatio': tech.get('buyRatio', 50.0),
      'rsScore': tech.get('rs', {}).get('rsScore', 50),
      'regime': reg.get('regime', 'NEUTRAL'),
  }

  # Targets & Stops
  targets_and_stops = {
      'tp1': {
          'label': 'TP1 (Trading T+)',
          'price': tplus_data['target'],
          'display': tplus_data['targetDisplay'],
          'basis': 'Kháng cự Fractal R1 gần nhất',
      },
      'tp2': {
          'label': 'TP2 (Kỹ thuật Trung hạn)',
          'price': tplus_data['target2'],
          'display': f"{tplus_data['target2']:,.0f} đ",
          'basis': 'Kháng cự Fractal R2 / Vùng cản tuần',
      },
      'tp3': {
          'label': 'TP3 (Định giá BCTC hợp lý)',
          'price': midterm_data['target'],
          'display': midterm_data['targetDisplay'],
          'basis': 'Dải Multiple P/E 12 quý BCTC',
      },
      'stopLoss': {
          'label': 'Stop Loss (Cắt lỗ T+)',
          'price': tplus_data['stopLoss'],
          'display': tplus_data['stopLossDisplay'],
          'basis': 'Hỗ trợ S1 trừ 0.5x ATR14',
      },
      'hardInvalidation': {
          'label': 'Hard Invalidation (Vô hiệu hóa)',
          'price': midterm_data['stopLoss'],
          'display': midterm_data['stopLossDisplay'],
          'basis': 'Thủng hỗ trợ nền tuần dài hạn',
      },
      'trailingStop': {
          'label': 'Trailing Stop (Chặn lãi bảo vệ vốn)',
          'price': tplus_data['trailingStop'],
          'display': tplus_data['trailingStopDisplay'],
          'basis': 'Chặn lãi động theo Fractal & mẫu hình nến',
      },
  }

  # Tính toán xác suất & kỳ vọng toán học (EV) thực tế
  p_bull = 0.50 if tplus_data['score'] >= 60 else 0.30
  p_base = 0.35
  p_bear = 0.15 if tplus_data['score'] >= 60 else 0.35

  bull_ret = round(((tplus_data['target'] - current_price) / current_price) * 100, 1) if current_price > 0 else 0.0
  base_target = round((current_price + tplus_data['target']) / 2, -2)
  base_ret = round(((base_target - current_price) / current_price) * 100, 1) if current_price > 0 else 0.0
  bear_ret = -round(((current_price - tplus_data['stopLoss']) / current_price) * 100, 1) if current_price > 0 else 0.0

  expected_val_pct = round((p_bull * bull_ret + p_base * base_ret + p_bear * bear_ret), 1)

  scenarios_output = {
      'bullCase': {
          'name': 'Kịch bản Khả quan (Bull)',
          'target': tplus_data['target'],
          'targetDisplay': tplus_data['targetDisplay'],
          'returnPct': bull_ret,
          'probability': int(p_bull * 100),
      },
      'baseCase': {
          'name': 'Kịch bản Cơ sở (Base)',
          'target': base_target,
          'targetDisplay': f"{base_target:,.0f} đ",
          'returnPct': base_ret,
          'probability': int(p_base * 100),
      },
      'bearCase': {
          'name': 'Kịch bản Phòng thủ (Bear)',
          'target': tplus_data['stopLoss'],
          'targetDisplay': tplus_data['stopLossDisplay'],
          'returnPct': bear_ret,
          'probability': int(p_bear * 100),
      },
      'expectedValuePct': expected_val_pct,
      'netRR': tplus_data['netRR'],
  }

  # 1. Tổng quan tín hiệu (Overall Signal)
  if tplus_data['hardRules']['triggeredCount'] > 0 or midterm_data['hardRules']['triggeredCount'] > 0:
    overall_signal = {
        'status': 'DANGER',
        'badge': 'CẢNH BÁO RỦI RO - BẢO VỆ VỐN / THOÁT VỊ THẾ',
        'type': 'danger',
    }
  elif tplus_data['score'] >= 65 or tplus_data['newEntry']['action'] == 'BUY':
    overall_signal = {
        'status': 'POSITIVE',
        'badge': 'TÍCH CỰC - ƯU TIÊN MUA GIA TĂNG / MUA MỚI KHI RUNG LẮC',
        'type': 'positive',
    }
  elif tplus_data['score'] >= 50 or midterm_data['score'] >= 60:
    overall_signal = {
        'status': 'NEUTRAL',
        'badge': 'TRUNG TÍNH - TÍCH LŨY NỀN / QUAN SÁT TÍN HIỆU DÒNG TIỀN',
        'type': 'neutral',
    }
  else:
    overall_signal = {
        'status': 'DEFENSIVE',
        'badge': 'THẬN TRỌNG - ƯU TIÊN QUẢN TRỊ RỦI RO / KHÔNG MUA ĐUỔI',
        'type': 'caution',
    }

  # 2. Tag trạng thái tức thời theo thị giá (Price Action Status Tag)
  stop_loss_val = tplus_data.get('stopLoss', 0)
  resist_r1_val = tplus_data.get('target', 0)
  entry_min_val = tplus_data.get('entryMin', 0)
  entry_max_val = tplus_data.get('entryMax', 0)

  if current_price <= stop_loss_val and current_price > 0:
    price_status_tag = {
        'status': 'STOP_LOSS',
        'badge': f'🚨 VI PHẠM CẮT LỖ (< {stop_loss_val:,.0f} đ)',
        'advice': 'Thoát vị thế ngay, kỷ luật bảo toàn vốn',
        'color': 'rose',
    }
  elif current_price >= resist_r1_val and resist_r1_val > 0:
    price_status_tag = {
        'status': 'TARGET_REACHED',
        'badge': f'🎯 ĐÃ ĐẠT TARGET T+ ({resist_r1_val:,.0f} đ)',
        'advice': 'Chủ động chốt lời 50%, nâng chặn lãi',
        'color': 'emerald',
    }
  elif entry_min_val <= current_price <= entry_max_val and entry_min_val > 0:
    price_status_tag = {
        'status': 'IN_BUY_ZONE',
        'badge': f'✅ ĐẠT ĐIỂM MUA AN TOÀN ({entry_min_val:,.0f} - {entry_max_val:,.0f} đ)',
        'advice': 'Giải ngân thăm dò 30% NAV, tuân thủ kỷ luật',
        'color': 'emerald',
    }
  elif current_price > entry_max_val and entry_max_val > 0:
    diff_pct = round(((current_price - entry_max_val) / entry_max_val) * 100, 1)
    price_status_tag = {
        'status': 'WAIT_PULLBACK',
        'badge': f'⏳ CHỜ RUNG LẮC VỀ VÙNG MUA ({entry_min_val:,.0f} - {entry_max_val:,.0f} đ)',
        'advice': f'Giá đã vượt vùng mua an toàn (+{diff_pct}%), không mua đuổi',
        'color': 'amber',
    }
  else:
    price_status_tag = {
        'status': 'NEAR_SUPPORT',
        'badge': f'👀 THEO DÕI HỖ TRỢ ({entry_min_val:,.0f} đ)',
        'advice': 'Chờ nến giữ vững hỗ trợ trước khi mở vị thế',
        'color': 'blue',
    }

  # 3. Luận điểm cốt lõi (3 dòng then chốt)
  ma20_val = tech.get('ma20', current_price)
  rsi_val = tech.get('rsi', 50.0)
  buy_ratio_val = tech.get('buyRatio', 50.0)
  vol_ratio_val = tech.get('volRatio', 1.0)
  has_bull_div = tech.get('rsiDivergence', {}).get('hasBullishDivergence', False)
  div_note = ' (xuất hiện phân kỳ dương)' if has_bull_div else ''
  ma20_rel = 'tạo nền trên MA20' if current_price >= ma20_val else 'vận động dưới MA20'

  fa_score = fund.get('faScore', 50)
  roe_val = fund.get('roe', 0.0)
  prof_growth = fund.get('profitGrowth', 0.0)
  margin_safe = midterm_data.get('marginOfSafetyPct', 0.0)

  core_thesis = {
      'technical': f"1. Đồ thị kỹ thuật (120D): Giá {ma20_rel} ({ma20_val:,.0f} đ), RSI {rsi_val:.0f}{div_note}; Mua chủ động {buy_ratio_val}%, Vol x{vol_ratio_val} TB20.",
      'fundamental': f"2. Động lực cơ bản: FA {fa_score}/100, ROE {roe_val:.1f}%, Tăng trưởng LN {prof_growth:+1.1f}%, Biên an toàn định giá {margin_safe:+1.1f}%.",
      'risk': f"3. Kịch bản quản trị: Vùng {resist_r1_val:,.0f} đ là cản đỉnh/R1, không mua đuổi khi giá > {entry_max_val:,.0f} đ; Cắt lỗ tuyệt đối nếu thủng {stop_loss_val:,.0f} đ (Net R/R 1:{tplus_data['netRR']}).",
  }

  return {
      'ticker': ticker,
      'exchange': exchange_clean,
      'currentPrice': current_price,
      'activeHorizon': 'tPlus',
      'activePosition': 'newEntry',
      'overallSignal': overall_signal,
      'priceStatusTag': price_status_tag,
      'coreThesis': core_thesis,
      'tPlus': tplus_data,
      'midTerm': midterm_data,
      # Tương thích ngược: Mặc định Mua Mới của T+
      'primaryAction': tplus_data['newEntry']['action'],
      'actionSubtag': tplus_data['newEntry']['subtag'],
      'actionBadge': tplus_data['newEntry']['badge'],
      'actionReason': tplus_data['newEntry']['reason'],
      'horizonFocus': 'Lướt sóng T+ (Ngắn hạn)',
      'quality': quality_output,
      'timing': timing_output,
      'hardRules': tplus_data['hardRules'],
      'positionSizing': {
          'action': tplus_data['newEntry']['action'],
          'allocatedNowPct': tplus_data['newEntry']['allocatedNowPct'],
          'initialPositionPct': tplus_data['pilotNavPct'],
          'targetPositionPct': tplus_data['maxNavPct'],
          'maxPositionPct': tplus_data['maxNavPct'],
      },
      'entries': tplus_data['entries'],
      'targetsAndStops': targets_and_stops,
      'scenarios': scenarios_output,
      'coreQuestions': tplus_data['newEntry']['coreQuestions'],
  }
