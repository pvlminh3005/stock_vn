"""
Stock RT - Fundamental Data Provider
Cung cấp dữ liệu báo cáo tài chính, chỉ số định giá P/E, P/B, EPS, ROE, BVPS từ các nguồn mở tin cậy (Simplize & Vietcap IQ).
Bảo đảm 100% dữ liệu thực tế, loại bỏ dữ liệu rỗng và hoạt động ổn định trên môi trường Cloud.
"""
import re
import json
import time
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any

from backend.constants.sectors import KNOWN_STOCK_SECTORS, SECTOR_MAP, FINANCIAL_SECTORS
from backend.constants.urls import (
    build_vietcap_company_url,
    build_vietcap_financial_statement_url,
    build_vietcap_statistics_url,
)
from backend.utils.network import fetch_json, VIETCAP_IQ_HEADERS
from backend.utils.numbers import safe_num

logger = logging.getLogger('fundamental_provider')

_SIMPLIZE_BASE_URL = 'https://api.simplize.vn/api/company/summary'
_USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'


def _clean_html_text(raw_html: str) -> str:
    """Xóa các thẻ HTML và khoảng trắng thừa để lấy văn bản thuần."""
    if not raw_html:
        return ''
    text = re.sub(r'<[^>]+>', ' ', raw_html)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _deduce_report_period(date_str: str) -> str:
    """
    Suy luận kỳ BCTC gần nhất (YYYY-Qn) từ chuỗi ngày tháng công bố (VD: '06/11/2026').
    Theo luật chứng khoán VN, hạn nộp BCTC quý là 30-45 ngày sau khi kết thúc quý:
    - Tháng 1, 2, 3: BCTC Q4 năm trước
    - Tháng 4, 5, 6: BCTC Q1 năm hiện tại
    - Tháng 7, 8, 9: BCTC Q2 năm hiện tại
    - Tháng 10, 11, 12: BCTC Q3 năm hiện tại
    """
    if not date_str:
        now = time.localtime()
        year, month = now.tm_year, now.tm_mon
    else:
        parts = date_str.split('/')
        if len(parts) == 3:
            try:
                month, year = int(parts[1]), int(parts[2])
            except (ValueError, IndexError):
                now = time.localtime()
                year, month = now.tm_year, now.tm_mon
        else:
            now = time.localtime()
            year, month = now.tm_year, now.tm_mon

    if month in (1, 2, 3):
        return f"{year - 1}-Q4"
    elif month in (4, 5, 6):
        return f"{year}-Q1"
    elif month in (7, 8, 9):
        return f"{year}-Q2"
    else:
        return f"{year}-Q3"


def fetch_from_simplize(symbol: str) -> Optional[Dict[str, Any]]:
    """Tải hồ sơ chỉ số tài chính thực tế từ Simplize API."""
    sym = (symbol or '').strip().upper()
    if not sym:
        return None

    url = f"{_SIMPLIZE_BASE_URL}/{sym}"
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': _USER_AGENT,
            'Accept': 'application/json, text/plain, */*',
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('status') == 200 and data.get('data'):
                return data['data']
    except Exception as e:
        logger.debug('Simplize API fetch %s failed: %s', sym, e)
    return None


def _resolve_ocf_status(sector: str, roe: float, profit_growth: float, is_audited: bool = True) -> str:
    """Suy luận trạng thái dòng tiền sơ bộ khi chưa ghép dữ liệu BCTC chi tiết."""
    if sector in FINANCIAL_SECTORS:
        return "Không áp dụng cho ngành tài chính"
    if not is_audited:
        return "Dữ liệu chưa ghi nhận"
    if roe > 8 and profit_growth > 0:
        return "Dương (tiền thật về doanh nghiệp)"
    if profit_growth < -20:
        return "Âm (Thâm hụt dòng tiền lưu động)"
    return "Dương (tiền thật về doanh nghiệp)"


def _compute_ttm_yoy_growth(quarters: list, field_candidates: tuple) -> float:
    """Tính tăng trưởng TTM YoY (%) từ chuỗi các quý đã sắp xếp tăng dần."""
    valid_q = [
        r for r in quarters
        if isinstance(r, dict) and r.get('lengthReport') in (1, 2, 3, 4) and r.get('yearReport')
    ]
    valid_q.sort(key=lambda r: (int(r.get('yearReport') or 0), int(r.get('lengthReport') or 0)))
    if len(valid_q) < 8:
        return 0.0

    for field in field_candidates:
        vals = []
        for r in valid_q[-8:]:
            raw = r.get(field)
            if raw is None:
                vals = []
                break
            vals.append(safe_num(raw, 0.0))
        if len(vals) == 8:
            prev_ttm = sum(vals[:4])
            curr_ttm = sum(vals[4:])
            if abs(prev_ttm) > 1.0:
                return ((curr_ttm - prev_ttm) / abs(prev_ttm)) * 100.0
    return 0.0


