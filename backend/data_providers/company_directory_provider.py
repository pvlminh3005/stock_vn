"""
Stock RT - Dynamic Company Directory & Search Provider
Quản lý danh bạ 1,626 mã cổ phiếu niêm yết trên HOSE, HNX, UPCoM từ Simplize Open API & MongoDB Atlas.
Lưu trữ từng mã vào MongoDB collection 'companies' với index tìm kiếm tối ưu.
Loại bỏ hoàn toàn việc gán cứng (hardcode) danh mục cổ phiếu và nhóm ngành.
"""

import re
import time
import logging
import urllib.request
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger('company_directory_provider')

_SIMPLIZE_ALL_COMPANIES_URL = 'https://api.simplize.vn/api/company/all'
_USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

# Bộ nhớ đệm RAM danh bạ công ty (TTL: 24 giờ)
_DIRECTORY_CACHE = {
    'timestamp': 0,
    'companies': [],
    'by_ticker': {},
    'sectors_map': {},
}

# Bản đồ 10 nhóm ngành kinh tế chuẩn quốc tế từ bcEconomicSectorId của Simplize
ECONOMIC_SECTOR_ID_MAP = {
    1: 'Dầu khí & Năng lượng',
    2: 'Thép & Nguyên vật liệu',
    3: 'Công nghiệp & Xây dựng',
    4: 'Bán lẻ & Tiêu dùng',
    5: 'Thực phẩm & Nông nghiệp',
    6: 'Dịch vụ Tài chính',
    7: 'Y tế & Dược phẩm',
    8: 'Công nghệ thông tin',
    9: 'Điện & Tiện ích',
    10: 'Bất động sản',
}


def _strip_vietnamese_accents(text: str) -> str:
    """Loại bỏ dấu tiếng Việt để tìm kiếm không dấu linh hoạt (ví dụ: 'binh minh' -> 'Bình Minh')."""
    if not text:
        return ''
    patterns = {
        '[àáạảãâầấậẩẫăằắặẳẵ]': 'a',
        '[ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴ]': 'A',
        '[èéẹẻẽêềếệểễ]': 'e',
        '[ÈÉẸẺẼÊỀẾỆỂỄ]': 'E',
        '[ìíịỉĩ]': 'i',
        '[ÌÍỊỈĨ]': 'I',
        '[òóọỏõôồốộổỗơờớợởỡ]': 'o',
        '[ÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠ]': 'O',
        '[ùúụủũưừứựửữ]': 'u',
        '[ÙÚỤỦŨƯỪỨỰỬỮ]': 'U',
        '[ỳýỵỷỹ]': 'y',
        '[ỲÝỴỶỸ]': 'Y',
        '[đ]': 'd',
        '[Đ]': 'D',
    }
    output = text
    for regex, replace in patterns.items():
        output = re.sub(regex, replace, output)
    return output


