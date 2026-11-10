"""
Stock RT - User Portfolio Controller
Quản lý sổ lệnh cá nhân, tính toán danh mục chuẩn tài chính:
- Giá vốn bình quân gia quyền (VWAP) khi mua nhiều lần/nhiều mức giá khác nhau
- Lãi/lỗ đã chốt (Realized PnL) từ các lệnh bán chốt lời/cắt lỗ trước đó
- Lãi/lỗ thời gian thực chưa chốt (Unrealized PnL Realtime)
- Tổng hiệu quả trọn đời của vị thế (Total PnL = Realized + Unrealized)
- Tích hợp 100% Entrade Engine lấy giá trong phiên và giá chốt nến ngày (1D) sau 15:00.
"""

import logging
from typing import Dict, Any, Optional, Union
from datetime import datetime
from backend.models import (
    PortfolioTrade,
    PortfolioSetting,
    PortfolioSummary,
)
from backend.db.portfolio_db import (
    add_trade,
    get_all_trade_models,
    delete_trade,
    reset_all_trades,
    save_setting,
    get_setting,
)
from backend.data_providers.market_board_provider import get_market_board_data
from backend.data_providers.entrade_provider import fetch_chart_data, fetch_intraday_snapshot

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


def get_entrade_stock_quote(sym: str, board_data: Optional[Dict[str, Any]] = None, default_p: float = 0.0) -> Dict[str, Any]:
    """
    Lấy giá thời gian thực chuẩn xác 100% từ Entrade Engine:
    1. Trong phiên: Lấy từ bảng giá Entrade / Intraday Snapshot (nến 1 phút).
    2. Sau 15:00: Đối chiếu nến ngày 1D của Entrade để lấy giá đóng cửa chính thức sau phiên ATC.
    """
    if board_data is None:
        board_data = get_market_board_data() or {}

    b_item = board_data.get(sym, {})
    raw_matched = b_item.get('matchedPrice') or b_item.get('lastPrice') or b_item.get('refPrice') or 0.0
    cur_p = _format_price(raw_matched)
    ref_p = _format_price(b_item.get('refPrice', 0))
    pct = float(b_item.get('priceChangePercent') or b_item.get('changePercent') or 0.0)

    # Sau 15:00 hoặc khi giá bảng chưa có, lấy từ nến 1D Entrade để đảm bảo giá chốt hạ ATC (14.95)
    now = datetime.now()
    is_after_market = now.hour >= 15 or now.hour < 9 or now.weekday() >= 5
    if is_after_market or cur_p == 0.0:
        try:
            chart = fetch_chart_data(sym, days=5, resolution='1D')
            if chart and chart.get('c'):
                eod_close = _format_price(chart['c'][-1])
                if eod_close > 0:
                    cur_p = eod_close
                    if len(chart['c']) >= 2:
                        ref_p = _format_price(chart['c'][-2])
                        if ref_p > 0:
                            pct = round(((cur_p - ref_p) / ref_p * 100), 2)
        except Exception as e:
            logger.debug("Lỗi đọc nến 1D Entrade cho %s: %s", sym, e)

    if cur_p == 0.0:
        snap = fetch_intraday_snapshot(sym)
        if snap and snap.get('matchedPrice', 0) > 0:
            cur_p = float(snap['matchedPrice'])
            ref_p = float(snap.get('refPrice', cur_p))
            pct = float(snap.get('priceChangePercent', 0.0))
        else:
            cur_p = default_p

    return {
        'current_price': cur_p,
        'ref_price': ref_p,
        'change_pct': pct,
        'exchange': b_item.get('exchange', 'HOSE'),
    }


