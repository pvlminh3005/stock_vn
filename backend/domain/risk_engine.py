"""
Stock RT - Securities Risk Assessment Engine
Chuyên gia định lượng & đánh giá rủi ro chứng khoán:
- Fear & Greed Index (0 - 100)
- Dòng vốn khối ngoại & thanh khoản
- Dò rủi ro pháp lý & pha loãng từ khóa trên tin tức gắn mã
- Ma trận kịch bản Bull / Bear kèm tỷ lệ R:R
- Hệ thống Guardrail bảo toàn vốn (Tail Lock Risk kẹt sàn, pháp lý, vĩ mô)
- Data Confidence Score (0 - 100)
"""

from backend.constants.sectors import FINANCIAL_SECTORS
from backend.constants.config import T_PLUS_RISK_BUDGET_PCT
from backend.utils.time_utils import vn_date
from backend.utils.ohlc_helpers import period_key, expected_latest_report_period
from backend.data_providers.news_provider import news_age_days
from backend.domain.valuation import assess_financial_distress
from backend.domain.outlook import build_macro_context

GOVERNANCE_NEWS_MAX_AGE_DAYS = 90


def calculate_market_fear_greed_index(ssi_board, ssi_item, technical_info):
  """Chỉ số Tâm Lý Thị Trường & Cổ Phiếu (Securities Market Fear & Greed Index: 0 - 100).

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
  """Dò từ khóa rủi ro pháp lý, pha loãng và biến động lãnh đạo trên tiêu đề tin GẮN ĐÚNG MÃ.

  - Không quét tin vĩ mô/thời sự chung và mô tả doanh nghiệp (dễ khớp nhầm 'kiểm soát', 'vi phạm'...).
  - Kết quả là dò từ khóa tự động: luôn ở trạng thái CHƯA XÁC MINH, cần đối chiếu công bố gốc HOSE/HNX/UBCKNN.
  - Không tìm thấy từ khóa không đồng nghĩa với không có rủi ro pháp lý.
  """
  legal_keywords = [
      'khởi tố', 'bị bắt', 'tạm giam', 'truy tố', 'truy cứu', 'thanh tra',
      'xử phạt', 'bị phạt', 'phạt vi phạm', 'thao túng', 'hủy niêm yết',
      'đình chỉ giao dịch', 'tạm ngừng giao dịch', 'diện cảnh báo', 'diện kiểm soát',
      'hạn chế giao dịch', 'kê biên', 'phong tỏa', 'bị kiện', 'khởi kiện', 'tranh chấp',
      'mất khả năng thanh toán', 'chậm thanh toán', 'chậm trả lãi', 'ý kiến ngoại trừ',
      'từ chối đưa ra ý kiến', 'giải chấp', 'bán giải chấp', 'phá sản',
  ]
  dilution_keywords = [
      'phát hành riêng lẻ', 'chào bán riêng lẻ', 'chào bán cổ phiếu', 'chào bán thêm',
      'trái phiếu chuyển đổi', 'pha loãng', 'quyền mua cổ phiếu',
  ]
  mgmt_keywords = [
      'từ nhiệm', 'miễn nhiệm', 'bãi nhiệm', 'thay đổi ban lãnh đạo', 'esop',
  ]

  legal_findings = []
  dilution_findings = []
  mgmt_findings = []

  scanned = 0
  for n in news_list or []:
    if not n.get('tickerSpecific'):
      continue
    title = n.get('title', '')
    if not title:
      continue
    age = news_age_days(n.get('date', ''))
    if age is not None and age > GOVERNANCE_NEWS_MAX_AGE_DAYS:
      continue
    scanned += 1
    date_txt = n.get('date') or 'không rõ ngày'
    label = f"{title} ({n.get('source', 'Tin tức')}, {date_txt})"
    lower_text = title.lower()
    if any(kw in lower_text for kw in legal_keywords):
      legal_findings.append(label)
    if any(kw in lower_text for kw in dilution_keywords):
      dilution_findings.append(label)
    if any(kw in lower_text for kw in mgmt_keywords):
      mgmt_findings.append(label)

  has_legal = len(legal_findings) > 0
  has_dilution = len(dilution_findings) > 0

  parts = []
  if has_legal:
    parts.append(f"⚠️ TIN CÓ TỪ KHÓA PHÁP LÝ (chưa xác minh): '{legal_findings[0]}'. Cần đọc nguyên văn công bố trên HOSE/HNX/UBCKNN để đánh giá mức độ.")
  if has_dilution:
    parts.append(f"⚠️ TIN CÓ TỪ KHÓA PHA LOÃNG (chưa xác minh): '{dilution_findings[0]}'. Kiểm tra giá phát hành, tỷ lệ và đối tượng chào bán.")
  if mgmt_findings:
    parts.append(f"Ghi nhận thông tin nhân sự/ESOP: '{mgmt_findings[0]}'.")

  if parts:
    governance_summary = ' '.join(parts)
  elif scanned == 0:
    governance_summary = 'Pháp lý & pha loãng: chưa đủ dữ liệu (không lấy được tin gắn mã trong 90 ngày gần nhất).'
  else:
    governance_summary = (
        f'Chưa phát hiện từ khóa rủi ro pháp lý/pha loãng trong {scanned} tin gắn mã gần nhất. '
        'Đây chỉ là dò tiêu đề tự động, chưa thay thế việc đối chiếu công bố thông tin HOSE/HNX/UBCKNN.'
    )

  return has_legal, has_dilution, legal_findings, dilution_findings, governance_summary


def compute_data_confidence(ssi_item, fundamental_info, technical_info, news_list, has_legal_unverified, regime):
  """Data Confidence (0 - 100) theo spec vsr-engine: bắt đầu 100, trừ điểm cho từng thiếu sót.

  DC < 65 -> chỉ WAIT/NO_TRADE; BUY yêu cầu DC >= 80.
  """
  dc = 100
  deductions = []

  latest_session = (regime or {}).get('asOf', '')
  session_start = (ssi_item or {}).get('sessionStart')
  price_date = vn_date(session_start / 1000.0) if session_start and (ssi_item or {}).get('refPrice') else None
  if not price_date:
    dc -= 30
    deductions.append('-30 không lấy được giá từ bảng giá realtime')
  elif latest_session and price_date < latest_session:
    dc -= 30
    deductions.append(f'-30 giá thuộc phiên {price_date}, cũ hơn phiên gần nhất {latest_session}')

  period = period_key((fundamental_info or {}).get('reportPeriod', ''))
  expected = expected_latest_report_period()
  if not period:
    dc -= 15
    deductions.append('-15 thiếu BCTC')
  elif expected and period < expected:
    dc -= 15
    deductions.append(f'-15 BCTC kỳ {period[0]}-Q{period[1]} cũ hơn kỳ đã quá hạn công bố {expected[0]}-Q{expected[1]}')

  if (technical_info or {}).get('volMa20', 0) <= 0:
    dc -= 15
    deductions.append('-15 thiếu dữ liệu khối lượng')

  if not any(n.get('tickerSpecific') for n in (news_list or [])):
    dc -= 20
    deductions.append('-20 chưa có tin gắn mã từ nguồn Tier 1-2')

  conflicts = (fundamental_info or {}).get('dataConflicts') or []
  if conflicts:
    dc -= 15
    deductions.append('-15 DATA_CONFLICT (' + '; '.join(conflicts) + ')')

  if has_legal_unverified:
    dc -= 10
    deductions.append('-10 tin pháp lý trọng yếu chưa xác minh')

  return max(0, dc), deductions


def evaluate_securities_risk_engine(ticker, sector, current_price, fundamental_info, technical_info, ssi_item, ssi_board, news_list):
  """CHUYÊN GIA ĐỊNH LƯỢNG & ĐÁNH GIÁ RỦI RO CHỨNG KHOÁN (SECURITIES RISK ASSESSMENT ENGINE)

  Triển khai quy trình phân tích định lượng chuẩn 5 phần và hệ thống Guardrail ngưỡng chặn rủi ro.
  Tuân thủ 3 nguyên tắc bất di bất dịch (Grounding Rules):
  1. Không suy diễn ngoài dữ liệu (nếu thiếu, ghi 'Dữ liệu chưa ghi nhận').
  2. Khách quan đa chiều (nhận định tích cực luôn đi kèm yếu tố rủi ro tương ứng).
  3. Phân biệt rõ giữa dữ liệu thực tế lịch sử/hiện tại và kịch bản dự báo xác suất.
  """
  env_rating, env_color, macro_impact = build_macro_context(news_list)

  fear_greed_score, fear_greed_label, fear_greed_color = calculate_market_fear_greed_index(
      ssi_board, ssi_item, technical_info
  )

  buy_f = ssi_item.get('buyForeignQtty', 0) if ssi_item else 0
  sell_f = ssi_item.get('sellForeignQtty', 0) if ssi_item else 0
  foreign_net = buy_f - sell_f
  vol_ratio = technical_info.get('volRatio', 1.0)
  buy_ratio = technical_info.get('buyRatio', 50.0)

  if foreign_net > 100000:
    foreign_flow_text = (
        f'Khối ngoại mua ròng tích cực +{foreign_net:,.0f} cổ phiếu trong phiên ngắn hạn '
        f'(Khối lượng mua: {buy_f:,.0f} cp vs Bán: {sell_f:,.0f} cp). Dòng tiền ngoại nâng đỡ tâm lý, '
        'tuy nhiên cần kiểm định mức độ duy trì dòng vốn ngoại khi chỉ số tiến sát kháng cự đỉnh cũ.'
    )
  elif foreign_net < -50000:
    foreign_flow_text = (
        f'Khối ngoại bán ròng đáng kể -{abs(foreign_net):,.0f} cổ phiếu trong phiên ngắn hạn '
        f'(Khối lượng mua: {buy_f:,.0f} cp vs Bán: {sell_f:,.0f} cp). Áp lực cơ cấu chốt lời từ dòng vốn '
        'ngoại tạo áp lực cung tiềm ẩn lên các nhịp tăng giá.'
    )
  elif foreign_net < 0:
    foreign_flow_text = (
        f'Khối ngoại bán ròng nhẹ -{abs(foreign_net):,.0f} cổ phiếu trong phiên, giao dịch tương đối cân bằng. '
        'Dòng tiền nội địa giữ vai trò chủ đạo chi phối bước giá.'
    )
  else:
    foreign_flow_text = (
        f'Khối ngoại giao dịch cân bằng (Ròng: {foreign_net:+,.0f} cp, Mua: {buy_f:,.0f} vs Bán: {sell_f:,.0f} cp). '
        'Xu hướng trung hạn ổn định, cổ phiếu vận động theo cung cầu tự nhiên thị trường.'
    )

  rs_info = technical_info.get('rs', {}) if technical_info else {}
  rs_score = rs_info.get('rsScore', 50)
  alpha_1m = rs_info.get('stockAlpha1M', 0.0)
  alpha_3m = rs_info.get('stockAlpha3M', 0.0)

  sentiment_liquidity_text = (
      f'Chỉ số Tâm lý thị trường ghi nhận {fear_greed_score}/100 ({fear_greed_label}). '
      f'Thanh khoản đạt {vol_ratio}x mức bình quân 20 phiên với tỷ lệ mua chủ động {buy_ratio}%, '
      f"cho thấy mức độ hấp thụ cung-cầu {'tích cực, phe mua kiểm soát thế trận' if buy_ratio >= 52 else 'thận trọng, phe bán vẫn còn gây sức ép'}. "
      f"Sức mạnh giá tương đối RS Rating O'Neil (CANSLIM) đạt {rs_score}/99 "
      f'với Alpha 1 tháng {alpha_1m:+.1f}% và Alpha 3 tháng {alpha_3m:+.1f}% so với VN-Index.'
  )

  pe = fundamental_info.get('pe', 0.0) if fundamental_info else 0.0
  pb = fundamental_info.get('pb', 0.0) if fundamental_info else 0.0
  roe = fundamental_info.get('roe', 0.0) if fundamental_info else 0.0
  growth = fundamental_info.get('profitGrowth', 0.0) if fundamental_info else 0.0
  debt = fundamental_info.get('debtToEquity', 0.0) if fundamental_info else 0.0
  is_audited = fundamental_info.get('isAudited', False) if fundamental_info else False
  ocf = fundamental_info.get('ocf', 0.0) if fundamental_info else 0.0
  cfo_ttm = fundamental_info.get('cfoTtm') if fundamental_info else None
  borrow_de = fundamental_info.get('borrowDE') if fundamental_info else None
  cfo_eff = cfo_ttm if cfo_ttm is not None else ocf
  gross_margin = fundamental_info.get('grossMargin', 0.0) if fundamental_info else 0.0
  net_margin = fundamental_info.get('netMargin', 0.0) if fundamental_info else 0.0
  ocf_status = fundamental_info.get('ocfStatus', '') if fundamental_info else ''
  report_period = fundamental_info.get('reportPeriod', '') if fundamental_info else ''
  period_txt = f' (kỳ {report_period})' if report_period else ''
  is_fin_sector = sector in FINANCIAL_SECTORS

  pe_display = f'{pe:.1f}x' if pe > 0 else 'Dữ liệu chưa ghi nhận'
  pb_display = f'{pb:.1f}x' if pb > 0 else 'Dữ liệu chưa ghi nhận'
  roe_display = f'{roe:.1f}%' if roe != 0 else 'Dữ liệu chưa ghi nhận'
  growth_display = f'{growth:+.1f}%' if growth != 0 else 'Dữ liệu chưa ghi nhận'
  ocf_display = f'{ocf:+,.1f} tỷ đ' if ocf != 0 else 'Dữ liệu chưa ghi nhận'

  cfo_ttm_txt = f', CFO 4 quý {cfo_ttm:+,.1f} tỷ đ' if cfo_ttm is not None else ''
  ocf_text = f' Dòng tiền HĐKD quý gần nhất {ocf_display} ({ocf_status}){cfo_ttm_txt}, Biên lãi gộp {gross_margin:.1f}% và Biên lãi ròng {net_margin:.1f}%.' if ocf != 0 or gross_margin != 0 else ''
  debt_txt = (
      f'Nợ vay/VCSH {borrow_de:.2f}x (Nợ phải trả/VCSH {debt:.2f}x)' if borrow_de is not None
      else f'Nợ phải trả/VCSH {debt:.2f}x'
  )

  if roe != 0 and pe > 0:
    if roe >= 15.0 and growth > 0:
      growth_quality = (
          f'Theo BCTC công bố gần nhất{period_txt}, {ticker} ghi nhận tỷ suất sinh lời ROE {roe_display} '
          f'và tăng trưởng lợi nhuận {growth_display}. Định giá P/E hiện tại {pe_display} và P/B {pb_display}. '
          f'{debt_txt}.{ocf_text}'
      )
    elif growth < 0:
      growth_quality = (
          f'Theo BCTC công bố gần nhất{period_txt}, {ticker} ghi nhận ROE {roe_display}, tuy nhiên tăng trưởng lợi nhuận '
          f'suy giảm {growth_display}. Mặc dù P/E ở mức {pe_display} (P/B {pb_display}), '
          f'biên an toàn doanh nghiệp suy giảm và rủi ro điều chỉnh định giá vẫn hiện hữu nếu chu kỳ kinh doanh chưa tạo đáy.{ocf_text}'
      )
    else:
      growth_quality = (
          f'Theo BCTC công bố gần nhất{period_txt}, {ticker} duy trì ROE {roe_display} với P/E {pe_display} và P/B {pb_display}, '
          f'tăng trưởng lợi nhuận {growth_display}. Cần đối chiếu định giá với lịch sử của chính mã và nhóm cùng ngành '
          f'trước khi kết luận rẻ/đắt.{ocf_text}'
      )
  else:
    growth_quality = (
        f'Chỉ số định giá P/E ({pe_display}) và ROE ({roe_display}) chưa ghi nhận đầy đủ từ nguồn dữ liệu BCTC. '
        f'Doanh nghiệp đang giao dịch theo thanh khoản và dòng tiền thực tế trên sàn.{ocf_text}'
    )

  has_legal, has_dilution, legal_findings, dilution_findings, governance_summary = detect_governance_and_legal_risks(
      ticker, news_list, fundamental_info
  )

  support_level = technical_info.get('support', round(current_price * 0.96, -2))
  resistance_level = technical_info.get('resistance', round(current_price * 1.08, -2))
  stop_loss_price = technical_info.get('tPlus', {}).get('stop', '')
  if not stop_loss_price or stop_loss_price == '--':
    stop_loss_price = f'{round(support_level * 0.97, -2):,.0f} đ'
  target_price_str = technical_info.get('tPlus', {}).get('target', '')
  if not target_price_str or target_price_str == '--':
    target_price_str = f'{resistance_level:,.0f} đ'

  upside = technical_info.get('upside', 8.0)
  downside = technical_info.get('downside', 4.0)
  rr_ratio = technical_info.get('rrRatio', 2.0)
  ma20 = technical_info.get('ma20', current_price)
  atr14 = technical_info.get('atr14', round(current_price * 0.02, 1))

  pos_sizing = technical_info.get('positionSizing', {})
  max_nav = pos_sizing.get('maxNavPct', 25.0)
  pilot_nav = pos_sizing.get('pilotNavPct', 8.5)
  pyramid_nav = pos_sizing.get('pyramidNavPct', 16.5)

  mtf = technical_info.get('multiTimeframe', {})
  confluence_text = mtf.get('confluence', 'Theo dõi xu hướng')
  mtf_desc = mtf.get('description', '')

  bull_trigger = (
      f'Dòng tiền mua chủ động duy trì trên 55%, RS Rating duy trì kênh trên (>=65), '
      f'khối ngoại ngừng bán ròng và giá giữ vững hỗ trợ then chốt {support_level:,.0f} đ (nền MA20 {ma20:,.0f} đ).'
  )
  bull_target = f'{resistance_level:,.0f} đ (+{upside}%)'

  bear_risk = (
      'Áp lực bán ròng gia tăng, xuất hiện phiên phân phối thanh khoản đột biến, '
      f'hoặc giá đóng cửa xuyên thủng ngưỡng hỗ trợ {support_level:,.0f} đ.'
  )
  bear_support = f'{support_level:,.0f} đ (Cắt lỗ tại {stop_loss_price})'

  guardrails_triggered = []
  action_status = 'Theo dõi'
  status_color = 'slate'

  _, tail_lock_financial, distress_reasons = assess_financial_distress(fundamental_info, sector)
  tail_lock_risk = tail_lock_financial
  tail_lock_reasons = distress_reasons if tail_lock_financial else []

  if tail_lock_risk:
    guardrail_msg = (
        f"🚨 GUARDRAIL KẸT THANH KHOẢN: Phát hiện nguy cơ kẹt sàn nghiêm trọng ({'; '.join(tail_lock_reasons)}). "
        f'Kích hoạt ngắt mạch bảo vệ vốn: Tuyệt đối cấm mua mới. Ưu tiên hạ tỷ trọng khi còn thanh khoản.'
    )
    guardrails_triggered.append(guardrail_msg)
    action_status = 'Tạm ngừng giao dịch (Rủi ro kẹt thanh khoản)'
    status_color = 'rose'
    core_warning = (
        f"RỦI RO KẸT THANH KHOẢN CAO: {'; '.join(tail_lock_reasons)}. "
        f'Không mua mới. Nếu đang nắm giữ, ưu tiên hạ tỷ trọng khi cổ phiếu còn thanh khoản; '
        f'lưu ý lệnh bán có thể không khớp nếu cổ phiếu mất thanh khoản (kẹt sàn).'
    )
    if 'tPlus' in technical_info:
      technical_info['tPlus']['decision'] = 'TẠM NGỪNG MUA (RỦI RO KẸT THANH KHOẢN)'
      technical_info['tPlus']['type'] = 'danger'
      technical_info['tPlus']['reason'] = core_warning


  elif has_legal:
    guardrail_msg = (
        f"GUARDRAIL PHÁP LÝ (CHƯA XÁC MINH): Tin gắn mã có từ khóa pháp lý '{legal_findings[0]}' -> "
        f'Tạm ngừng mua mới cho đến khi đối chiếu nguyên văn công bố trên HOSE/HNX/UBCKNN.'
    )
    guardrails_triggered.append(guardrail_msg)
    action_status = 'Chờ xác minh pháp lý'
    status_color = 'rose'
    core_warning = (
        f"Phát hiện tin có từ khóa pháp lý: '{legal_findings[0]}'. Đây là dò từ khóa tự động trên tiêu đề, chưa xác minh mức độ. "
        f'Tạm ngừng mua mới; nếu đang nắm giữ, đọc nguyên văn công bố để đánh giá ảnh hưởng tới lợi nhuận/vốn trước khi quyết định, không bán vội theo tiêu đề.'
    )
    if 'tPlus' in technical_info:
      technical_info['tPlus']['decision'] = 'CHỜ XÁC MINH TIN PHÁP LÝ'
      technical_info['tPlus']['type'] = 'warning'
      technical_info['tPlus']['reason'] = core_warning

  elif has_dilution:
    guardrail_msg = (
        f"GUARDRAIL PHA LOÃNG (CHƯA XÁC MINH): Tin gắn mã có từ khóa phát hành/pha loãng '{dilution_findings[0]}' -> "
        "Buộc chuyển trạng thái sang 'Thận trọng / Hạn chế giao dịch' bất chấp tín hiệu kỹ thuật ngắn hạn."
    )
    guardrails_triggered.append(guardrail_msg)
    action_status = 'Thận trọng / Hạn chế giao dịch'
    status_color = 'rose'
    core_warning = (
        'Ưu tiên bảo toàn vốn; tạm ngừng mở vị thế mua mới cho đến khi kiểm tra giá phát hành, tỷ lệ pha loãng và đối tượng chào bán trong công bố chính thức.'
    )

  elif (fear_greed_score > 80 or (technical_info.get('rsi', 50) > 72 and fear_greed_score >= 70)) and foreign_net < -50000:
    guardrail_msg = (
        f'GUARDRAIL QUẢN TRỊ RỦI RO: Chỉ số tâm lý thị trường hưng phấn cực độ ({fear_greed_score}/100) kết hợp áp lực '
        f'khối ngoại bán ròng mạnh ({foreign_net:,.0f} cp) -> Buộc AI hạ tỷ trọng khuyến nghị mua mới, ưu tiên quản trị chốt lời bảo vệ thành quả.'
    )
    guardrails_triggered.append(guardrail_msg)
    action_status = 'Hạ tỷ trọng'
    status_color = 'amber'
    core_warning = (
        f'Cảnh giác bẫy tăng giá khi thị trường hưng phấn kết hợp khối ngoại bán ròng; chủ động hiện thực hóa lợi nhuận '
        f'từng phần khi giá tiệm cận vùng kháng cự {resistance_level:,.0f} đ.'
    )

  elif (not is_fin_sector) and cfo_eff < 0 and growth > 0 and ((borrow_de > 1.0) if borrow_de is not None else (debt > 1.8)):
    guardrail_msg = (
        f"GUARDRAIL CHẤT LƯỢNG LỢI NHUẬN: Dòng tiền HĐKD âm ({cfo_eff:+,.1f} tỷ đ{', 4 quý' if cfo_ttm is not None else ''}) dù LNST tăng trưởng, "
        f'kết hợp đòn bẩy cao ({debt_txt}) -> Tiềm ẩn rủi ro lợi nhuận giấy và căng thẳng dòng tiền lưu động.'
    )
    guardrails_triggered.append(guardrail_msg)
    action_status = 'Theo dõi'
    status_color = 'amber'
    core_warning = (
        f'Thận trọng với rủi ro dòng tiền HĐKD âm ({cfo_eff:+,.1f} tỷ đ); chỉ giao dịch ngắn hạn theo dòng tiền T+ '
        f'với tỷ trọng nhỏ tối đa {pilot_nav}% NAV, không giải ngân vốn lớn.'
    )

  else:
    ta_score = technical_info.get('taScore', 50)
    fa_score = fundamental_info.get('faScore', 0) if fundamental_info else 0
    rsi = technical_info.get('rsi', 50)

    if ta_score >= 75 and current_price >= ma20 and buy_ratio >= 55 and rs_score >= 60:
      action_status = 'Mở vị thế thăm dò'
      status_color = 'emerald'
      buy_zone_low = round(max(support_level, current_price - atr14 * 0.6), -2)
      buy_zone_high = round(min(current_price * 1.002, buy_zone_low + atr14 * 0.5), -2)
      core_warning = (
          f'Quản trị vị thế: Giải ngân thăm dò tối đa {pilot_nav}% NAV quanh vùng gom {buy_zone_low:,.0f} - {buy_zone_high:,.0f} đ '
          f'(tổng vị thế tối đa {max_nav}% NAV). {mtf_desc} Cắt lỗ tuyệt đối nếu thủng {support_level:,.0f} đ.'
      )
    elif current_price >= ma20 and 46 <= rsi <= 68:
      action_status = 'Tích lũy'
      status_color = 'blue'
      core_warning = (
          f'Theo dõi tính nhất quán của dòng tiền chủ động tại vùng hỗ trợ {support_level:,.0f} đ (RS {rs_score}/99). '
          f"Tỷ trọng đề xuất: Thăm dò {pilot_nav}% NAV, rủi ro mỗi lệnh <= {pos_sizing.get('riskBudgetPct', T_PLUS_RISK_BUDGET_PCT)}% NAV."
      )
    elif rsi > 70:
      action_status = 'Hạ tỷ trọng'
      status_color = 'amber'
      core_warning = (
          f'Cổ phiếu tiến sâu vào vùng quá mua RSI ({rsi:.1f}), rủi ro điều chỉnh T+ gia tăng; '
          f'hạn chế đua giá và canh chốt lời từng phần tại {resistance_level:,.0f} đ.'
      )
    elif current_price < ma20:
      action_status = 'Theo dõi'
      status_color = 'slate'
      core_warning = (
          f'Giá vẫn vận động dưới đường MA20 ({ma20:,.0f} đ) và {confluence_text}; '
          'kiên nhẫn đứng ngoài quan sát cho đến khi xuất hiện nến đảo chiều xác nhận dòng tiền lớn hấp thụ trở lại.'
      )
    else:
      action_status = 'Theo dõi'
      status_color = 'slate'
      core_warning = (
          f'Duy trì tỷ trọng an toàn và theo dõi phản ứng cung cầu của cổ phiếu quanh ngưỡng hỗ trợ {support_level:,.0f} đ.'
      )

  regime = technical_info.get('regime', {}) or {}
  dc_score, dc_deductions = compute_data_confidence(
      ssi_item, fundamental_info, technical_info, news_list, has_legal, regime
  )
  dc_rating = 'CAO' if dc_score >= 80 else ('KHÁ' if dc_score >= 65 else 'THẤP')

  regime_name = regime.get('regime', 'NEUTRAL')
  regime_summary = regime.get('summary', 'Regime chưa xác định')
  t_plus = technical_info.get('tPlus', {})
  mid_term = technical_info.get('midTerm', {})
  buy_statuses = {'Mở vị thế thăm dò', 'Tích lũy'}

  if action_status in buy_statuses and regime_name == 'NO_NEW_RISK':
    action_status = 'Theo dõi (Thị trường rủi ro cao)'
    status_color = 'slate'
    core_warning = f'{regime_summary}: không mở vị thế mới. {core_warning}'
  elif action_status in buy_statuses and regime_name == 'DEFENSIVE':
    action_status = 'Chờ (thị trường phòng thủ)'
    status_color = 'amber'
    core_warning = f'{regime_summary}: mặc định chờ, chỉ xét tỷ trọng nhỏ ở mã ngành dẫn dắt có xác nhận. {core_warning}'

  if dc_score < 80:
    dc_reason = f"Độ tin cậy dữ liệu {dc_score}/100 ({'; '.join(dc_deductions)})"
    gate_label = 'WAIT - DỮ LIỆU CHƯA ĐỦ TIN CẬY' if dc_score < 65 else 'WAIT - DC CHƯA ĐẠT 80'
    if action_status in buy_statuses:
      action_status = 'Chờ (dữ liệu chưa đủ tin cậy)'
      status_color = 'amber'
      core_warning = f'{dc_reason}: chưa đủ điều kiện mua mới. {core_warning}'
    if t_plus.get('type') == 'success':
      t_plus['decision'] = gate_label
      t_plus['type'] = 'warning'
      t_plus['reason'] = f"{dc_reason}. Setup kỹ thuật đạt nhưng cần bổ sung dữ liệu trước khi mua. {t_plus.get('reason', '')}"
      t_plus['isEligible'] = False
    if dc_score < 65 and mid_term.get('type') == 'success':
      mid_term['decision'] = gate_label
      mid_term['type'] = 'warning'
      mid_term['reason'] = f"{dc_reason}. {mid_term.get('reason', '')}"

  t_dec = technical_info.get('tPlus', {}).get('decision', 'Quan sát')
  t_ent = technical_info.get('tPlus', {}).get('entry', '--')
  t_stp = technical_info.get('tPlus', {}).get('stop', '--')
  t_tgt = technical_info.get('tPlus', {}).get('target', '--')
  t_rr = technical_info.get('tPlus', {}).get('rrRatio', 1.0)
  m_dec = technical_info.get('midTerm', {}).get('decision', 'Theo dõi')
  m_tgt = technical_info.get('midTerm', {}).get('target', '--')
  m_dca = technical_info.get('midTerm', {}).get('dcaZone', '--')

  h_info = technical_info.get('positionHolding', {})
  h_dec = h_info.get('decision', 'Theo dõi')
  h_stop = h_info.get('trailingStopDisplay', '--')
  h_pattern = h_info.get('candlePattern', 'Chưa có mẫu hình xấu')

  bottom_line = (
      f'• Lướt sóng T+ (Mua mới): {t_dec} (Vùng vào: {t_ent}, Mục tiêu: {t_tgt}, Cắt lỗ: {t_stp}, Net R:R 1:{t_rr}).\n'
      f'• Vị thế đang nắm giữ (Chốt sớm / Chặn lãi): {h_dec} (Chặn lãi Trailing Stop: {h_stop} | Tín hiệu nến: {h_pattern}).\n'
      f'• Đầu tư Trung/Dài hạn: {m_dec} (Định giá hợp lý: {m_tgt}, Vùng gom DCA: {m_dca}).\n'
      f'• Thị trường: {regime_summary}. Độ tin cậy dữ liệu {dc_score}/100.\n'
      'Thông tin tham khảo, không phải tư vấn đầu tư cá nhân; ngưỡng điểm là tham số tạm, chưa backtest.'
  )

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
- **Regime thị trường**: {regime_summary}
{chr(10).join(f"  - [{'x' if c['met'] else (' ' if c['met'] is False else '?')}] {c['name']}: {c['detail']}" for c in regime.get('conditions', []))}

## 4. MA TRẬN KỊCH BẢN KỲ VỌNG & QUẢN TRỊ RỦI RO
- **Kịch bản Khả quan (Bull Case)**:
  - Điều kiện kích hoạt: {bull_trigger}
  - Mục tiêu giá/Kháng cự kỳ vọng: {bull_target}
- **Kịch bản Thận trọng/Phòng thủ (Bear Case)**:
  - Yếu tố rủi ro kích hoạt: {bear_risk}
  - Vùng hỗ trợ/Cắt lỗ đề xuất: {bear_support}
- **Tỷ lệ Lợi nhuận/Rủi ro (R:R Ratio)**: 1:{rr_ratio}
- **Quản trị vị thế (Position Sizing)**: Tỷ trọng giải ngân tối đa {max_nav}% NAV (Thăm dò: {pilot_nav}% NAV, Gia tăng: {pyramid_nav}% NAV) • Rủi ro tối đa mỗi lệnh {pos_sizing.get('riskBudgetPct', T_PLUS_RISK_BUDGET_PCT)}% NAV.

## 5. KẾT LUẬN HÀNH ĐỘNG & VỊ THẾ NẮM GIỮ
- **Trạng thái Mua Mới**: [{action_status}]
- **Vị thế Đang Nắm Giữ**: [{h_dec}] (Chặn lãi Trailing Stop: {h_stop} | Mẫu hình nến: {h_pattern})
- **Xu hướng đa khung (Multi-Timeframe)**: {confluence_text}
- **Độ tin cậy dữ liệu**: {dc_score}/100 ({dc_rating}){(' — ' + '; '.join(dc_deductions)) if dc_deductions else ''}
- **Lưu ý cốt lõi**: {core_warning}

## 6. ĐÚC KẾT (BOTTOM LINE)
{bottom_line}
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
      'tailLockRisk': tail_lock_risk,
      'tailLockReasons': tail_lock_reasons,
      'dcScore': dc_score,
      'dcRating': dc_rating,
      'dcDeductions': dc_deductions,
      'regime': regime,
      'bottomLine': bottom_line,
      'rawMarkdown': markdown_report,
  }
