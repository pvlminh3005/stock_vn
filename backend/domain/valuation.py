"""
Stock RT - Valuation & Fundamental Analysis Domain Engine
Định giá trung dài hạn theo dải Multiple lịch sử 12 quý, chấm điểm FA và kiểm soát căng thẳng tài chính.
"""
import io
import sys
import pandas as pd
from vnstock import Company, Finance

from backend.constants.colors import (
    DECISION_TYPE_DANGER,
    DECISION_TYPE_SUCCESS,
    DECISION_TYPE_WARNING,
    STATUS_COLOR_PERFECT,
    STATUS_COLOR_MOMENTUM,
    STATUS_COLOR_NEUTRAL,
    STATUS_COLOR_RISK,
)
from backend.constants.config import (
    VALUATION_MIN_QUARTERS,
    VALUATION_WINDOW_QUARTERS,
)
from backend.constants.sectors import (
    CYCLICAL_SECTORS,
    FINANCIAL_SECTORS,
    PB_PRIMARY_SECTORS,
    SECTOR_MAP,
)
from backend.db.database import get_cached_fundamental, save_cached_fundamental
from backend.data_providers.vci_provider import (
    _latest,
    get_vci_financial_history,
    summarize_vci_history,
)
from backend.utils.network import vnstock_call
from backend.utils.numbers import percentile, safe_num
from backend.utils.ohlc_helpers import parse_quarter_key

def classify_ocf_status(sector, ocf, profit_growth):
  """Đánh giá chất lượng dòng tiền HĐKD (Quality of Earnings)."""
  if sector in FINANCIAL_SECTORS:
    return "Không áp dụng cho ngành tài chính"
  if ocf > 0:
    return "Dương (tiền thật về doanh nghiệp)"
  if ocf < 0 and profit_growth > 0:
    return "⚠️ Cảnh báo Lợi nhuận giấy (OCF âm / Lãi ảo)"
  if ocf < 0:
    return "Âm (Thâm hụt dòng tiền lưu động)"
  return "Dữ liệu chưa ghi nhận"