def handle_get_portfolio() -> Dict[str, Any]:
    """
    Trả về toàn bộ sổ lệnh cá nhân kèm theo:
    1. Danh sách gom nhóm vị thế (Holdings View): Bình quân giá vốn VWAP, Realized PnL, Unrealized PnL, Total PnL.
    2. Danh sách nhật ký chi tiết từng lệnh (Trades History View).
    3. Tổng kết tài chính toàn diện: Tổng NAV, Vốn giải ngân, Sức mua, Lãi chốt, Lãi chạy, Tổng lãi.
    """
    trades = get_all_trade_models()
    total_nav_str = get_setting(PortfolioSetting.KEY_TOTAL_NAV, '0')
    try:
        total_nav = float(total_nav_str)
    except (ValueError, TypeError):
        total_nav = 0.0

    board_data = get_market_board_data() or {}

    # 1. Xử lý nhật ký chi tiết từng lệnh (Enriched Trades)
    enriched_trades = []
    for t in trades:
        sym = t.symbol
        order_type = t.order_type
        vol = t.volume
        entry_price = t.price

        q = get_entrade_stock_quote(sym, board_data, entry_price)
        cur_p = q['current_price']
        ref_p = q['ref_price']
        chg_pct = q['change_pct']

        invested_amt = vol * entry_price
        cur_amt = vol * cur_p
        pnl_val = (cur_amt - invested_amt) if order_type == PortfolioTrade.ORDER_BUY else 0.0
        pnl_pct = round((pnl_val / invested_amt * 100), 2) if invested_amt > 0 else 0.0

        enriched_trades.append({
            'id': t.id,
            'symbol': sym,
            'order_type': order_type,
            'volume': vol,
            'price': entry_price,
            'current_price': cur_p,
            'ref_price': ref_p,
            'change_pct': chg_pct,
            'invested_amount': invested_amt,
            'current_amount': cur_amt,
            'pnl_val': round(pnl_val, 2),
            'pnl_pct': pnl_pct,
            'trade_date': t.trade_date,
            'note': t.note,
            'status': t.status,
            'exchange': q.get('exchange', 'HOSE'),
        })

    # 2. Gom nhóm vị thế theo mã (Consolidated Holdings Engine - VWAP + Realized + Unrealized)
    sorted_trades = sorted(trades, key=lambda x: (x.trade_date, str(x.id or '')))
    holdings_map = {}

    for t in sorted_trades:
        sym = t.symbol
        if not sym:
            continue
        order_type = t.order_type
        vol = t.volume
        price = t.price

        if sym not in holdings_map:
            holdings_map[sym] = {
                'symbol': sym,
                'holding_volume': 0,
                'total_cost': 0.0,
                'avg_price': 0.0,
                'realized_pnl': 0.0,
                'total_buy_vol': 0,
                'total_sell_vol': 0,
                'total_buy_val': 0.0,
                'total_sell_val': 0.0,
                'buy_trades_count': 0,
                'sell_trades_count': 0,
                'first_trade_date': t.trade_date,
                'last_trade_date': t.trade_date,
            }

        h = holdings_map[sym]
        h['last_trade_date'] = t.trade_date

        if order_type == PortfolioTrade.ORDER_BUY:
            new_vol = h['holding_volume'] + vol
            h['total_cost'] += (vol * price)
            h['avg_price'] = round(h['total_cost'] / new_vol, 2) if new_vol > 0 else 0.0
            h['holding_volume'] = new_vol
            h['total_buy_vol'] += vol
            h['total_buy_val'] += (vol * price)
            h['buy_trades_count'] += 1
        elif order_type == PortfolioTrade.ORDER_SELL:
            # Chốt lời/cắt lỗ cho số lượng bán theo giá vốn bình quân hiện tại
            sell_profit = vol * (price - h['avg_price'])
            h['realized_pnl'] += sell_profit
            h['holding_volume'] = max(0, h['holding_volume'] - vol)
            h['total_cost'] = h['holding_volume'] * h['avg_price']
            h['total_sell_vol'] += vol
            h['total_sell_val'] += (vol * price)
            h['sell_trades_count'] += 1

    # 3. Tính toán giá trị thị trường và PnL thời gian thực cho từng vị thế
    consolidated_holdings = []
    total_holding_cost = 0.0
    total_market_val = 0.0
    total_realized_pnl = 0.0

    from backend.domain.portfolio_bundler import get_stock_sector

    for sym, h in holdings_map.items():
        q = get_entrade_stock_quote(sym, board_data, h['avg_price'])
        cur_p = q['current_price']
        ref_p = q['ref_price']
        chg_pct = q['change_pct']

        holding_vol = h['holding_volume']
        avg_p = h['avg_price']
        total_cost = h['total_cost']

        cur_val = holding_vol * cur_p
        unrealized_pnl = (cur_val - total_cost) if holding_vol > 0 else 0.0
        unrealized_pnl_pct = round((unrealized_pnl / total_cost * 100), 2) if total_cost > 0 else 0.0

        realized_pnl = h['realized_pnl']
        total_pnl = realized_pnl + unrealized_pnl

        # Tỷ trọng danh mục (% NAV)
        weight_pct = round((cur_val / total_nav * 100), 1) if total_nav > 0 else 0.0

        if holding_vol > 0:
            total_holding_cost += total_cost
            total_market_val += cur_val
        total_realized_pnl += realized_pnl

        sector_name = get_stock_sector(sym)

        consolidated_holdings.append({
            'symbol': sym,
            'sector': sector_name,
            'exchange': q.get('exchange', 'HOSE'),
            'holding_volume': holding_vol,
            'avg_price': round(avg_p, 2),
            'current_price': cur_p,
            'ref_price': ref_p,
            'change_pct': chg_pct,
            'total_cost': round(total_cost, 2),
            'current_value': round(cur_val, 2),
            'unrealized_pnl': round(unrealized_pnl, 2),
            'unrealized_pnl_pct': unrealized_pnl_pct,
            'realized_pnl': round(realized_pnl, 2),
            'total_pnl': round(total_pnl, 2),
            'weight_pct': weight_pct,
            'status': 'HOLDING' if holding_vol > 0 else 'CLOSED',
            'buy_trades_count': h['buy_trades_count'],
            'sell_trades_count': h['sell_trades_count'],
            'first_trade_date': h['first_trade_date'],
            'last_trade_date': h['last_trade_date'],
        })

    # Sắp xếp: Ưu tiên mã đang giữ lên trước (theo giá trị thị trường giảm dần), mã đã đóng xuống dưới
    consolidated_holdings.sort(key=lambda x: (0 if x['holding_volume'] > 0 else 1, -x['current_value']))

    # Tổng kết toàn danh mục
    total_unrealized_pnl = total_market_val - total_holding_cost
    total_unrealized_pnl_pct = round((total_unrealized_pnl / total_holding_cost * 100), 2) if total_holding_cost > 0 else 0.0
    total_combined_pnl = total_realized_pnl + total_unrealized_pnl
    total_combined_pnl_pct = round((total_combined_pnl / total_nav * 100), 2) if total_nav > 0 else 0.0

    # Sức mua tiền mặt: Tổng NAV - Vốn đang giữ + Lãi đã chốt thu về
    available_nav = (total_nav - total_holding_cost + total_realized_pnl) if total_nav > 0 else 0.0

    summary_obj = PortfolioSummary(
        total_nav=total_nav,
        total_buy_cost=round(total_holding_cost, 2),
        current_market_val=round(total_market_val, 2),
        unrealized_pnl=round(total_unrealized_pnl, 2),
        unrealized_pnl_pct=total_unrealized_pnl_pct,
        realized_pnl=round(total_realized_pnl, 2),
        total_pnl=round(total_combined_pnl, 2),
        total_pnl_pct=total_combined_pnl_pct,
        available_nav=round(available_nav, 2),
        holdings_count=len([h for h in consolidated_holdings if h['holding_volume'] > 0]),
        closed_count=len([h for h in consolidated_holdings if h['holding_volume'] == 0]),
        total_trades_count=len(trades),
    )

    return {
        'success': True,
        'summary': summary_obj.to_dict(),
        'holdings': consolidated_holdings,
        'trades': enriched_trades,
    }