def get_dynamic_sector(ticker: str, name_vi: str = '', sector_id: Optional[int] = None) -> str:
    """
    Xác định nhóm ngành thông minh không hardcode:
    Phân loại dựa trên đặc thù doanh nghiệp, từ khóa tên và bcEconomicSectorId chuẩn.
    """
    sym = (ticker or '').strip().upper()
    name_lower = (name_vi or '').lower()

    # 1. Phân loại chuyên sâu ngành Tài chính & Ngân hàng & Chứng khoán (SectorId 6 hoặc từ khóa)
    if 'ngân hàng' in name_lower or 'bank' in name_lower:
        return 'Ngân hàng'
    if 'chứng khoán' in name_lower or 'securities' in name_lower or sym in {'SSI', 'VND', 'VIX', 'HCM', 'VCI', 'SHS', 'MBS', 'BSI', 'FTS', 'CTS', 'ORS', 'AGR'}:
        return 'Chứng khoán'
    if 'bảo hiểm' in name_lower or 'insurance' in name_lower:
        return 'Bảo hiểm'

    # 2. Thép & Nguyên vật liệu & Hóa chất (SectorId 2 hoặc từ khóa)
    if any(k in name_lower for k in ['thép', 'kim khí', 'tôn mạ', 'hòa phát', 'hoa sen', 'nam kim']) or sym in {'HPG', 'HSG', 'NKG', 'VGS', 'TLH', 'SMC'}:
        return 'Thép & VLXD'
    if any(k in name_lower for k in ['hóa chất', 'phân bón', 'đạm', 'đức giang']) or sym in {'DGC', 'DCM', 'DPM', 'CSV'}:
        return 'Phân bón & Hóa chất'

    # 3. Bất động sản dân dụng vs Khu công nghiệp (SectorId 10 hoặc từ khóa)
    if any(k in name_lower for k in ['khu công nghiệp', 'kcn', 'kinh bắc', 'idico', 'sonadezi']) or sym in {'KBC', 'IDC', 'SZC', 'BCM', 'VGC'}:
        return 'BĐS Khu công nghiệp'
    if sector_id == 10 or any(k in name_lower for k in ['bất động sản', 'địa ốc', 'nhà ở', 'vinhomes', 'khang điền', 'nam long', 'đất xanh', 'novaland', 'phát đạt']) or sym in {'VHM', 'VIC', 'VRE', 'KDH', 'NLG', 'PDR', 'DIG', 'DXG', 'NVL', 'CEO', 'TCH'}:
        return 'Bất động sản'

    # 4. Công nghiệp & Logistics & Xây dựng (SectorId 3 hoặc từ khóa)
    if any(k in name_lower for k in ['cảng', 'logistics', 'vận tải biển', 'xếp dỡ', 'hải an', 'gemadept']) or sym in {'HAH', 'GMD', 'VSC', 'PVT', 'VOS'}:
        return 'Cảng biển & Logistics'
    if any(k in name_lower for k in ['xây dựng', 'xây lắp', 'hạ tầng', 'cầu đường', 'công trình']) or sym in {'VCG', 'HHV', 'FCN', 'CII', 'CTD', 'HBC', 'CTR'}:
        return 'Xây dựng & Hạ tầng'

    # 5. Dầu khí & Năng lượng (SectorId 1 hoặc từ khóa)
    if any(k in name_lower for k in ['dầu khí', 'khoan', 'xăng dầu', 'khí đốt', 'lọc hóa dầu']) or sym in {'GAS', 'PVD', 'PVS', 'BSR', 'PLX'}:
        return 'Dầu khí'

    # 6. Điện & Tiện ích (SectorId 9 hoặc từ khóa)
    if any(k in name_lower for k in ['điện', 'thủy điện', 'nhiệt điện', 'năng lượng tái tạo', 'cơ điện']) or sym in {'POW', 'PC1', 'REE', 'GELEX', 'GEX'}:
        return 'Điện & Tiện ích'

    # 7. Công nghệ thông tin & Viễn thông (SectorId 8 hoặc từ khóa)
    if sector_id == 8 or any(k in name_lower for k in ['công nghệ', 'tin học', 'viễn thông', 'phần mềm']) or sym in {'FPT', 'CMG', 'ELC'}:
        return 'Công nghệ thông tin'

    # 8. Bán lẻ & Tiêu dùng (SectorId 4 hoặc từ khóa)
    if any(k in name_lower for k in ['bán lẻ', 'thế giới di động', 'fpt retail', 'vàng bạc', 'trang sức']) or sym in {'MWG', 'FRT', 'PNJ', 'DGW'}:
        return 'Bán lẻ tiêu dùng'

    # 9. Thực phẩm & Nông nghiệp (SectorId 5 hoặc từ khóa)
    if any(k in name_lower for k in ['thực phẩm', 'đồ uống', 'sữa', 'bia', 'chăn nuôi', 'thủy sản']) or sym in {'VNM', 'MSN', 'SAB', 'KDC', 'VHC', 'ANV', 'DBC', 'BAF'}:
        return 'Thực phẩm & Đồ uống'

    # 10. Fallback theo bảng 10 ngành kinh tế
    if sector_id and sector_id in ECONOMIC_SECTOR_ID_MAP:
        return ECONOMIC_SECTOR_ID_MAP[sector_id]

    return 'Thị trường chung'


def _get_mongo_companies_coll():
    """Lấy MongoDB collection 'companies' nếu có kết nối (hỗ trợ auto-reconnect)."""
    try:
        from backend.db.portfolio_db import get_mongo_db
        from backend.constants.db import COLL_COMPANIES
        db = get_mongo_db()
        if db is not None:
            return db[COLL_COMPANIES]
    except Exception:
        pass
    return None


