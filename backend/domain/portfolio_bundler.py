"""
Stock RT - Portfolio Bundling & Capital Allocation Engine
Tạo các gói đầu tư tối ưu theo quy mô vốn (15tr, 20tr, 25tr, 50tr...):
- Tuân thủ nghiêm ngặt Lô chẵn 100 cổ phiếu (HOSE/HNX)
- Phân bổ 2 mã thuộc 2 nhóm ngành độc lập (triệt tiêu rủi ro ngành)
- Điều tiết tỷ lệ tiền mặt dự phòng theo Market Regime (VN-Index)
- Cung cấp danh sách cổ phiếu tương đương để đổi mã linh hoạt
"""

import time
from concurrent.futures import ThreadPoolExecutor
from backend.data_providers.ssi_provider import get_ssi_board_data
from backend.data_providers.entrade_provider import fetch_chart_data
from backend.domain.regime import evaluate_market_regime
from backend.domain.technicals import analyze_technicals_and_scoring
from backend.constants.sectors import SECTOR_MAP

# Bảng tra cứu nhóm ngành cho các cổ phiếu thanh khoản hàng đầu TTCK Việt Nam
KNOWN_STOCK_SECTORS = {
    # Ngân hàng
    'VCB': 'Ngân hàng', 'BID': 'Ngân hàng', 'CTG': 'Ngân hàng', 'TCB': 'Ngân hàng',
    'MBB': 'Ngân hàng', 'ACB': 'Ngân hàng', 'VPB': 'Ngân hàng', 'HDB': 'Ngân hàng',
    'STB': 'Ngân hàng', 'SHB': 'Ngân hàng', 'TPB': 'Ngân hàng', 'LPB': 'Ngân hàng',
    'MSB': 'Ngân hàng', 'VIB': 'Ngân hàng', 'EIB': 'Ngân hàng', 'OCB': 'Ngân hàng',
    'SSB': 'Ngân hàng', 'NAB': 'Ngân hàng', 'BVB': 'Ngân hàng',
    # Chứng khoán / Dịch vụ tài chính
    'SSI': 'Chứng khoán', 'VND': 'Chứng khoán', 'VIX': 'Chứng khoán', 'HCM': 'Chứng khoán',
    'VCI': 'Chứng khoán', 'SHS': 'Chứng khoán', 'MBS': 'Chứng khoán', 'BSI': 'Chứng khoán',
    'FTS': 'Chứng khoán', 'CTS': 'Chứng khoán', 'ORS': 'Chứng khoán', 'AGR': 'Chứng khoán',
    # Thép & Tài nguyên cơ bản
    'HPG': 'Thép & VLXD', 'HSG': 'Thép & VLXD', 'NKG': 'Thép & VLXD', 'VGS': 'Thép & VLXD',
    'TLH': 'Thép & VLXD', 'SMC': 'Thép & VLXD',
    # Bất động sản dân dụng & KCN
    'VHM': 'Bất động sản', 'VIC': 'Bất động sản', 'VRE': 'Bất động sản', 'KDH': 'Bất động sản',
    'NLG': 'Bất động sản', 'PDR': 'Bất động sản', 'DIG': 'Bất động sản', 'DXG': 'Bất động sản',
    'KBC': 'BĐS Khu công nghiệp', 'IDC': 'BĐS Khu công nghiệp', 'SZC': 'BĐS Khu công nghiệp',
    'BCM': 'BĐS Khu công nghiệp', 'VGC': 'BĐS Khu công nghiệp', 'NVL': 'Bất động sản',
    'CEO': 'Bất động sản', 'TCH': 'Bất động sản', 'HQC': 'Bất động sản', 'DPG': 'Bất động sản & Hạ tầng',
    # Bán lẻ & Tiêu dùng
    'MWG': 'Bán lẻ tiêu dùng', 'MSN': 'Bán lẻ & Tiêu dùng', 'PNJ': 'Bán lẻ trang sức',
    'DGW': 'Phân phối ICT', 'FRT': 'Bán lẻ ICT & Dược', 'VNM': 'Thực phẩm & Đồ uống',
    'SAB': 'Thực phẩm & Đồ uống', 'KDC': 'Thực phẩm & Đồ uống', 'MCH': 'Hàng tiêu dùng',
    # Công nghệ thông tin
    'FPT': 'Công nghệ thông tin', 'CMG': 'Công nghệ thông tin', 'ELC': 'Công nghệ thông tin',
    # Dầu khí & Năng lượng
    'GAS': 'Dầu khí', 'PVD': 'Dầu khí', 'PVS': 'Dầu khí', 'BSR': 'Dầu khí & Lọc hóa dầu',
    'PLX': 'Dầu khí', 'POW': 'Năng lượng điện', 'PC1': 'Năng lượng & Xây lắp', 'REE': 'Năng lượng & Cơ điện',
    'GELEX': 'Thiết bị điện & Hạ tầng', 'GEX': 'Thiết bị điện & Hạ tầng',
    # Hóa chất & Phân bón
    'DGC': 'Hóa chất cơ bản', 'DCM': 'Phân bón & Hóa chất', 'DPM': 'Phân bón & Hóa chất', 'CSV': 'Hóa chất cơ bản',
    # Vận tải & Logistics
    'HAH': 'Cảng biển & Vận tải biển', 'GMD': 'Cảng biển & Logistics', 'VSC': 'Cảng biển & Container',
    'PVT': 'Vận tải dầu khí', 'VOS': 'Vận tải biển',
    # Xây dựng & Hạ tầng
    'VCG': 'Xây dựng & Hạ tầng', 'HHV': 'Hạ tầng giao thông', 'FCN': 'Nền móng & Công trình ngầm',
    'CII': 'Hạ tầng cầu đường', 'CTD': 'Xây dựng dân dụng', 'HBC': 'Xây dựng dân dụng',
    # Thủy sản & Nông nghiệp
    'VHC': 'Thủy sản', 'ANV': 'Thủy sản', 'DBC': 'Chăn nuôi & Nông nghiệp', 'BAF': 'Chăn nuôi heo',
    'PAN': 'Nông nghiệp & Thực phẩm', 'HAG': 'Nông nghiệp & Trái cây',
}