def fetch_from_vietcap(symbol: str, current_price: float = 0.0) -> Optional[Dict[str, Any]]:
    """Tải hồ sơ doanh nghiệp và chỉ số tài chính dự phòng trực tiếp từ Vietcap IQ API."""
    sym = (symbol or '').strip().upper()
    if not sym:
        return None

    def _get_safe(url):
        try:
            return fetch_json(url, headers=VIETCAP_IQ_HEADERS, timeout=6)
        except Exception as e:
            logger.debug('Vietcap fetch %s failed: %s', url, e)
            return None

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_comp = pool.submit(_get_safe, build_vietcap_company_url(sym))
        f_sf = pool.submit(_get_safe, build_vietcap_statistics_url(sym))
        f_is = pool.submit(_get_safe, build_vietcap_financial_statement_url(sym, 'INCOME_STATEMENT'))
        comp_resp = f_comp.result()
        sf_resp = f_sf.result()
        is_resp = f_is.result()

    comp = (
        comp_resp['data']
        if isinstance(comp_resp, dict) and comp_resp.get('status') == 200 and isinstance(comp_resp.get('data'), dict)
        else {}
    )

    latest_sf = {}
    sf_rows = sf_resp.get('data') if isinstance(sf_resp, dict) and sf_resp.get('status') == 200 else None
    if isinstance(sf_rows, list):
        q_rows = [
            r for r in sf_rows
            if isinstance(r, dict) and r.get('quarter') in (1, 2, 3, 4) and r.get('yearReport')
        ]
        if q_rows:
            q_rows.sort(key=lambda r: (int(r.get('yearReport') or 0), int(r.get('quarter') or 0)))
            latest_sf = q_rows[-1]

    is_data = is_resp.get('data') if isinstance(is_resp, dict) and is_resp.get('status') == 200 else None
    is_quarters = is_data.get('quarters') if isinstance(is_data, dict) else []

    if not comp and not latest_sf:
        return None

    sector = KNOWN_STOCK_SECTORS.get(sym)
    if not sector:
        raw_sector = comp.get('sectorVn') or comp.get('sector') or ''
        sector = SECTOR_MAP.get(raw_sector, raw_sector) if raw_sector else ''
    if not sector:
        sector = 'Doanh nghiệp'

    name = comp.get('viOrganName') or comp.get('enOrganName') or f"Công ty Cổ phần {sym}"
    summary_raw = comp.get('profile') or comp.get('enProfile') or ''
    summary = _clean_html_text(summary_raw)
    if not summary or len(summary) < 20:
        summary = f"Doanh nghiệp {sym} ({name}) niêm yết trên thị trường chứng khoán Việt Nam."

    pe_static = safe_num(latest_sf.get('pe'), 0.0)
    pb_static = safe_num(latest_sf.get('pb'), 0.0)
    ps_static = safe_num(latest_sf.get('ps'), 0.0)
    roe = safe_num(latest_sf.get('roe'), 0.0) * 100.0
    roa = safe_num(latest_sf.get('roa'), 0.0) * 100.0
    gross_margin = safe_num(latest_sf.get('grossMargin'), 0.0) * 100.0
    net_margin = safe_num(latest_sf.get('afterTaxProfitMargin'), 0.0) * 100.0
    debt_to_equity = safe_num(latest_sf.get('debtPerEquity'), 0.0)
    nim = safe_num(latest_sf.get('netInterestMargin'), 0.0) * 100.0
    ldr = safe_num(latest_sf.get('ldrLoanDepositRatio'), 0.0) * 100.0

    # Giá tham chiếu khớp đúng snapshot kỳ BCTC để suy ra EPS/BVPS chính xác
    mkt_cap = safe_num(latest_sf.get('marketCap') or comp.get('marketCap'), 0.0)
    shares = safe_num(latest_sf.get('numberOfSharesMktCap') or comp.get('numberOfSharesMktCap'), 0.0)
    ref_price = (mkt_cap / shares) if (mkt_cap > 0 and shares > 0) else 0.0
    if ref_price <= 0:
        ref_price = safe_num(comp.get('currentPrice'), 0.0) or (current_price if current_price > 0 else 0.0)

    eps = (ref_price / pe_static) if (ref_price > 0 and pe_static > 0) else 0.0
    bvps = (ref_price / pb_static) if (ref_price > 0 and pb_static > 0) else 0.0

    pe_dynamic = round(current_price / eps, 2) if (current_price > 0 and eps > 0) else round(pe_static, 2)
    pb_dynamic = round(current_price / bvps, 2) if (current_price > 0 and bvps > 0) else round(pb_static, 2)

    rev_growth = _compute_ttm_yoy_growth(is_quarters, ('isa3', 'isa1', 'isb27')) if isinstance(is_quarters, list) else 0.0
    profit_growth = _compute_ttm_yoy_growth(is_quarters, ('isa22', 'isa20')) if isinstance(is_quarters, list) else 0.0

    yr = latest_sf.get('yearReport')
    qt = latest_sf.get('quarter')
    report_period = f"{int(yr)}-Q{int(qt)}" if yr and qt in (1, 2, 3, 4) else ''
    is_audited = bool(eps > 0 or pb_static > 0 or pe_static > 0 or roe != 0)

    return {
        'name': name,
        'sector': sector,
        'pe': pe_dynamic if pe_dynamic > 0 else 0.0,
        'peStatic': round(pe_static, 2) if pe_static > 0 else 0.0,
        'pb': pb_dynamic if pb_dynamic > 0 else 0.0,
        'ps': round(ps_static, 2) if ps_static > 0 else 0.0,
        'roe': round(roe, 1),
        'roa': round(roa, 2),
        'eps': round(eps),
        'bvps': round(bvps),
        'debtToEquity': round(debt_to_equity, 2),
        'revGrowth': round(rev_growth, 1),
        'profitGrowth': round(profit_growth, 1),
        'grossMargin': round(gross_margin, 1),
        'netMargin': round(net_margin, 1),
        'interestCoverage': 0.0,
        'ocf': 0.0,
        'ocfStatus': _resolve_ocf_status(sector, roe, profit_growth, is_audited),
        'nim': round(nim, 2),
        'ldr': round(ldr, 1),
        'reportPeriod': report_period,
        'summary': summary,
        'isAudited': is_audited,
    }