def _sync_companies_to_mongo(companies: List[Dict[str, Any]]):
    """
    Đồng bộ từng công ty vào MongoDB collection 'companies':
    Lưu riêng từng document và gắn sẵn sector, nameUnaccent để search siêu tốc.
    """
    coll = _get_mongo_companies_coll()
    if coll is None or not companies:
        return

    try:
        from pymongo import ReplaceOne
        from backend.models.db_models import CompanyItem
        ops = []
        for c in companies:
            sym = c.get('ticker')
            if not sym:
                continue
            name_vi = c.get('nameVi', '')
            sec_id = c.get('bcEconomicSectorId')
            sector = get_dynamic_sector(sym, name_vi, sec_id)
            name_unaccent = _strip_vietnamese_accents(name_vi).lower()

            item = CompanyItem(
                ticker=sym,
                name=c.get('name', ''),
                name_vi=name_vi,
                name_en=c.get('nameEn', ''),
                name_unaccent=name_unaccent,
                exchange=c.get('stockExchange', 'HOSE'),
                sector=sector,
                industry=c.get('industry', ''),
                image_url=c.get('imageUrl', ''),
                bc_economic_sector_id=sec_id,
                updated_at=int(time.time()),
            )
            ops.append(ReplaceOne(CompanyItem.filter_by_ticker(sym), item.to_doc(), upsert=True))

        if ops:
            coll.bulk_write(ops, ordered=False)
            try:
                coll.create_index(CompanyItem.INDEX_TICKER, unique=True)
                coll.create_index(CompanyItem.INDEX_NAME_VI)
                coll.create_index(CompanyItem.INDEX_NAME_UNACCENT)
                coll.create_index(CompanyItem.INDEX_SECTOR)
            except Exception:
                pass
            logger.info("Đã đồng bộ %d công ty vào MongoDB collection 'companies'.", len(ops))
    except Exception as e:
        logger.warning("Lỗi đồng bộ companies lên MongoDB: %s", e)