def fetch_from_vnstock(symbol):
  """Lấy dữ liệu BCTC và hồ sơ doanh nghiệp thực tế qua vnstock."""
  old_stdout, old_stderr = sys.stdout, sys.stderr
  sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
  try:
    # 1. Thông tin doanh nghiệp từ VCI
    ov = vnstock_call(lambda: Company(symbol=symbol, source='VCI').overview())
    if ov is None:
      ov = pd.DataFrame()
    name = (
        ov['organ_name'].values[0]
        if 'organ_name' in ov.columns and len(ov) > 0
        else f'Công ty Cổ phần {symbol}'
    )
    raw_sector = (
        ov['sector'].values[0]
        if 'sector' in ov.columns and len(ov) > 0
        else 'Doanh nghiệp'
    )
    sector = SECTOR_MAP.get(raw_sector, raw_sector)
    summary = (
        ov['company_profile'].values[0]
        if 'company_profile' in ov.columns and len(ov) > 0
        else ''
    )

    # 2. Chỉ số tài chính BCTC từ KBS (tham khảo & dự phòng)
    r = vnstock_call(lambda: Finance(source='KBS', symbol=symbol).ratio())
    item_map = {}
    latest_col = ''
    if r is not None and not r.empty:
      quarter_cols = [c for c in r.columns if c not in ['item', 'item_id']]
      sorted_cols = sorted(quarter_cols, key=parse_quarter_key)
      latest_col = sorted_cols[-1] if sorted_cols else r.columns[-1]
      item_map = dict(zip(r['item'], r[latest_col]))

    bvps = safe_num(item_map.get('Giá trị sổ sách của cổ phiếu (BVPS)'), 0.0)
    pe = safe_num(item_map.get('Chỉ số giá thị trường trên thu nhập (P/E)'), 0.0)
    pb = safe_num(item_map.get('Chỉ số giá thị trường trên giá trị sổ sách (P/B)'), 0.0)
    ps = safe_num(item_map.get('Chỉ số giá thị trường trên doanh thu thuần (P/S)'), 0.0)
    roe = safe_num(item_map.get('ROE bình quân 4 quý gần nhất'), 0.0)
    eps = safe_num(item_map.get('Thu nhập trên mỗi cổ phần của 4 quý gần nhất (EPS)'), 0.0)
    debt = safe_num(item_map.get('Tỷ số Nợ trên Vốn chủ sở hữu'), 0.0) / 100.0
    rev_growth = safe_num(item_map.get('Tăng trưởng  doanh thu thuần'), 0.0)
    profit_growth = safe_num(item_map.get('Tăng trưởng lợi nhuận sau thuế của CĐ công ty mẹ'), 0.0)
    gross_margin = safe_num(item_map.get('Tỷ suất lợi nhuận gộp biên'), 0.0)
    net_margin = safe_num(item_map.get('Tỷ suất sinh lợi trên doanh thu thuần'), 0.0)
    interest_cov = safe_num(item_map.get('Khả năng thanh toán lãi vay'), 0.0)
    nim = safe_num(item_map.get('Tỷ lệ thu nhập lãi thuần (NIM)'), 0.0)
    ldr = safe_num(item_map.get('Dư nợ cho vay khách hàng/Tổng vốn huy động (LDR)'), 0.0)

    ocf = 0.0
    ocf_status = classify_ocf_status(sector, ocf, profit_growth)
    has_audited_data = (pe > 0 or pb > 0 or roe != 0 or eps > 0 or len(ov) > 0)

    return {
        'name': name,
        'sector': sector,
        'pe': round(pe, 1) if pe > 0 else 0.0,
        'peStatic': round(pe, 2) if pe > 0 else 0.0,
        'pb': round(pb, 2) if pb > 0 else 0.0,
        'ps': round(ps, 2) if ps > 0 else 0.0,
        'roe': round(roe, 1) if roe != 0 else 0.0,
        'eps': round(eps) if eps > 0 else 0.0,
        'bvps': round(bvps) if bvps > 0 else 0.0,
        'debtToEquity': round(debt, 2),
        'revGrowth': round(rev_growth, 1),
        'profitGrowth': round(profit_growth, 1),
        'grossMargin': round(gross_margin, 1),
        'netMargin': round(net_margin, 1),
        'interestCoverage': round(interest_cov, 1),
        'ocf': round(ocf / 1e9, 1),
        'ocfStatus': ocf_status,
        'nim': round(nim, 2),
        'ldr': round(ldr, 1),
        'reportPeriod': str(latest_col),
        'summary': summary or f'Doanh nghiệp {symbol} niêm yết trên thị trường chứng khoán Việt Nam.',
        'isAudited': has_audited_data,
    }
  except Exception:
    return None
  finally:
    sys.stdout, sys.stderr = old_stdout, old_stderr

