"""
Stock RT - User Portfolio Controller
Quản lý sổ lệnh cá nhân, tính toán danh mục, P&L thời gian thực từ bảng giá SSI,
NAV còn lại, và quản lý các giao dịch Mua/Bán.
"""

import logging
from typing import Dict, Any, List
from datetime import datetime
from backend.db.portfolio_db import (
    add_trade,
    get_all_trades,
    delete_trade,
    reset_all_trades,
    save_setting,
    get_setting,
)
from backend.data_providers.ssi_provider import get_ssi_board_data

logger = logging.getLogger('user_portfolio_controller')


def _format_price(val: Any) -> float:
    """Chuẩn hóa giá về đơn vị Đồng (VNĐ). Nếu người dùng nhập 27.5 thì tự nhân 1000 thành 27500."""
    try:
        p = float(val)
        if 0 < p < 1000:
            return round(p * 1000, 2)
        return round(p, 2)
    except (ValueError, TypeError):
        return 0.0


def handle_get_portfolio() -> Dict[str, Any]:
    """
    Trả về toàn bộ sổ lệnh cá nhân kèm theo:
    - Bảng giá thị trường realtime (SSI)
    - P&L từng mã (đ và %)
    - Tổng NAV, Tổng giải ngân, Sức mua/NAV còn lại, Tổng Lời/Lỗ danh mục.
    """
    trades = get_all_trades()
    total_nav_str = get_setting('total_nav', '0')
    try:
        total_nav = float(total_nav_str)
    except (ValueError, TypeError):
        total_nav = 0.0

    # Lấy bảng giá realtime
    board_data = get_ssi_board_data() or {}

    enriched_trades = []
    total_buy_cost = 0.0      # Tổng vốn ban đầu của các mã đang giữ
    current_market_val = 0.0  # Tổng giá trị thị trường hiện tại của các mã đang giữ
    total_sell_val = 0.0      # Tiền thu về từ các lệnh Bán

    for t in trades:
        sym = t.get('symbol', '').strip().upper()
        order_type = t.get('order_type', 'BUY').upper()
        vol = int(t.get('volume', 0))
        entry_price = float(t.get('price', 0))

        # Thông tin realtime từ sàn
        board_item = board_data.get(sym, {})
        # matchedPrice trên SSI thường ở đơn vị nghìn đồng (vd 28.5) hoặc đồng tùy endpoint
        raw_matched = board_item.get('matchedPrice') or board_item.get('lastPrice') or board_item.get('refPrice') or 0.0
        current_price = _format_price(raw_matched)
        if current_price == 0.0:
            # Fallback nếu sàn ngoài giờ chưa có giá matched
            current_price = entry_price

        ref_price = _format_price(board_item.get('refPrice', 0))
        change_pct = float(board_item.get('priceChangePercent') or board_item.get('changePercent') or 0.0)

        # Tính toán giá trị và P&L
        invested_amount = vol * entry_price
        current_amount = vol * current_price

        pnl_val = 0.0
        pnl_pct = 0.0

        if order_type == 'BUY':
            pnl_val = current_amount - invested_amount
            pnl_pct = round((pnl_val / invested_amount * 100), 2) if invested_amount > 0 else 0.0
            total_buy_cost += invested_amount
            current_market_val += current_amount
        else:
            # Lệnh bán: ghi nhận số tiền thu về
            total_sell_val += invested_amount
            pnl_val = 0.0
            pnl_pct = 0.0

        enriched_trades.append({
            'id': t.get('id'),
            'symbol': sym,
            'order_type': order_type,
            'volume': vol,
            'price': entry_price,
            'current_price': current_price,
            'ref_price': ref_price,
            'change_pct': change_pct,
            'invested_amount': invested_amount,
            'current_amount': current_amount,
            'pnl_val': round(pnl_val, 2),
            'pnl_pct': pnl_pct,
            'trade_date': t.get('trade_date', ''),
            'note': t.get('note', ''),
            'status': t.get('status', 'HOLDING'),
            'exchange': board_item.get('exchange', 'HOSE'),
        })

    # Tổng kết Lời/Lỗ chưa thực hiện (Unrealized P&L) cho danh mục đang giữ
    unrealized_pnl = current_market_val - total_buy_cost
    unrealized_pnl_pct = round((unrealized_pnl / total_buy_cost * 100), 2) if total_buy_cost > 0 else 0.0

    # NAV còn lại (Sức mua tiền mặt): Tổng NAV - Vốn đang giữ + Tiền bán đã thu
    available_nav = (total_nav - total_buy_cost + total_sell_val) if total_nav > 0 else 0.0

    return {
        'success': True,
        'summary': {
            'total_nav': total_nav,
            'total_buy_cost': round(total_buy_cost, 2),
            'current_market_val': round(current_market_val, 2),
            'unrealized_pnl': round(unrealized_pnl, 2),
            'unrealized_pnl_pct': unrealized_pnl_pct,
            'available_nav': round(available_nav, 2),
            'holdings_count': len([t for t in enriched_trades if t['order_type'] == 'BUY']),
            'closed_count': len([t for t in enriched_trades if t['order_type'] == 'SELL']),
        },
        'trades': enriched_trades,
    }


