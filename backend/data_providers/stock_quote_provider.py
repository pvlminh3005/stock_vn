"""
Stock RT - Unified Stock Quote Provider
Hàm định giá và chuẩn hóa thị giá realtime dùng chung cho toàn bộ hệ thống:
Đảm bảo tab 'Tra cứu 1 mã' (Stock Detail) và tab 'Sổ lệnh' (Portfolio Tracker)
luôn đồng nhất 100% về: current_price, ref_price, change_pct và sàn niêm yết (exchange).
"""

import time
import copy
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from backend.constants.config import DAILY_HISTORY_DAYS
from backend.utils.time_utils import vn_date, VN_UTC_OFFSET_SEC
from backend.utils.ohlc_helpers import merge_live_candle_to_chart_data
from backend.data_providers.market_board_provider import get_market_board_data
from backend.data_providers.entrade_provider import fetch_chart_data, fetch_intraday_snapshot
from backend.data_providers.company_directory_provider import get_company_by_ticker, get_stock_exchange

logger = logging.getLogger('stock_quote_provider')

# Bộ nhớ đệm RAM định giá tức thì (TTL: 15s trong phiên, 300s ngoài phiên/cuối tuần)
# Bảo vệ 100% chống nghẽn và chống bị Rate Limit / Block IP từ Entrade API khi danh mục có nhiều mã
_QUOTE_CACHE: Dict[str, Dict[str, Any]] = {}
_QUOTE_TTL_MARKET_SEC = 15
_QUOTE_TTL_OFF_MARKET_SEC = 300


def _is_market_session_open() -> bool:
    """Kiểm tra thị trường có đang trong phiên giao dịch (Thứ 2 - 6, 09:00 - 15:00 GMT+7) hay không."""
    now_vn = datetime.fromtimestamp(time.time() + VN_UTC_OFFSET_SEC - time.timezone)
    if now_vn.weekday() >= 5:  # Thứ 7 hoặc CN
        return False
    if 9 <= now_vn.hour < 15:
        return True
    return False