def compute_valuation_band(hist, sector, eps, bvps, roe_now, current_price):
  """
  Dải định giá hợp lý theo lịch sử multiple 12 quý của chính doanh nghiệp.
  - P/E cho doanh nghiệp thường; P/B cho ngân hàng/CTCK/bảo hiểm, bất động sản và ngành chu kỳ.
  - Bị định giá lại (multiple hiện tại < 70% trung vị 2 năm trước đó): không giả định quay về trung vị,
    dịch dải xuống (thấp = min(hiện tại, p25), giữa = p25, cao = trung vị).
  - P/B điều chỉnh theo ROE hiện tại / ROE trung vị dải (0.7 - 1.2; ngành chu kỳ tối đa 1.0).
  - Ngân hàng có chất lượng tài sản xấu (nợ xấu > 3%, tăng > 0.5 điểm % trong 4 quý, bao phủ < 100%): dùng nửa dưới của dải.
  """
  if not hist:
    return None
  periods = hist['periods'][-VALUATION_WINDOW_QUARTERS:]
  s = hist['series']
  use_pb = sector in PB_PRIMARY_SECTORS or not eps or eps <= 0
  if use_pb:
    key, base, label, max_mult = 'pb', bvps, 'P/B', 15.0
  else:
    key, base, label, max_mult = 'pe', eps, 'P/E', 60.0
  if not base or base <= 0:
    return None
  mult_series = [(p, s.get(key, {}).get(p)) for p in periods]
  mults = [v for _, v in mult_series if v is not None and 0 < v <= max_mult]
  if len(mults) < VALUATION_MIN_QUARTERS:
    return None

  p25, med, p75 = percentile(mults, 0.25), percentile(mults, 0.5), percentile(mults, 0.75)
  current_mult = current_price / base if current_price > 0 else None
  older = [v for _, v in mult_series[:-4] if v is not None and 0 < v <= max_mult]
  older_med = percentile(older, 0.5) if len(older) >= 4 else None
  de_rating = bool(current_mult and older_med and current_mult < 0.7 * older_med)
  notes = []
  recent = [v for _, v in mult_series[-4:] if v is not None and 0 < v <= max_mult]
  if de_rating and recent:
    low, mid, high = min(recent), percentile(recent, 0.5), max(percentile(recent, 0.5), p25)
    notes.append(
        f'{label} hiện tại {current_mult:.1f}x thấp hơn 30% so với trung vị 2 năm trước đó ({older_med:.1f}x): '
        f'thị trường đang định giá lại nên dải neo theo 4 quý gần nhất, không giả định multiple quay về mức cũ'
    )
  else:
    low, mid, high = p25, med, p75

  roe_factor = 1.0
  if use_pb and roe_now and roe_now > 0:
    roe_vals = [s['roe'][p] * 100 for p in periods if p in s.get('roe', {}) and s['roe'][p] > 0]
    roe_med = percentile(roe_vals, 0.5) if roe_vals else None
    if roe_med:
      cap_up = 1.0 if sector in CYCLICAL_SECTORS else 1.2
      roe_factor = max(0.7, min(cap_up, roe_now / roe_med))
      if abs(roe_factor - 1.0) >= 0.05:
        notes.append(f'P/B điều chỉnh x{roe_factor:.2f} theo ROE hiện tại {roe_now:.1f}% so với trung vị {roe_med:.1f}%')

  quality_flags = []
  if sector == 'Ngân hàng':
    npl_series = s.get('npl', {})
    npl_periods = [p for p in periods if p in npl_series]
    if npl_periods:
      npl_now = npl_series[npl_periods[-1]] * 100
      if npl_now > 3.0:
        quality_flags.append(f'nợ xấu {npl_now:.2f}% > 3%')
      if len(npl_periods) >= 5 and npl_now - npl_series[npl_periods[-5]] * 100 > 0.5:
        quality_flags.append(f'nợ xấu tăng {npl_now - npl_series[npl_periods[-5]] * 100:+.2f} điểm % trong 4 quý')
    cov, _ = _latest(s.get('nplCoverage', {}), periods)
    cov = abs(cov) if cov is not None else None
    if cov is not None and 0 < cov < 1.0:
      quality_flags.append(f'bao phủ nợ xấu {cov * 100:.0f}% < 100%')
    if quality_flags:
      low, mid, high = low, low, mid
      notes.append('Chất lượng tài sản suy yếu (' + ', '.join(quality_flags) + '): dùng nửa dưới của dải')

  fair = [round(base * m * roe_factor, -2) for m in (low, mid, high)]
  return {
      'method': label,
      'baseValue': round(base),
      'quarters': len(mults),
      'window': f'{periods[0]} → {periods[-1]}',
      'p25': round(p25, 2), 'median': round(med, 2), 'p75': round(p75, 2),
      'appliedMultiples': [round(low * roe_factor, 2), round(mid * roe_factor, 2), round(high * roe_factor, 2)],
      'currentMultiple': round(current_mult, 2) if current_mult else None,
      'deRating': de_rating,
      'roeFactor': round(roe_factor, 2),
      'qualityFlags': quality_flags,
      'fairLow': fair[0], 'fairMid': fair[1], 'fairHigh': fair[2],
      'notes': notes,
  }