def handle_add_trade(data: Dict[str, Any]) -> Dict[str, Any]:
    """Thêm giao dịch mua/bán mới."""
    sym = data.get('symbol', '').strip().upper()
    if not sym:
        return {'success': False, 'error': 'Vui lòng nhập mã chứng khoán'}

    try:
        vol = int(data.get('volume', 0))
        if vol <= 0:
            return {'success': False, 'error': 'Khối lượng phải lớn hơn 0'}
    except (ValueError, TypeError):
        return {'success': False, 'error': 'Khối lượng không hợp lệ'}

    price = _format_price(data.get('price', 0))
    if price <= 0:
        return {'success': False, 'error': 'Giá mua/bán phải lớn hơn 0'}

    order_type = data.get('order_type', 'BUY').strip().upper()
    if order_type not in ['BUY', 'SELL']:
        order_type = 'BUY'

    trade_date = data.get('trade_date', '').strip()
    if not trade_date:
        trade_date = datetime.now().strftime('%Y-%m-%d')

    trade_record = {
        'symbol': sym,
        'order_type': order_type,
        'volume': vol,
        'price': price,
        'trade_date': trade_date,
        'note': data.get('note', '').strip(),
        'status': 'HOLDING' if order_type == 'BUY' else 'CLOSED',
    }

    inserted_id = add_trade(trade_record)
    if inserted_id:
        return {'success': True, 'id': inserted_id, 'message': f'Đã thêm lệnh {order_type} mã {sym} thành công'}
    return {'success': False, 'error': 'Không thể ghi nhận giao dịch vào cơ sở dữ liệu'}


def handle_delete_trade(trade_id: str) -> Dict[str, Any]:
    """Xóa một giao dịch khỏi sổ lệnh."""
    if not trade_id:
        return {'success': False, 'error': 'Thiếu ID giao dịch'}
    ok = delete_trade(trade_id)
    if ok:
        return {'success': True, 'message': 'Đã xóa giao dịch thành công'}
    return {'success': False, 'error': 'Không tìm thấy hoặc không thể xóa giao dịch này'}


def handle_reset_portfolio() -> Dict[str, Any]:
    """Xóa trắng toàn bộ giao dịch."""
    ok = reset_all_trades()
    if ok:
        return {'success': True, 'message': 'Đã xóa toàn bộ sổ lệnh'}
    return {'success': False, 'error': 'Không thể thực hiện reset danh mục'}


def handle_save_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    """Lưu cài đặt tổng NAV."""
    nav_val = data.get('total_nav')
    if nav_val is not None:
        try:
            total_nav = float(nav_val)
            save_setting('total_nav', str(total_nav))
            return {'success': True, 'message': 'Đã lưu cấu hình Tổng NAV thành công', 'total_nav': total_nav}
        except (ValueError, TypeError):
            return {'success': False, 'error': 'Giá trị Tổng NAV không hợp lệ'}
    return {'success': False, 'error': 'Thiếu tham số cấu hình'}