# Nhóm ngành phân loại vai trò
CORE_SECTORS = {'Ngân hàng', 'Thép & VLXD', 'Bán lẻ tiêu dùng', 'Thực phẩm & Đồ uống', 'Công nghệ thông tin'}
MOMENTUM_SECTORS = {
    'Chứng khoán', 'Bất động sản', 'BĐS Khu công nghiệp', 'Dầu khí', 'Dầu khí & Lọc hóa dầu',
    'Phân bón & Hóa chất', 'Hóa chất cơ bản', 'Cảng biển & Logistics', 'Xây dựng & Hạ tầng',
    'Thiết bị điện & Hạ tầng', 'Năng lượng điện'
}

# Danh mục các nhóm ngành chuẩn hóa để người dùng tùy biến khẩu vị
MAJOR_SECTOR_GROUPS = [
    'Ngân hàng',
    'Chứng khoán',
    'Thép & VLXD',
    'Bất động sản',
    'BĐS Khu công nghiệp',
    'Bán lẻ & Tiêu dùng',
    'Công nghệ thông tin',
    'Dầu khí & Năng lượng',
    'Hóa chất & Phân bón',
    'Cảng biển & Logistics',
    'Xây dựng & Hạ tầng',
    'Thủy sản & Nông nghiệp',
]