def apply_vci_overlay(info, hist):
  """
  Bổ sung và chuẩn hóa số liệu tài chính theo nguồn VCI:
  - EPS, BVPS, ROE: Chuẩn hóa theo VCI (đồng nhất với chuỗi định giá 12 quý, phản ánh đúng
    số cổ phiếu sau chia thưởng/tăng vốn và kỳ BCTC mới nhất).
  - ROE: Chuẩn hóa theo VCI ROE TTM (tính theo VCSH bình quân chuẩn phân tích).
  - Cập nhật kỳ BCTC (reportPeriod), P/E, P/B tĩnh, biên lợi nhuận từ VCI.
  - DATA_CONFLICT chỉ ghi nhận khi có mâu thuẫn trọng yếu thực sự về bản chất.
  """
  info['dataConflicts'] = []
  summary = summarize_vci_history(hist)
  if not summary:
    return
  kbs_eps, kbs_roe = info.get('eps', 0.0), info.get('roe', 0.0)
  vci_eps, vci_roe = summary['eps'], summary['roe']

  if vci_eps is not None and kbs_eps:
    if (vci_eps > 0) != (kbs_eps > 0) and (abs(vci_eps) > 100 and abs(kbs_eps) > 100):
      info['dataConflicts'].append(f'EPS lệch dấu: KBS {kbs_eps:,.0f} đ vs VCI {vci_eps:,.0f} đ')
  if vci_roe is not None and kbs_roe:
    if (vci_roe > 0) != (kbs_roe > 0) and (abs(vci_roe) > 3.0 and abs(kbs_roe) > 3.0):
      info['dataConflicts'].append(f'ROE lệch dấu: KBS {kbs_roe:.1f}% vs VCI {vci_roe:.1f}%')

  info['kbs'] = {'eps': kbs_eps, 'bvps': info.get('bvps', 0.0), 'roe': kbs_roe}

  if vci_eps is not None and vci_eps > 0:
    info['eps'] = round(vci_eps)
  if summary['bvps'] and summary['bvps'] > 0:
    info['bvps'] = round(summary['bvps'])
  if vci_roe is not None:
    info['roe'] = round(vci_roe, 1)
    info['roeVci'] = round(vci_roe, 1)
  if summary.get('pe') and summary['pe'] > 0:
    info['peStatic'] = round(summary['pe'], 2)
  if summary.get('pb') and summary['pb'] > 0:
    info['pb'] = round(summary['pb'], 2)
  if summary.get('grossMargin') is not None:
    info['grossMargin'] = round(summary['grossMargin'] * 100, 1)
  if summary.get('netMargin') is not None:
    info['netMargin'] = round(summary['netMargin'] * 100, 1)
  if summary.get('period'):
    info['reportPeriod'] = summary['period']
    info['valuationSource'] = f"VCI kỳ {summary['period']}"

  info['roe4QAgo'] = round(summary['roe4QAgo'], 1) if summary['roe4QAgo'] is not None else None
  info['borrowDE'] = round(summary['borrowDE'], 2) if summary['borrowDE'] is not None else None
  info['cfoTtm'] = round(summary['cfoTtm'] / 1e9, 1) if summary['cfoTtm'] is not None else None
  info['shortBorrowings'] = round(summary['shortBorrowings'] / 1e9, 1)
  info['liquidAssets'] = round((summary['cash'] + summary['shortInvestments']) / 1e9, 1)
  if summary['cfoLatest'] is not None:
    info['ocf'] = round(summary['cfoLatest'] / 1e9, 1)
  info['ocfStatus'] = classify_ocf_status(info.get('sector', ''), info.get('ocf', 0.0), info.get('profitGrowth', 0.0))
  if info.get('sector') == 'Ngân hàng':
    if summary['npl'] is not None:
      info['npl'] = round(summary['npl'] * 100, 2)
    if summary['nplCoverage'] is not None:
      info['nplCoverage'] = round(abs(summary['nplCoverage']) * 100, 0)
    if summary['casa'] is not None:
      info['casa'] = round(summary['casa'] * 100, 1)
  info['vciHistory'] = hist