def resolve_stock_realtime_quote(
    ticker: str,
    board_data: Optional[Dict[str, Any]] = None,
    days: int = DAILY_HISTORY_DAYS,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Xác định báo giá realtime chuẩn xác và đồng nhất cho 1 mã cổ phiếu:
    1. Kiểm tra RAM Cache (15s trong phiên, 5 phút ngoài phiên) để triệt tiêu tải lặp lại.
    2. Kiểm tra bảng giá SSI/Entrade Market Board.
    3. Fallback tự động sang Entrade Intraday Snapshot nếu mã thuộc HNX/UPCoM hoặc ngoài bảng chính.
    4. Tra cứu sàn niêm yết chính thức (HOSE, HNX, UPCoM) từ danh bạ 1,626 mã cổ phiếu.
    5. Đối chiếu nến ngày 1D (Entrade) để xác định chuẩn xác ref_price (tham chiếu) và current_price (thị giá).
    """
    sym = (ticker or '').strip().upper()
    if not sym:
        raise ValueError("Mã cổ phiếu không hợp lệ")

    now = time.time()
    ttl = _QUOTE_TTL_MARKET_SEC if _is_market_session_open() else _QUOTE_TTL_OFF_MARKET_SEC
    cached = _QUOTE_CACHE.get(sym)
    if not force_refresh and cached and (now - cached['ts'] < ttl):
        return copy.deepcopy(cached['data'])

    if board_data is None:
        board_data = get_market_board_data() or {}

    board_item = dict(board_data.get(sym, {}))

    # Nếu bảng giá rỗng hoặc chưa khớp lệnh -> Tự động Fallback sang Entrade Intraday Live 1-min
    if not board_item or float(board_item.get('matchedPrice') or 0) <= 0:
        entrade_snap = fetch_intraday_snapshot(sym)
        if entrade_snap and float(entrade_snap.get('matchedPrice') or 0) > 0:
            board_item = entrade_snap

    # Tra cứu sàn và tên công ty chuẩn từ danh bạ
    comp = get_company_by_ticker(sym)
    exchange = board_item.get('exchange')
    if not exchange and comp:
        exchange = comp.get('stockExchange') or comp.get('exchange')
    if not exchange:
        exchange = get_stock_exchange(sym)
    exchange = (exchange or 'HOSE').upper()
    board_item['exchange'] = exchange

    company_name = board_item.get('companyNameVi') or board_item.get('clientName')
    if not company_name and comp:
        company_name = comp.get('nameVi')
    company_name = company_name or f'Cổ phiếu {sym}'

    # Toàn bộ nến ngày lịch sử và nến live
    chart_data = fetch_chart_data(sym, days=days, resolution='1D', market_item=board_item)
    chart_data = merge_live_candle_to_chart_data(chart_data, board_item, resolution='1D')

    t_list = chart_data.get('t', [])
    h_list = chart_data.get('h', [])
    l_list = chart_data.get('l', [])
    c_list = chart_data.get('c', [])
    v_list = chart_data.get('v', [])

    scale = 1000 if (c_list and c_list[-1] < 1000) else 1
    now_vn = time.gmtime(time.time() + VN_UTC_OFFSET_SEC)
    today_str = time.strftime('%Y-%m-%d', now_vn)
    last_candle_date = vn_date(t_list[-1]) if t_list else None

    # Xác định giá tham chiếu và nến đóng cửa trước đó:
    # Nếu nến cuối cùng trong t_list trùng ngày hôm nay (sau khi merge nến live hoặc Entrade đã chốt phiên):
    # thì Tham chiếu là nến c_list[-2]. Nếu chưa có nến hôm nay: Tham chiếu là c_list[-1].
    if last_candle_date == today_str and len(c_list) > 1:
        ref_from_chart = float(c_list[-2] * scale)
        latest_c = float(c_list[-1] * scale)
    elif c_list:
        ref_from_chart = float(c_list[-1] * scale)
        latest_c = ref_from_chart
    else:
        ref_from_chart = 0.0
        latest_c = 0.0

    # Xác định tham chiếu chuẩn:
    # Ưu tiên refPrice của board_item nếu hợp lệ (> 0) và khác matchedPrice;
    # nếu board_item có refPrice == matchedPrice hoặc <= 0, lấy từ nến ngày ref_from_chart
    board_ref = float(board_item.get('refPrice') or 0)
    board_matched = float(board_item.get('matchedPrice') or 0)
    if board_ref > 0 and (board_matched <= 0 or abs(board_ref - board_matched) > 1e-4):
        ref_price = board_ref
    else:
        ref_price = ref_from_chart if ref_from_chart > 0 else (board_matched if board_matched > 0 else latest_c)

    band = 0.07 if exchange == 'HOSE' else (0.10 if exchange == 'HNX' else 0.15)

    # Dữ liệu realtime từ Entrade Market Board nếu có phiên đang mở
    if board_item and board_matched > 0:
        current_price = board_matched
        price_change = round(current_price - ref_price, 2)
        pct_change = round((price_change / ref_price) * 100, 2) if ref_price > 0 else 0.0
        open_price = float(board_item.get('openPrice') or current_price)
        ceiling = board_item.get('ceiling') or round(ref_price * (1 + band))
        floor = board_item.get('floor') or round(ref_price * (1 - band))
        highest_price = board_item.get('highest') or (h_list[-1] * scale if h_list else current_price)
        lowest_price = board_item.get('lowest') or (l_list[-1] * scale if l_list else current_price)
        total_vol = board_item.get('stockVol', v_list[-1] if v_list else 0)
        foreign_net = board_item.get('buyForeignQtty', 0) - board_item.get('sellForeignQtty', 0)
    elif board_item and board_ref > 0:
        ref_price = board_ref
        current_price = board_matched if board_matched > 0 else ref_price
        price_change = round(current_price - ref_price, 2)
        pct_change = round((price_change / ref_price) * 100, 2) if ref_price > 0 else 0.0
        open_price = float(board_item.get('openPrice') or current_price)
        ceiling = board_item.get('ceiling') or round(ref_price * (1 + band))
        floor = board_item.get('floor') or round(ref_price * (1 - band))
        highest_price = board_item.get('highest') or (h_list[-1] * scale if h_list else current_price)
        lowest_price = board_item.get('lowest') or (l_list[-1] * scale if l_list else current_price)
        total_vol = board_item.get('stockVol', v_list[-1] if v_list else 0)
        foreign_net = board_item.get('buyForeignQtty', 0) - board_item.get('sellForeignQtty', 0)
    else:
        current_price = latest_c
        price_change = round(latest_c - ref_price, 2)
        pct_change = round((price_change / ref_price) * 100, 2) if ref_price > 0 else 0.0
        open_price = current_price
        ceiling = round(ref_price * (1 + band))
        floor = round(ref_price * (1 - band))
        highest_price = (h_list[-1] * scale) if h_list else current_price
        lowest_price = (l_list[-1] * scale) if l_list else current_price
        total_vol = v_list[-1] if v_list else 0
        foreign_net = 0

    if not highest_price or highest_price <= 0:
        highest_price = current_price
    if not lowest_price or lowest_price <= 0:
        lowest_price = current_price

    res = {
        'ticker': sym,
        'symbol': sym,
        'current_price': float(current_price),
        'ref_price': float(ref_price),
        'price_change': float(price_change),
        'pct_change': float(pct_change),
        'change_pct': float(pct_change),
        'open_price': float(open_price),
        'highest_price': float(highest_price),
        'lowest_price': float(lowest_price),
        'ceiling': float(ceiling),
        'floor': float(floor),
        'total_vol': int(total_vol),
        'foreign_net': int(foreign_net),
        'company_name': company_name,
        'exchange': exchange,
        'band': band,
        'board_item': board_item,
        'chart_data': chart_data,
        'scale': scale,
    }

    _QUOTE_CACHE[sym] = {'ts': now, 'data': copy.deepcopy(res)}
    return res