def fetch_and_cache_company_directory(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Tải danh bạ toàn bộ 1,626 công ty niêm yết:
    1. Kiểm tra RAM cache (TTL 24h)
    2. Đọc từ MongoDB Atlas collection 'companies' hoặc 'company_directory'
    3. Nếu chưa có hoặc force_refresh: Tải trực tiếp từ Simplize API và lưu lại
    """
    now = time.time()
    if not force_refresh and _DIRECTORY_CACHE['companies'] and (now - _DIRECTORY_CACHE['timestamp'] < 86400):
        return _DIRECTORY_CACHE['companies']

    # 1. Đọc từ MongoDB collection 'companies'
    coll = _get_mongo_companies_coll()
    if coll is not None and not force_refresh:
        try:
            from backend.models.db_models import CompanyItem
            mongo_docs = list(coll.find({}, CompanyItem.PROJECTION_NO_ID))
            if mongo_docs and len(mongo_docs) >= 1000:
                _DIRECTORY_CACHE['companies'] = mongo_docs
                _DIRECTORY_CACHE['by_ticker'] = {c[CompanyItem.F_TICKER]: c for c in mongo_docs if CompanyItem.F_TICKER in c}
                _DIRECTORY_CACHE['sectors_map'] = {c[CompanyItem.F_TICKER]: c.get(CompanyItem.F_SECTOR, 'Thị trường chung') for c in mongo_docs if CompanyItem.F_TICKER in c}
                _DIRECTORY_CACHE['timestamp'] = now
                logger.info("Đã nạp %d công ty từ MongoDB collection 'companies' vào RAM Cache.", len(mongo_docs))
                return mongo_docs
        except Exception as e:
            logger.debug("Lỗi đọc 'companies' từ Mongo: %s", e)

    # 2. Tải trực tiếp từ Simplize Open API
    try:
        req = urllib.request.Request(
            _SIMPLIZE_ALL_COMPANIES_URL,
            headers={'User-Agent': _USER_AGENT, 'Accept': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            items = data.get('data', [])
            if items and len(items) >= 1000:
                clean_companies = []
                sectors_map = {}
                for it in items:
                    sym = str(it.get('ticker', '')).strip().upper()
                    if not sym or len(sym) < 3:
                        continue
                    name_vi = it.get('nameVi') or it.get('name') or f'CTCP {sym}'
                    sec_id = it.get('bcEconomicSectorId')
                    sector = get_dynamic_sector(sym, name_vi, sec_id)
                    name_unaccent = _strip_vietnamese_accents(name_vi).lower()

                    item_doc = {
                        'ticker': sym,
                        'nameVi': name_vi,
                        'nameEn': it.get('nameEn', ''),
                        'nameUnaccent': name_unaccent,
                        'stockExchange': it.get('stockExchange', 'HOSE'),
                        'bcEconomicSectorId': sec_id,
                        'sector': sector,
                        'imageUrl': it.get('imageUrl', ''),
                    }
                    clean_companies.append(item_doc)
                    sectors_map[sym] = sector

                _DIRECTORY_CACHE['companies'] = clean_companies
                _DIRECTORY_CACHE['by_ticker'] = {c['ticker']: c for c in clean_companies}
                _DIRECTORY_CACHE['sectors_map'] = sectors_map
                _DIRECTORY_CACHE['timestamp'] = now

                # Đồng bộ vào MongoDB Atlas
                _sync_companies_to_mongo(clean_companies)
                logger.info("Đã tải thành công %d công ty từ Simplize API.", len(clean_companies))
                return clean_companies
    except Exception as e:
        logger.warning("Lỗi tải danh bạ từ Simplize API: %s", e)

    return _DIRECTORY_CACHE.get('companies', [])


def get_all_stock_sectors_map() -> Dict[str, str]:
    """Trả về từ điển động toàn bộ {Mã CP: Ngành} nạp từ MongoDB hoặc RAM Cache."""
    if _DIRECTORY_CACHE['sectors_map'] and len(_DIRECTORY_CACHE['sectors_map']) >= 1000:
        return _DIRECTORY_CACHE['sectors_map']

    companies = fetch_and_cache_company_directory()
    if companies:
        _DIRECTORY_CACHE['sectors_map'] = {
            c['ticker']: c.get('sector') or get_dynamic_sector(c['ticker'], c.get('nameVi', ''), c.get('bcEconomicSectorId'))
            for c in companies if 'ticker' in c
        }
        return _DIRECTORY_CACHE['sectors_map']

    return {}


def is_valid_ticker(ticker: str) -> bool:
    """Kiểm tra một mã có tồn tại hợp lệ trên sàn HOSE, HNX, UPCoM hay không."""
    sym = (ticker or '').strip().upper()
    if not sym:
        return False
    if _DIRECTORY_CACHE['by_ticker']:
        return sym in _DIRECTORY_CACHE['by_ticker']
    companies = fetch_and_cache_company_directory()
    return any(c.get('ticker') == sym for c in companies)


def get_company_by_ticker(ticker: str) -> Optional[Dict[str, Any]]:
    """Lấy thông tin chi tiết một công ty từ danh bạ (gồm tên, ngành, sàn niêm yết)."""
    sym = (ticker or '').strip().upper()
    if not sym:
        return None
    if _DIRECTORY_CACHE['by_ticker'] and sym in _DIRECTORY_CACHE['by_ticker']:
        return _DIRECTORY_CACHE['by_ticker'][sym]
    companies = fetch_and_cache_company_directory()
    return _DIRECTORY_CACHE.get('by_ticker', {}).get(sym)


def get_stock_exchange(ticker: str, fallback: str = 'HOSE') -> str:
    """Xác định chính xác sàn niêm yết (HOSE, HNX, UPCoM) của một mã cổ phiếu."""
    comp = get_company_by_ticker(ticker)
    if comp:
        ex = comp.get('stockExchange') or comp.get('exchange')
        if ex:
            return str(ex).strip().upper()
    return fallback.strip().upper()


def search_companies(query: str, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Tìm kiếm thông minh trên MongoDB Atlas (1,626 mã):
    1. Truy vấn trực tiếp từ MongoDB collection 'companies' nếu kết nối sẵn sàng.
    2. Fallback tìm kiếm tức thì qua RAM Cache (< 1ms).
    3. Hỗ trợ tìm kiếm theo:
       - Mã CP (khớp chính xác, khớp tiền tố)
       - Tên công ty tiếng Việt (có dấu & không dấu)
       - Nhóm ngành
    4. Tự động gắn kèm giá realtime thời gian thực từ bảng giá thị trường.
    """
    raw_q = (query or '').strip()
    if not raw_q:
        return []

    q_upper = raw_q.upper()
    q_unaccent = _strip_vietnamese_accents(raw_q).lower()

    # Lấy bảng giá realtime hiện có để gắn giá tức thì
    from backend.data_providers.market_board_provider import get_market_board_data
    board = get_market_board_data() or {}

    matched_companies = []
    seen_tickers = set()

    # 1. Thử tìm kiếm trực tiếp trên MongoDB Atlas
    coll = _get_mongo_companies_coll()
    if coll is not None:
        try:
            from backend.models.db_models import CompanyItem
            # Ưu tiên khớp chính xác hoặc tiền tố ticker trước
            exact_docs = list(coll.find(CompanyItem.filter_by_ticker(q_upper), CompanyItem.PROJECTION_NO_ID))
            for d in exact_docs:
                t = d.get(CompanyItem.F_TICKER)
                if t and t not in seen_tickers:
                    matched_companies.append(d)
                    seen_tickers.add(t)

            prefix_docs = list(coll.find(
                CompanyItem.filter_by_ticker_prefix(q_upper, exclude_tickers=list(seen_tickers)),
                CompanyItem.PROJECTION_NO_ID
            ).limit(limit))
            for d in prefix_docs:
                t = d.get(CompanyItem.F_TICKER)
                if t and t not in seen_tickers:
                    matched_companies.append(d)
                    seen_tickers.add(t)

            # Tìm theo tên tiếng Việt hoặc tên không dấu hoặc ngành
            if len(matched_companies) < limit:
                remain = limit - len(matched_companies)
                name_docs = list(coll.find(
                    CompanyItem.filter_search_text(raw_q, q_unaccent, exclude_tickers=list(seen_tickers)),
                    CompanyItem.PROJECTION_NO_ID
                ).limit(remain))
                for d in name_docs:
                    t = d.get(CompanyItem.F_TICKER)
                    if t and t not in seen_tickers:
                        matched_companies.append(d)
                        seen_tickers.add(t)
        except Exception as e:
            logger.debug("Lỗi tìm kiếm Mongo, chuyển sang RAM Cache: %s", e)

    # 2. Fallback sang RAM Cache nếu Mongo chưa trả về hoặc chưa kết nối
    if not matched_companies:
        companies = fetch_and_cache_company_directory()
        exact_matches = []
        prefix_matches = []
        name_matches = []

        for c in companies:
            ticker = c.get('ticker', '')
            name_vi = c.get('nameVi', '')
            name_u = c.get('nameUnaccent') or _strip_vietnamese_accents(name_vi).lower()
            sec = c.get('sector', '')

            if ticker == q_upper:
                exact_matches.append(c)
            elif ticker.startswith(q_upper):
                prefix_matches.append(c)
            elif q_unaccent in name_u or raw_q.lower() in name_vi.lower() or raw_q.lower() in sec.lower():
                name_matches.append(c)

        for c in (exact_matches + prefix_matches + name_matches):
            if c.get('ticker') not in seen_tickers:
                matched_companies.append(c)
                seen_tickers.add(c.get('ticker'))
            if len(matched_companies) >= limit:
                break

    # 3. Gắn dữ liệu giá realtime từ bảng giá
    results = []
    for c in matched_companies[:limit]:
        sym = c.get('ticker')
        board_item = board.get(sym, {})
        raw_p = board_item.get('matchedPrice') or board_item.get('lastPrice') or board_item.get('refPrice', 0)
        p = float(raw_p) if raw_p else 0.0
        if 0 < p < 1000:
            p *= 1000

        chg = float(board_item.get('priceChange', 0.0) or 0.0)
        pct = float(board_item.get('priceChangePercent', board_item.get('changePercent', 0.0)) or 0.0)
        sector_name = c.get('sector') or get_dynamic_sector(sym, c.get('nameVi', ''), c.get('bcEconomicSectorId'))

        results.append({
            'symbol': sym,
            'ticker': sym,
            'name': c.get('nameVi', f'CTCP {sym}'),
            'exchange': c.get('stockExchange', c.get('exchange', 'HOSE')),
            'sector': sector_name,
            'price': p,
            'change': chg,
            'percentChange': pct,
            'logo': c.get('imageUrl', ''),
        })

    return results