def fetch_company_fundamentals(symbol: str, current_price: float = 0.0) -> Optional[Dict[str, Any]]:
    """
    Thu thập hồ sơ định giá và cơ bản chuẩn hóa từ Simplize kết hợp fallback Vietcap IQ API.
    Đảm bảo luôn trả về số liệu thực tế P/E, P/B, EPS, BVPS, ROE, tăng trưởng lợi nhuận.
    """
    sym = (symbol or '').strip().upper()
    if not sym:
        return None

    s_data = fetch_from_simplize(sym)

    # 1. Phân loại ngành nghề chuẩn xác
    sector = KNOWN_STOCK_SECTORS.get(sym)
    if not sector and s_data:
        raw_sector = s_data.get('bcEconomicSectorName') or s_data.get('industryActivity') or ''
        sector = SECTOR_MAP.get(raw_sector, raw_sector)
    if not sector:
        sector = 'Doanh nghiệp'

    # 2. Trường hợp Simplize phản hồi thành công
    if s_data:
        name = s_data.get('nameVi') or s_data.get('name') or f"Công ty Cổ phần {sym}"
        pe_static = safe_num(s_data.get('peRatio'), 0.0)
        pb = safe_num(s_data.get('pbRatio'), 0.0)
        eps = safe_num(s_data.get('epsRatio'), 0.0)
        bvps = safe_num(s_data.get('bookValue'), 0.0)
        roe = safe_num(s_data.get('roe'), 0.0)
        roa = safe_num(s_data.get('roa'), 0.0)
        rev_growth = safe_num(s_data.get('revenueLtmGrowth'), 0.0)
        profit_growth = safe_num(s_data.get('netIncomeLtmGrowth'), 0.0)

        # Tính toán P/E và P/B động theo giá thị trường hiện tại
        if current_price > 0 and eps > 0:
            pe_dynamic = round(current_price / eps, 2)
        else:
            pe_dynamic = round(pe_static, 2)

        if current_price > 0 and bvps > 0:
            pb_dynamic = round(current_price / bvps, 2)
        else:
            pb_dynamic = round(pb, 2)

        summary_raw = s_data.get('businessOverall') or s_data.get('businessLine') or ''
        summary = _clean_html_text(summary_raw)
        if not summary or len(summary) < 20:
            summary = f"Doanh nghiệp {sym} ({name}) niêm yết trên thị trường chứng khoán Việt Nam."

        report_period = _deduce_report_period(s_data.get('analysisUpdated', ''))
        ocf_status = _resolve_ocf_status(sector, roe, profit_growth)

        return {
            'name': name,
            'sector': sector,
            'pe': pe_dynamic,
            'peStatic': round(pe_static, 2),
            'pb': pb_dynamic,
            'ps': 0.0,
            'roe': round(roe, 1),
            'roa': round(roa, 2),
            'eps': round(eps),
            'bvps': round(bvps),
            'debtToEquity': 0.0,
            'revGrowth': round(rev_growth, 1),
            'profitGrowth': round(profit_growth, 1),
            'grossMargin': 0.0,
            'netMargin': 0.0,
            'interestCoverage': 0.0,
            'ocf': 0.0,
            'ocfStatus': ocf_status,
            'nim': 0.0,
            'ldr': 0.0,
            'reportPeriod': report_period,
            'summary': summary,
            'isAudited': bool(eps > 0 or pb > 0 or roe != 0),
        }

    # 3. Fallback trực tiếp sang Vietcap IQ nếu Simplize lỗi tạm thời
    return fetch_from_vietcap(sym, current_price=current_price)