def handle_add_trade(data: Union[PortfolioTrade, Dict[str, Any]]) -> Dict[str, Any]:
    """Thêm giao dịch mua/bán mới thông qua PortfolioTrade Model."""
    if isinstance(data, PortfolioTrade):
        trade_obj = data
    else:
        trade_obj, err = PortfolioTrade.from_request(data)
        if err:
            return {'success': False, 'error': err}

    inserted_id = add_trade(trade_obj)
    if inserted_id:
        return {
            'success': True,
            'id': inserted_id,
            'message': f'Đã thêm lệnh {trade_obj.order_type} mã {trade_obj.symbol} thành công'
        }
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


def handle_save_settings(data: Union[PortfolioSetting, Dict[str, Any]]) -> Dict[str, Any]:
    """Lưu cài đặt tổng NAV thông qua PortfolioSetting Model."""
    if isinstance(data, PortfolioSetting):
        setting_obj = data
    else:
        setting_obj, err = PortfolioSetting.from_request(data)
        if err:
            return {'success': False, 'error': err}

    ok = save_setting(setting_obj.key, setting_obj.value)
    if ok:
        try:
            val_num = float(setting_obj.value)
        except (ValueError, TypeError):
            val_num = 0.0
        return {
            'success': True,
            'message': 'Đã lưu cấu hình Tổng NAV thành công',
            'total_nav': val_num
        }
    return {'success': False, 'error': 'Không thể lưu cài đặt vào cơ sở dữ liệu'}