def assess_financial_distress(fundamental_info, sector):
  """
  Đánh giá căng thẳng tài chính (không áp dụng ngành tài chính). Trả về (is_distress, is_tail_lock, lý do).
  - Tail lock: Nguy cơ mất khả năng thanh toán nghiêm trọng dẫn tới kẹt sàn/mất thanh khoản:
    Chỉ kích hoạt khi nợ vay ngắn hạn vượt tiền mặt & CFO VÀ khả năng trả lãi kiệt quệ (interestCoverage < 1.2x)
    hoặc nợ vay/VCSH cực kỳ nguy hiểm (borrowDE > 3.5x kèm lỗ nặng kéo dài).
    Doanh nghiệp bán lẻ/chuỗi có khả năng trả lãi tốt (như FRT 4.2x) không bị coi là kẹt sàn.
  - Căng thẳng tài chính (Distress): CFO 4 quý âm kéo dài kết hợp nợ vay cao (cần theo dõi vốn lưu động).
  """
  fi = fundamental_info or {}
  if sector in FINANCIAL_SECTORS:
    return False, False, []
  reasons = []
  short_debt = fi.get('shortBorrowings')
  liquid = fi.get('liquidAssets')
  cfo_ttm = fi.get('cfoTtm')
  cfo = cfo_ttm if cfo_ttm is not None else fi.get('ocf', 0.0)
  borrow_de = fi.get('borrowDE')
  interest_cov = fi.get('interestCoverage', 0.0)
  tail_lock = False

  # Tiêu chí nguy hiểm thực sự
  critically_weak_interest = (interest_cov != 0 and interest_cov < 1.2)
  heavy_debt = (borrow_de is not None and borrow_de > 2.0)
  extreme_debt = (borrow_de is not None and borrow_de > 3.5)
  weak_profit = fi.get('roe', 0.0) <= 0 or fi.get('profitGrowth', 0.0) <= -20.0

  if short_debt is not None and liquid is not None and short_debt > 0:
    coverage = liquid + max(cfo_ttm or 0.0, 0.0)
    # Tail lock chỉ kích hoạt khi nợ ngắn hạn vượt tài sản thanh khoản VÀ khả năng trả lãi kiệt quệ < 1.2x
    if short_debt > coverage and (critically_weak_interest or (extreme_debt and weak_profit)):
      tail_lock = True
      reasons.append(
          f'Vay ngắn hạn {short_debt:,.0f} tỷ đ vượt tiền & đầu tư ngắn hạn {liquid:,.0f} tỷ đ'
          f' + CFO 4 quý {cfo_ttm if cfo_ttm is not None else 0:+,.0f} tỷ đ, kèm khả năng trả lãi kiệt quệ ({interest_cov:.1f}x < 1.2x)'
      )

  distress = tail_lock or (cfo < 0 and (heavy_debt or critically_weak_interest))
  if not tail_lock and cfo < 0 and heavy_debt:
    de_txt = f'nợ vay/VCSH {borrow_de:.2f}x' if borrow_de is not None else 'nợ vay cao'
    reasons.append(
        f'CFO 4 quý âm ({cfo:+,.1f} tỷ đ) do chu kỳ mở rộng vốn lưu động, {de_txt}, '
        f'cần theo dõi dòng tiền lưu động (khả năng trả lãi hiện tại đạt {interest_cov:.1f}x)'
    )

  return distress, tail_lock, reasons