def match_sector_group(stock_sector, target_group):
  """Kiểm tra một ngành cổ phiếu có khớp với nhóm ngành được chọn hay không."""
  if not target_group or target_group == 'Tất cả':
    return True
  s = (stock_sector or '').lower()
  tg = target_group.lower()

  if tg == 'ngân hàng':
    return 'ngân hàng' in s
  if tg == 'chứng khoán':
    return 'chứng khoán' in s or 'tài chính' in s
  if 'thép' in tg or 'vlxd' in tg:
    return 'thép' in s or 'kim khí' in s or 'vật liệu' in s
  if tg == 'bđs khu công nghiệp' or 'khu công nghiệp' in tg:
    return 'khu công nghiệp' in s or 'kcn' in s
  if tg == 'bất động sản':
    return ('bất động sản' in s or 'địa ốc' in s or 'nhà ở' in s) and 'khu công nghiệp' not in s
  if 'bán lẻ' in tg or 'tiêu dùng' in tg:
    return any(k in s for k in ['bán lẻ', 'tiêu dùng', 'phân phối ict', 'thực phẩm', 'đồ uống', 'sữa', 'trang sức', 'dược'])
  if 'công nghệ' in tg:
    return 'công nghệ' in s or 'tin học' in s or 'viễn thông' in s
  if 'dầu khí' in tg or 'năng lượng' in tg:
    return any(k in s for k in ['dầu khí', 'xăng dầu', 'năng lượng', 'điện', 'lọc hóa dầu', 'thiết bị điện'])
  if 'hóa chất' in tg or 'phân bón' in tg:
    return 'hóa chất' in s or 'phân bón' in s
  if 'cảng' in tg or 'logistics' in tg or 'vận tải' in tg:
    return 'cảng' in s or 'logistics' in s or 'vận tải' in s or 'container' in s
  if 'xây dựng' in tg or 'hạ tầng' in tg:
    return 'xây dựng' in s or 'hạ tầng' in s or 'cầu đường' in s or 'công trình' in s
  if 'thủy sản' in tg or 'nông nghiệp' in tg:
    return 'thủy sản' in s or 'nông nghiệp' in s or 'chăn nuôi' in s or 'trái cây' in s

  return tg in s


def get_stock_sector(symbol, company_name=''):
  """Xác định nhóm ngành của cổ phiếu từ từ điển hoặc tên công ty."""
  sym = symbol.strip().upper()
  if sym in KNOWN_STOCK_SECTORS:
    return KNOWN_STOCK_SECTORS[sym]
  
  name = (company_name or '').lower()
  if 'ngân hàng' in name:
    return 'Ngân hàng'
  if 'chứng khoán' in name:
    return 'Chứng khoán'
  if 'thép' in name or 'kim khí' in name:
    return 'Thép & VLXD'
  if 'bất động sản' in name or 'địa ốc' in name or 'nhà ở' in name:
    return 'Bất động sản'
  if 'dầu khí' in name or 'xăng dầu' in name:
    return 'Dầu khí'
  if 'hóa chất' in name or 'phân bón' in name:
    return 'Phân bón & Hóa chất'
  if 'xây dựng' in name or 'xây lắp' in name:
    return 'Xây dựng & Hạ tầng'
  if 'cảng' in name or 'vận tải' in name or 'logistics' in name:
    return 'Cảng biển & Logistics'
  if 'thực phẩm' in name or 'sữa' in name or 'đồ uống' in name:
    return 'Thực phẩm & Đồ uống'
  if 'công nghệ' in name or 'tin học' in name:
    return 'Công nghệ thông tin'
  return 'Thị trường chung'


def _build_stock_summary(item):
  """Rút trích các trường cần thiết từ SSI item và tính điểm nhanh."""
  sym = item.get('stockSymbol', '').upper()
  name = item.get('companyNameVi', item.get('clientName', f'Cổ phiếu {sym}'))
  price = item.get('matchedPrice') or item.get('refPrice', 0)
  ref_price = item.get('refPrice', price)
  change = item.get('priceChange', price - ref_price)
  pct_change = item.get('priceChangePercent', round((change / ref_price * 100), 2) if ref_price else 0)
  traded_val = item.get('nmTotalTradedValue', 0)
  traded_vol = item.get('stockVol', 0)
  foreign_net = item.get('buyForeignQtty', 0) - item.get('sellForeignQtty', 0)
  exchange = item.get('exchange', 'HOSE').upper()
  sector = get_stock_sector(sym, name)

  # Chấm điểm xung lực nhanh (Fast Score: 0 - 100)
  score = 50
  if pct_change > 2.0:
    score += 18
  elif pct_change > 0.5:
    score += 10
  elif pct_change < -2.0:
    score -= 15

  if foreign_net > 50000:
    score += 10
  elif foreign_net < -200000:
    score -= 8

  if traded_val > 100_000_000_000:  # > 100 tỷ
    score += 15
  elif traded_val > 30_000_000_000:  # > 30 tỷ
    score += 8

  score = max(20, min(95, score))

  return {
      'symbol': sym,
      'name': name,
      'price': price,
      'refPrice': ref_price,
      'change': change,
      'percentChange': pct_change,
      'tradedValue': traded_val,
      'tradedVolume': traded_vol,
      'foreignNet': foreign_net,
      'exchange': exchange,
      'sector': sector,
      'fastScore': score,
  }


def _enrich_stock_technicals(stock_summary, ssi_board, regime):
  """Làm giàu thông tin kỹ thuật chuyên sâu (S1, R1, R2, ATR, khoảng cách nền) cho cổ phiếu được chọn."""
  sym = stock_summary['symbol']
  item = ssi_board.get(sym, {})
  p = stock_summary['price']
  exchange = stock_summary.get('exchange', 'HOSE')
  try:
    chart = fetch_chart_data(sym, days=120, resolution='1D', ssi_item=item)
    tech = analyze_technicals_and_scoring(chart, item, p, {}, ticker=sym, exchange=exchange, regime=regime)
    atr = tech.get('atr14', round(p * 0.02, 1))
    s1 = tech.get('support', round(p - 1.5 * atr, -2))
    r1 = tech.get('resistance', round(p + 2.0 * atr, -2))
    r2 = tech.get('resistance2', round(p + 3.5 * atr, -2))
    dist_s1 = round(((p - s1) / s1) * 100.0, 1) if s1 > 0 else 0.0
    is_extended = dist_s1 > 4.0

    if is_extended:
      pb_min = round(max(s1, p - 0.5 * (p - s1)), -2)
      pb_max = round(max(s1, p - 0.25 * (p - s1)), -2)
      buy_zone = f'{pb_min:,.0f} - {pb_max:,.0f} đ (Vùng Pullback)'
      action = '⏳ CHỜ RETEST / KHÔNG MUA ĐUỔI'
      action_color = 'amber'
      advice = f'Giá đã tăng cách nền {dist_s1}%, không mua đuổi đỉnh ngắn hạn. Đặt lệnh chờ tại vùng Pullback.'
    else:
      entry_max = round(min(s1 + 0.4 * atr, p * 1.005), -2)
      buy_zone = f'{s1:,.0f} - {entry_max:,.0f} đ'
      action = 'VÙNG GOM AN TOÀN'
      action_color = 'emerald'
      advice = f'Giá đang nằm trong vùng nền tích lũy an toàn (cách nền {dist_s1}%).'

    stop_loss = round(min(s1 - 0.5 * atr, p - 1.5 * atr), -2)
    target1 = r1
    target2 = r2
    downside = max(1.0, p - stop_loss)
    upside = max(0.1, target1 - p)
    rr_ratio = round(upside / downside, 1)

    return {
        **stock_summary,
        'support': s1,
        'resistance': r1,
        'resistance2': r2,
        'atr': atr,
        'distToS1': dist_s1,
        'isExtended': is_extended,
        'buyZone': buy_zone,
        'action': action,
        'actionColor': action_color,
        'advice': advice,
        'stopLoss': stop_loss,
        'stopLossPct': round(((stop_loss - p) / p) * 100.0, 1),
        'target1': target1,
        'target1Pct': round(((target1 - p) / p) * 100.0, 1),
        'target2': target2,
        'target2Pct': round(((target2 - p) / p) * 100.0, 1),
        'riskReward': rr_ratio,
    }
  except Exception as e:
    max_band = 0.07 if exchange == 'HOSE' else (0.10 if exchange == 'HNX' else 0.15)
    stop_loss = round(p * (1 - max_band * 0.65), -2)
    target1 = round(p * (1 + max_band * 0.95), -2)
    target2 = round(p * (1 + max_band * 1.8), -2)
    sl_pct = round(((stop_loss - p) / p) * 100.0, 1)
    t1_pct = round(((target1 - p) / p) * 100.0, 1)
    t2_pct = round(((target2 - p) / p) * 100.0, 1)
    rr = round(abs(target1 - p) / max(1.0, abs(p - stop_loss)), 1)
    bz_min = round(p * (1 - max_band * 0.2), -2)
    bz_max = round(p * (1 + max_band * 0.1), -2)
    return {
        **stock_summary,
        'distToS1': 0.0,
        'isExtended': False,
        'buyZone': f'{bz_min:,.0f} - {bz_max:,.0f} đ',
        'action': 'VÙNG GOM AN TOÀN' if stock_summary.get('percentChange', 0) <= 1.5 else 'CANH RUNG LẮC MUA',
        'actionColor': 'emerald' if stock_summary.get('percentChange', 0) <= 1.5 else 'blue',
        'advice': 'Giải ngân theo vùng gom khuyến nghị.',
        'stopLoss': stop_loss,
        'stopLossPct': sl_pct,
        'target1': target1,
        'target1Pct': t1_pct,
        'target2': target2,
        'target2Pct': t2_pct,
        'riskReward': rr,
    }