def get_fundamental_profile(ticker, current_price):
  """Trả về hồ sơ cơ bản chuẩn hóa và điểm FA lấy từ vnstock/VCI."""
  sym = ticker.upper()

  # 1. Kiểm tra cache
  cached = get_cached_fundamental(sym)
  info = dict(cached) if cached else None

  # 2. Nếu chưa có trong cache, gọi vnstock
  if not info:
    fetched = fetch_from_vnstock(sym)
    if fetched:
      save_cached_fundamental(sym, fetched)
      info = dict(fetched)

  # 3. Nếu vnstock không có dữ liệu
  if not info:
    info = {
        'name': f'Công ty Cổ phần {sym}',
        'sector': 'Chưa phân loại',
        'pe': 0.0,
        'pb': 0.0,
        'roe': 0.0,
        'eps': 0.0,
        'bvps': 0.0,
        'debtToEquity': 0.0,
        'revGrowth': 0.0,
        'profitGrowth': 0.0,
        'grossMargin': 0.0,
        'netMargin': 0.0,
        'interestCoverage': 0.0,
        'ocf': 0.0,
        'ocfStatus': 'Dữ liệu chưa ghi nhận',
        'nim': 0.0,
        'ldr': 0.0,
        'reportPeriod': '',
        'summary': f'Mã {sym} đang được giao dịch trên sàn với thanh khoản ghi nhận thực tế theo phiên gần nhất.',
        'isAudited': False,
    }

  # 4. Đối chiếu & bổ sung từ lịch sử VCI
  apply_vci_overlay(info, get_vci_financial_history(sym))

  # Tính P/E, P/B và P/S động theo giá thị trường
  eps = info.get('eps', 0.0)
  bvps = info.get('bvps', 0.0)
  ps_static = info.get('ps', 0.0)
  pe_static = info.get('peStatic', info.get('pe', 0.0))
  if eps > 0 and current_price > 0:
    info['pe'] = round(current_price / eps, 2)
  if bvps > 0 and current_price > 0:
    info['pb'] = round(current_price / bvps, 2)
  if ps_static > 0 and pe_static > 0 and info.get('pe', 0.0) > 0:
    info['ps'] = round(ps_static * (info['pe'] / pe_static), 2)

  # Chấm điểm FA Score (0 - 100)
  is_audited = info.get('isAudited', False)
  roe = info.get('roe', 0.0)
  pe = info.get('pe', 0.0)
  growth = info.get('profitGrowth', 0.0)
  ocf = info['cfoTtm'] if info.get('cfoTtm') is not None else info.get('ocf', 0.0)
  gross_margin = info.get('grossMargin', 0.0)

  if not is_audited or (roe == 0.0 and pe == 0.0 and growth == 0.0):
    info['faScore'] = 0
    info['faVerdict'] = 'Dữ liệu chưa ghi nhận'
    info['faColor'] = 'slate'
    return info

  score = 50
  if roe >= 20:
    score += 20
  elif roe >= 14:
    score += 12
  elif roe < 8 and roe != 0:
    score -= 15

  if 0 < pe <= 12:
    score += 15
  elif 12 < pe <= 18:
    score += 8
  elif pe > 25:
    score -= 10

  if growth >= 20:
    score += 15
  elif growth > 0:
    score += 8
  elif growth < 0:
    score -= 10

  is_financial = info.get('sector', '') in FINANCIAL_SECTORS
  if not is_financial:
    if ocf > 0:
      score += 8
    elif ocf < 0 and growth > 0:
      score -= 12
    if gross_margin >= 30.0:
      score += 5

  score = max(10, min(98, score))
  info['faScore'] = score
  if score >= 80:
    info['faVerdict'] = 'Doanh Nghiệp Xuất Sắc (Top FA)'
    info['faColor'] = STATUS_COLOR_PERFECT
  elif score >= 60:
    info['faVerdict'] = 'Sức Khỏe Tài Chính Tốt'
    info['faColor'] = STATUS_COLOR_MOMENTUM
  elif score >= 45:
    info['faVerdict'] = 'Trung Bình / Cân Bằng'
    info['faColor'] = STATUS_COLOR_NEUTRAL
  else:
    info['faVerdict'] = 'Cơ Bản Kém / Cần Thận Trọng'
    info['faColor'] = STATUS_COLOR_RISK

  return info