def generate_portfolio_bundle(capital=20_000_000, style='balanced'):
  """
  Động cơ sinh Gói danh mục tối ưu theo số vốn:
  - capital: Số vốn đầu tư (VND), mặc định 20.000.000 đ
  - style: 'balanced' (Cân bằng), 'momentum' (Đột phá T+), 'defensive' (An toàn/Tích sản)
  """
  try:
    capital = float(capital)
    if capital < 5_000_000:
      capital = 5_000_000
    elif capital > 500_000_000:
      capital = 500_000_000
  except (ValueError, TypeError):
    capital = 20_000_000

  ssi_board = get_ssi_board_data()
  regime = evaluate_market_regime(ssi_board)
  regime_label = regime.get('regime', 'Neutral')
  regime_score = regime.get('score', 3)
  regime_advice = regime.get('recommendation', 'Thị trường thận trọng')

  # 1. Tỷ lệ giải ngân theo Market Regime
  if 'Risk-on' in regime_label:
    alloc_rate = 0.88  # Giải ngân 88%, dự phòng 12%
  elif 'Defensive' in regime_label or 'No-new' in regime_label:
    alloc_rate = 0.55  # Giải ngân 55%, giữ 45% tiền mặt phòng thủ
  else:
    alloc_rate = 0.75  # Trung tính: Giải ngân 75%, giữ 25% tiền mặt

  total_budget = capital * alloc_rate
  slot_budget = total_budget / 2.0

  # 2. Lọc danh sách ứng viên từ SSI board (Thanh khoản > 15 tỷ, thị giá >= 10k)
  valid_stocks = []
  for sym, item in ssi_board.items():
    if item.get('stockType') != 's' or len(sym) != 3:
      continue
    price = item.get('matchedPrice') or item.get('refPrice', 0)
    traded_val = item.get('nmTotalTradedValue', 0)
    # Lọc cổ phiếu có thanh khoản thực tế và giá hợp lệ
    if price >= 10_000 and traded_val >= 15_000_000_000:
      summary = _build_stock_summary(item)
      valid_stocks.append(summary)

  # Sắp xếp theo giá trị giao dịch và xung lực
  valid_stocks.sort(key=lambda s: -(s['tradedValue'] * 0.6 + s['fastScore'] * 1e9 * 0.4))

  # 3. Phân tách ứng viên theo vai trò & Khả năng mua tối thiểu 1 lô 100
  # Điều kiện mua được ít nhất 100 CP: price * 100 <= slot_budget
  eligible_stocks = [s for s in valid_stocks if (s['price'] * 100) <= slot_budget]

  if not eligible_stocks:
    # Nếu vốn quá nhỏ không đủ mua 2 mã, lấy các mã giá thấp nhất trong top thanh khoản
    eligible_stocks = sorted(valid_stocks, key=lambda s: s['price'])[:10]

  core_candidates = [
      s for s in eligible_stocks
      if s['sector'] in CORE_SECTORS or any(k in s['name'].lower() for k in ['ngân hàng', 'hòa phát', 'fpt', 'vinamilk'])
  ]
  momentum_candidates = [
      s for s in eligible_stocks
      if s['sector'] in MOMENTUM_SECTORS or s['percentChange'] > 0
  ]

  if not core_candidates:
    core_candidates = eligible_stocks[:5]
  if not momentum_candidates:
    momentum_candidates = eligible_stocks[5:10] if len(eligible_stocks) > 5 else eligible_stocks

  # 4. Chọn cặp đôi tối ưu theo Style & Quy tắc Khác Ngành (Sector Diversification)
  stock1 = None
  stock2 = None

  if style == 'defensive':
    core_candidates.sort(key=lambda s: -s['tradedValue'])
    stock1 = core_candidates[0] if core_candidates else eligible_stocks[0]
    # Tìm mã thứ 2 khác ngành
    for s in core_candidates[1:]:
      if s['sector'] != stock1['sector']:
        stock2 = s
        break
  elif style == 'momentum':
    momentum_candidates.sort(key=lambda s: -s['percentChange'])
    stock1 = momentum_candidates[0] if momentum_candidates else eligible_stocks[0]
    for s in momentum_candidates[1:]:
      if s['sector'] != stock1['sector']:
        stock2 = s
        break
  else:  # 'balanced' (Khuyên dùng: 1 Core + 1 Momentum)
    # Ưu tiên các mã chưa tăng quá nóng (percentChange <= 2.5%) để đảm bảo sát nền hỗ trợ an toàn
    safe_core = [s for s in core_candidates if s.get('percentChange', 0) <= 2.5]
    stock1 = safe_core[0] if safe_core else (core_candidates[0] if core_candidates else eligible_stocks[0])
    
    # Ưu tiên mã Momentum khác ngành với stock1
    safe_momentum = [s for s in momentum_candidates if s.get('percentChange', 0) <= 3.0]
    for s in (safe_momentum or momentum_candidates):
      if s['symbol'] != stock1['symbol'] and s['sector'] != stock1['sector']:
        stock2 = s
        break

  # Dự phòng nếu chưa tìm được mã thứ 2
  if not stock2:
    for s in eligible_stocks:
      if s['symbol'] != stock1['symbol']:
        stock2 = s
        break

  # Dự phòng cuối cùng nếu chỉ có 1 mã hợp lệ
  if not stock2:
    stock2 = stock1

  # 5. Phân tích nến song song cho đúng 2 mã được chọn (Zero-lag, chỉ tốn ~200-300ms)
  try:
    with ThreadPoolExecutor(max_workers=2) as pool:
      enriched_list = list(pool.map(
          lambda s: _enrich_stock_technicals(s, ssi_board, regime),
          [stock1, stock2]
      ))
    stock1_ready, stock2_ready = enriched_list[0], enriched_list[1]
  except Exception as e:
    stock1_ready, stock2_ready = stock1, stock2

  # 6. Tính toán Sizing & Làm tròn Lô chẵn 100
  def _calculate_slot_position(stock_info, budget, role_title):
    p = stock_info['price']
    lot_100_cost = p * 100
    if lot_100_cost > 0:
      raw_lots = int(budget // lot_100_cost)
      qty = max(100, raw_lots * 100)
    else:
      qty = 100
    
    total_cost = qty * p

    exch = stock_info.get('exchange', 'HOSE')
    band = 0.07 if exch == 'HOSE' else (0.10 if exch == 'HNX' else 0.15)
    default_sl = round(p * (1 - band * 0.65), -2)
    default_tg1 = round(p * (1 + band * 0.95), -2)
    default_tg2 = round(p * (1 + band * 1.8), -2)
    sl = stock_info.get('stopLoss', default_sl)
    tg1 = stock_info.get('target1', default_tg1)
    tg2 = stock_info.get('target2', default_tg2)
    sl_pct = stock_info.get('stopLossPct', round(((sl - p) / p) * 100.0, 1))
    tg1_pct = stock_info.get('target1Pct', round(((tg1 - p) / p) * 100.0, 1))
    tg2_pct = stock_info.get('target2Pct', round(((tg2 - p) / p) * 100.0, 1))
    rr = stock_info.get('riskReward', round(abs(tg1 - p) / max(1.0, abs(p - sl)), 1))

    bz_min = round(p * (1 - band * 0.2), -2)
    bz_max = round(p * (1 + band * 0.1), -2)

    return {
        'symbol': stock_info['symbol'],
        'name': stock_info['name'],
        'exchange': stock_info['exchange'],
        'sector': stock_info['sector'],
        'price': p,
        'change': stock_info['change'],
        'percentChange': stock_info['percentChange'],
        'fastScore': stock_info['fastScore'],
        'role': role_title,
        'quantity': qty,
        'totalCost': total_cost,
        'costPercent': round((total_cost / capital) * 100, 1),
        'buyZone': stock_info.get('buyZone', f'{bz_min:,.0f} - {bz_max:,.0f} đ'),
        'stopLoss': sl,
        'stopLossPct': sl_pct,
        'target1': tg1,
        'target1Pct': tg1_pct,
        'target2': tg2,
        'target2Pct': tg2_pct,
        'riskReward': rr,
        'action': stock_info.get('action', 'VÙNG GOM AN TOÀN'),
        'actionColor': stock_info.get('actionColor', 'emerald'),
        'advice': stock_info.get('advice', ''),
        'distToS1': stock_info.get('distToS1', 0.0),
        'isExtended': stock_info.get('isExtended', False),
    }

  slot1 = _calculate_slot_position(stock1_ready, slot_budget, 'Trụ Cân Bằng / Nền Tảng')
  slot2 = _calculate_slot_position(stock2_ready, slot_budget, 'Động Lực Tăng Trưởng / T+')

  total_invested = slot1['totalCost'] + slot2['totalCost']
  # Nếu tổng vượt quá vốn người dùng, tự động giảm bớt 100 CP ở mã có tỷ trọng cao hơn
  while total_invested > capital and (slot1['quantity'] > 100 or slot2['quantity'] > 100):
    if slot1['totalCost'] >= slot2['totalCost'] and slot1['quantity'] > 100:
      slot1['quantity'] -= 100
      slot1['totalCost'] = slot1['quantity'] * slot1['price']
      slot1['costPercent'] = round((slot1['totalCost'] / capital) * 100, 1)
    elif slot2['quantity'] > 100:
      slot2['quantity'] -= 100
      slot2['totalCost'] = slot2['quantity'] * slot2['price']
      slot2['costPercent'] = round((slot2['totalCost'] / capital) * 100, 1)
    total_invested = slot1['totalCost'] + slot2['totalCost']

  cash_reserve = max(0, capital - total_invested)
  cash_reserve_pct = round((cash_reserve / capital) * 100, 1)

  return {
      'capital': capital,
      'style': style,
      'regime': {
          'label': regime_label,
          'score': regime_score,
          'allocationRate': int(alloc_rate * 100),
          'advice': regime_advice,
      },
      'allocation': {
          'totalInvested': total_invested,
          'totalInvestedPct': round((total_invested / capital) * 100, 1),
          'cashReserve': cash_reserve,
          'cashReservePct': cash_reserve_pct,
      },
      'slots': [slot1, slot2],
      'generatedAt': time.strftime('%H:%M:%S %d/%m/%Y'),
  }


def get_alternative_candidates(current_symbol, sector, max_budget=10_000_000, exclude_sector=None, target_sector=None):
  """
  Lấy danh sách cổ phiếu tương đương theo ngành hoặc toàn sàn:
  - target_sector: Nhóm ngành người dùng muốn lọc (None hoặc 'Tất cả' để lấy tự do)
  - max_budget: Ngân sách tối đa của slot
  - exclude_sector: Ngành của slot còn lại (để cảnh báo/lọc chống trùng ngành)
  """
  current_sym = (current_symbol or '').strip().upper()
  ssi_board = get_ssi_board_data()
  alternatives = []

  is_filtered_by_target = bool(target_sector and target_sector != 'Tất cả')

  for sym, item in ssi_board.items():
    if sym == current_sym or item.get('stockType') != 's' or len(sym) != 3:
      continue
    price = item.get('matchedPrice') or item.get('refPrice', 0)
    traded_val = item.get('nmTotalTradedValue', 0)
    
    # Điều kiện: Thanh khoản > 3 tỷ và mua được tối thiểu 1 lô 100
    if price < 10_000 or (price * 100) > max_budget or traded_val < 3_000_000_000:
      continue

    sym_sector = get_stock_sector(sym, item.get('companyNameVi', ''))

    # Nếu người dùng chọn lọc theo ngành cụ thể:
    if is_filtered_by_target:
      if not match_sector_group(sym_sector, target_sector):
        continue
    else:
      # Không chọn ngành cụ thể: loại trừ ngành của slot còn lại nếu có
      if exclude_sector and match_sector_group(sym_sector, exclude_sector):
        continue

    is_same_sector = match_sector_group(sym_sector, sector)
    summary = _build_stock_summary(item)
    summary['isSameSector'] = is_same_sector
    summary['isConflictWithOtherSlot'] = bool(exclude_sector and match_sector_group(sym_sector, exclude_sector))

    # Tính thử số lượng cổ phiếu tròn lô 100
    lots = int(max_budget // (price * 100))
    qty = max(100, lots * 100)
    summary['suggestedQty'] = qty
    summary['totalCost'] = qty * price
    # Ước tính mức cắt lỗ / chốt lời dựa theo biên độ sàn và giá thực tế
    exch = summary.get('exchange', 'HOSE')
    band = 0.07 if exch == 'HOSE' else (0.10 if exch == 'HNX' else 0.15)
    sl = round(price * (1 - band * 0.65), -2)
    tg1 = round(price * (1 + band * 0.95), -2)
    summary['stopLoss'] = sl
    summary['target1'] = tg1
    summary['stopLossPct'] = round(((sl - price) / price) * 100.0, 1)
    summary['target1Pct'] = round(((tg1 - price) / price) * 100.0, 1)

    alternatives.append(summary)

  # Sắp xếp
  if is_filtered_by_target:
    # Sắp xếp theo thanh khoản & điểm xung lực trong ngành được chọn
    alternatives.sort(key=lambda s: -(s['tradedValue'] * 0.6 + s['fastScore'] * 1e9 * 0.4))
  else:
    # Ưu tiên mã cùng ngành trước, sau đó sắp xếp theo giá trị giao dịch & điểm số
    alternatives.sort(key=lambda s: (not s['isSameSector'], -(s['tradedValue'] * 0.6 + s['fastScore'] * 1e9 * 0.4)))

  return {'alternatives': alternatives[:12], 'targetSector': target_sector or 'Tất cả'}


def get_available_sectors_for_budget(slot_budget=10_000_000, exclude_sector=None):
  """
  Thống kê tất cả các nhóm ngành trên sàn và khả năng mua lô 100 theo ngân sách:
  - Trả về danh sách nhóm ngành kèm số lượng mã hợp lệ, giá tối thiểu để mua 1 lô 100
  """
  ssi_board = get_ssi_board_data()
  results = []
  total_all_eligible = 0

  for sec_name in MAJOR_SECTOR_GROUPS:
    candidates = []
    min_price = float('inf')

    for sym, item in ssi_board.items():
      if item.get('stockType') != 's' or len(sym) != 3:
        continue
      price = item.get('matchedPrice') or item.get('refPrice', 0)
      traded_val = item.get('nmTotalTradedValue', 0)
      if price < 10_000 or traded_val < 3_000_000_000:
        continue

      sym_sector = get_stock_sector(sym, item.get('companyNameVi', ''))
      if match_sector_group(sym_sector, sec_name):
        min_price = min(min_price, price)
        if (price * 100) <= slot_budget:
          candidates.append((sym, price, traded_val))

    candidates.sort(key=lambda x: -x[2])
    eligible_count = len(candidates)
    total_all_eligible += eligible_count

    is_excluded = bool(exclude_sector and match_sector_group(exclude_sector, sec_name))
    min_lot_cost = (min_price * 100) if min_price != float('inf') else 0

    results.append({
        'name': sec_name,
        'eligibleCount': eligible_count,
        'minLotCost': min_lot_cost,
        'isAvailable': eligible_count > 0,
        'isExcluded': is_excluded,
        'sampleSymbols': [c[0] for c in candidates[:3]],
    })

  # Thêm tab 'Tất cả' ở đầu
  all_item = {
      'name': 'Tất cả',
      'eligibleCount': total_all_eligible,
      'minLotCost': 1_000_000,
      'isAvailable': True,
      'isExcluded': False,
      'sampleSymbols': [],
  }

  return {
      'sectors': [all_item] + results,
      'budget': slot_budget,
      'excludeSector': exclude_sector or '',
  }