def calculate_fundamental_valuation(fundamental_info, current_price, sector, w_levels, s2_support, multi_tf=None):
  """
  Định giá trung/dài hạn theo DẢI MULTIPLE LỊCH SỬ 12 quý của chính doanh nghiệp (VCI).
  Cổng 'GOM TÍCH SẢN': giá dưới vùng hợp lý + ROE >= 12% + xu hướng tuần không giảm + lợi nhuận không suy giảm.
  """
  empty_plan = {
      'decision': 'CHỜ BỔ SUNG BCTC',
      'type': DECISION_TYPE_WARNING,
      'reason': 'Dữ liệu BCTC chưa ghi nhận đầy đủ để định giá nội tại.',
      'target': 'Chưa ghi nhận (Thiếu BCTC)',
      'targetVal': None,
      'upsidePct': None,
      'fairRange': None,
      'entry': '--',
      'stop': '--',
      'dcaZone': '--',
      'invalidation': '--',
      'bandLabel': '--',
      'valuationMethod': 'Chưa xác định',
      'valuationBand': None,
  }
  if not fundamental_info:
    return empty_plan

  eps = fundamental_info.get('eps', 0.0)
  bvps = fundamental_info.get('bvps', 0.0)
  roe = fundamental_info.get('roe', 0.0)
  is_audited = fundamental_info.get('isAudited', False)
  profit_growth = fundamental_info.get('profitGrowth', 0.0)
  roe_4q_ago = fundamental_info.get('roe4QAgo')
  roe_vci = fundamental_info.get('roeVci', roe)

  w_ma50 = w_levels.get('wMa50', current_price)
  w52_low = w_levels.get('w52Low', current_price * 0.8)

  is_distress, _, distress_reasons = assess_financial_distress(fundamental_info, sector)
  band = compute_valuation_band(
      fundamental_info.get('vciHistory'), sector, eps, bvps, roe_vci, current_price
  )

  dca_base = min(current_price * 0.99, max(w_ma50, s2_support))
  dca_min = round(min(dca_base * 0.96, s2_support), -2)
  dca_max = round(dca_base, -2)
  dca_zone = f"{dca_min:,.0f} - {dca_max:,.0f} đ"

  inval_price = round(min(w_ma50 * 0.95, w52_low), -2)
  inval_pct = round(((current_price - inval_price) / current_price) * 100, 1) if current_price > 0 else 10.0
  inval_str = f"{inval_price:,.0f} đ (-{inval_pct}%)"

  plan = dict(empty_plan)
  plan.update({'entry': dca_zone, 'dcaZone': dca_zone, 'stop': inval_str, 'invalidation': inval_str, 'valuationBand': band})

  if is_distress:
    plan.update({
        'decision': 'CẢNH BÁO RỦI RO TÀI CHÍNH (TRÁNH ĐẦU TƯ)',
        'type': DECISION_TYPE_DANGER,
        'reason': f"Căng thẳng tài chính: {'; '.join(distress_reasons)}. Không đạt tiêu chuẩn đầu tư trung dài hạn.",
        'target': 'Không áp dụng định giá (Căng thẳng nợ / thanh khoản)',
        'dcaZone': 'Không khuyến nghị gom',
        'entry': 'Không khuyến nghị gom',
        'invalidation': f"Thủng đáy 52W: {w52_low:,.0f} đ",
        'stop': f"Thủng đáy 52W: {w52_low:,.0f} đ",
        'valuationMethod': 'Cảnh báo căng thẳng tài chính',
    })
    return plan

  if not is_audited or (eps <= 0 and roe <= 0):
    plan.update({
        'reason': f'Dữ liệu BCTC chưa đầy đủ hoặc kết quả kinh doanh âm (ROE {roe:.1f}%, EPS {eps:,.0f} đ). Chưa đủ điều kiện giải ngân tích sản trung dài hạn.',
        'target': 'Chưa ghi nhận (LNST âm / Thiếu BCTC)',
        'entry': '--', 'dcaZone': '--', 'stop': '--', 'invalidation': '--',
    })
    return plan

  if not band:
    plan.update({
        'decision': 'THEO DÕI NỘI TẠI',
        'reason': f'Chưa đủ {VALUATION_MIN_QUARTERS} quý lịch sử P/E, P/B hợp lệ để dựng dải định giá; không đưa ra giá mục tiêu.',
        'target': 'Chưa ghi nhận (Thiếu lịch sử định giá)',
        'valuationMethod': 'Chưa đủ lịch sử định giá',
    })
    return plan

  fair_low, fair_mid, fair_high = band['fairLow'], band['fairMid'], band['fairHigh']
  upside_pct = round((fair_mid - current_price) / current_price * 100, 1) if current_price > 0 else None
  applied = band['appliedMultiples']
  method = (
      f"Dải {band['method']} {band['quarters']} quý ({band['window']}): p25 {band['p25']}x · trung vị {band['median']}x · p75 {band['p75']}x; "
      f"dải áp dụng {applied[0]}x - {applied[1]}x - {applied[2]}x"
      f" × {'BVPS' if band['method'] == 'P/B' else 'EPS'} {band['baseValue']:,.0f} đ"
  )
  notes_txt = (' ' + '; '.join(band['notes']) + '.') if band['notes'] else ''
  target_str = f"{fair_low:,.0f} - {fair_high:,.0f} đ (giữa {fair_mid:,.0f} đ, {upside_pct:+.1f}%)"

  trend_down = bool((multi_tf or {}).get('isSevereDowntrend')) or (w_ma50 and current_price < w_ma50 * 0.97)
  roe_falling = roe_4q_ago is not None and roe_vci < roe_4q_ago - 3.0
  earnings_down = profit_growth < 0 or roe_falling
  earnings_txt = (
      f"tăng trưởng LN {profit_growth:+.1f}%" + (f", ROE (VCI) giảm từ {roe_4q_ago:.1f}% xuống {roe_vci:.1f}% trong 4 quý" if roe_falling else '')
  )

  if current_price < fair_low or (current_price <= fair_mid and upside_pct is not None and upside_pct >= 15.0):
    if trend_down:
      decision, dec_type = 'RẺ SO VỚI LỊCH SỬ - CHỜ XU HƯỚNG ĐẢO CHIỀU', DECISION_TYPE_WARNING
      reason = (
          f"Giá {current_price:,.0f} đ thấp hơn vùng hợp lý {target_str}, nhưng giá dưới MA50 tuần ({w_ma50:,.0f} đ) / xu hướng giảm. "
          f"Chưa gom khi chưa có tín hiệu tạo đáy (giá lấy lại MA50 tuần kèm thanh khoản)."
      )
    elif earnings_down:
      decision, dec_type = 'RẺ NHƯNG LỢI NHUẬN SUY GIẢM - CHỜ XÁC NHẬN', DECISION_TYPE_WARNING
      reason = (
          f"Định giá thấp hơn lịch sử ({target_str}) nhưng {earnings_txt}: có thể rẻ vì lợi nhuận đang giảm. "
          f"Chờ BCTC quý tới xác nhận lợi nhuận ổn định."
      )
    elif fundamental_info.get('dataConflicts'):
      decision, dec_type = 'CHỜ ĐỐI CHIẾU SỐ LIỆU (DATA_CONFLICT)', DECISION_TYPE_WARNING
      reason = (
          f"Giá dưới vùng hợp lý {target_str}, nhưng số liệu đầu vào định giá đang lệch giữa các nguồn "
          f"({'; '.join(fundamental_info['dataConflicts'])}). Đối chiếu BCTC gốc trên HOSE/HNX trước khi gom."
      )
    elif roe >= 12.0:
      decision, dec_type = 'GOM TÍCH SẢN (DƯỚI VÙNG HỢP LÝ)', DECISION_TYPE_SUCCESS
      reason = (
          f"ROE {roe:.1f}%, {earnings_txt}, xu hướng tuần chưa gãy. Giá dưới vùng hợp lý {target_str}. "
          f"Có thể gom từng phần quanh {dca_zone}, dừng nếu thủng {inval_str}."
      )
    else:
      decision, dec_type = 'NẮM GIỮ THEO DÕI NỀN', DECISION_TYPE_WARNING
      reason = f"Giá dưới vùng hợp lý {target_str} nhưng ROE {roe:.1f}% thấp (< 12%), chưa đủ chất lượng để tích sản."
  elif current_price <= fair_high:
    decision, dec_type = 'TRONG VÙNG HỢP LÝ - NẮM GIỮ', DECISION_TYPE_WARNING
    reason = f"Giá {current_price:,.0f} đ nằm trong vùng hợp lý {target_str}. Nắm giữ nếu đã có, không mua đuổi; vùng gom ưu tiên {dca_zone}."
  else:
    decision, dec_type = 'ĐỊNH GIÁ CAO - CHỜ CHIẾT KHẤU', DECISION_TYPE_WARNING
    reason = f"Giá {current_price:,.0f} đ cao hơn vùng hợp lý {target_str}. Kiên nhẫn chờ chiết khấu về vùng {dca_zone}."

  plan.update({
      'decision': decision,
      'type': dec_type,
      'reason': f"{reason} Phương pháp: {method}.{notes_txt}",
      'target': target_str,
      'targetVal': fair_mid,
      'upsidePct': upside_pct,
      'fairRange': [fair_low, fair_mid, fair_high],
      'bandLabel': f"{band['method']} p25-med-p75 ({applied[0]}x - {applied[1]}x - {applied[2]}x)",
      'valuationMethod': method,
  })
  return plan
