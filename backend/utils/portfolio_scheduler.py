"""
Stock RT - Portfolio Realtime Scanner & Telegram Alert Scheduler
Chức năng:
1. Quét định kỳ 15 phút/lần các mã có vị thế MUA (HOLDING) trong phiên giao dịch.
2. Kiểm tra tín hiệu: Chạm Cắt Lỗ (Stoploss/S1), Đạt Mục Tiêu Chốt Lời (Target/R1).
3. Cơ chế Chống Spam Lặp Lại (Deduplication / State Transition): Chỉ gửi 1 lần khi vi phạm.
4. Xử lý Tín Hiệu Nhấp Nháy Xanh/Hồng: Trong phiên không gửi riêng lẻ, gom lại gửi 1 bản tin
   tổng kết duy nhất vào đúng 14:30 các ngày Thứ 2 đến Thứ 6 (trừ T7, CN).
"""

import os
import time
import logging
from datetime import datetime, timezone, timedelta
import threading

from backend.db.portfolio_db import (
    get_active_holding_symbols,
    get_all_trade_models,
    get_alert_state,
    save_alert_state,
    is_alert_already_sent,
    record_alert_sent,
)
from backend.data_providers.market_board_provider import get_market_board_data
from backend.controllers.stock_controller import handle_stock_detail
from backend.utils.telegram_bot import send_telegram_message, get_public_url

logger = logging.getLogger('portfolio_scheduler')

# Múi giờ Việt Nam (UTC+7) chuẩn hoá cho môi trường Cloud (Render/Docker)
VN_TZ = timezone(timedelta(hours=7))


def get_vn_now() -> datetime:
    """Lấy thời gian hiện tại chuẩn theo múi giờ Việt Nam (UTC+7)."""
    return datetime.now(VN_TZ)


_last_scan_ts = 0
_last_digest_date = ""  # Ngày đã gửi bản tin 14h30 (YYYY-MM-DD)


def is_trading_day(dt: datetime) -> bool:
    """Kiểm tra có phải ngày giao dịch (Thứ 2 đến Thứ 6) không."""
    return dt.weekday() < 5


def is_market_hours(dt: datetime) -> bool:
    """Kiểm tra thời gian trong phiên giao dịch chứng khoán Việt Nam (09:00 - 11:30 & 13:00 - 15:00)."""
    if not is_trading_day(dt):
        return False
    h = dt.hour
    m = dt.minute
    total_min = h * 60 + m
    # Phiên sáng: 09:00 -> 11:30 (540 -> 690)
    # Phiên chiều: 13:00 -> 15:00 (780 -> 900)
    in_morning = 540 <= total_min <= 690
    in_afternoon = 780 <= total_min <= 900
    return in_morning or in_afternoon


def get_t_plus_status(trade_date_str: str) -> str:
    """Tính toán trạng thái T+ (T+0, T+1, T+2 Chiều về, T+3 Khả dụng) theo ngày giao dịch."""
    if not trade_date_str:
        return ""
    try:
        t_date = datetime.strptime(trade_date_str[:10], '%Y-%m-%d').date()
        today = get_vn_now().date()
        if today < t_date:
            return ""
        trading_days = 0
        curr = t_date
        while curr < today:
            curr += timedelta(days=1)
            if curr.weekday() < 5:
                trading_days += 1
        if trading_days == 0:
            return "T+0 (Vừa mua hôm nay)"
        elif trading_days == 1:
            return "T+1 (Chưa về TK)"
        elif trading_days == 2:
            return "T+2 (Chiều nay về TK)"
        else:
            return f"T+{trading_days} (Sẵn sàng bán)"
    except Exception:
        return ""


def format_portfolio_alert(symbol: str, alert_type: str, detail: dict) -> tuple:
    """Định dạng tin nhắn cảnh báo Telegram cho vị thế trong sổ lệnh."""
    base_url = get_public_url()
    access_pin = os.environ.get('APP_ACCESS_PIN', '').strip()
    auth_param = f"&auth={access_pin}" if access_pin else ""
    deep_link = f"{base_url}/?ticker={symbol}{auth_param}"

    price = detail.get('price', 0)
    change_pct = detail.get('change_pct', 0.0)
    sign = '+' if change_pct >= 0 else ''

    avg_p = detail.get('avg_price', 0)
    pnl_pct = detail.get('pnl_pct', 0.0)
    pnl_line = f"📊 <b>Giá vốn TB:</b> {avg_p:,.0f} đ (Lỗ tạm tính: <b>{pnl_pct:.2f}%</b>)\n" if avg_p > 0 and pnl_pct < 0 else (f"📊 <b>Giá vốn TB:</b> {avg_p:,.0f} đ (Lãi tạm tính: <b>+{pnl_pct:.2f}%</b>)\n" if avg_p > 0 else "")

    trade_date = detail.get('trade_date', '')
    signal_date = detail.get('signal_date', '')
    holding_bars = detail.get('holding_bars')
    t_status = get_t_plus_status(trade_date)

    date_line = ""
    if trade_date:
        t_suffix = f" (<b>{t_status}</b>)" if t_status else ""
        date_line = f"📅 <b>Ngày vào lệnh:</b> {trade_date}{t_suffix}\n"
    elif signal_date:
        bar_str = f" ({holding_bars} phiên trước)" if holding_bars else ""
        date_line = f"📅 <b>Ngày phát lệnh kỹ thuật:</b> {signal_date}{bar_str}\n"

    if alert_type == 'STOPLOSS_TRIGGERED':
        stop_val = detail.get('stop_loss', 0)
        downside_pct = round(((stop_val - price) / price * 100), 2) if price > 0 and stop_val > 0 else 0.0
        msg = (
            f"🚨 <b>CẢNH BÁO DANH MỤC: {symbol} CHẠM NGƯỠNG CẮT LỖ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Thị giá:</b> {price:,.0f} đ ({sign}{change_pct:.2f}%)\n"
            f"{pnl_line}"
            f"{date_line}"
            f"🛡️ <b>Mốc hỗ trợ S1 / Stoploss:</b> {stop_val:,.0f} đ ({downside_pct:.1f}%)\n\n"
            f"⚠️ <i>Giá cổ phiếu đã vi phạm hoặc xuyên thủng ngưỡng phòng thủ ban đầu. "
            f"Hãy xem xét hạ tỷ trọng hoặc đóng vị thế để bảo toàn vốn.</i>\n"
        )
    elif alert_type == 'NEAR_STOPLOSS':
        stop_val = detail.get('stop_loss', 0)
        dist_to_sl = detail.get('dist_to_sl', 0.0)

        msg = (
            f"⚠️ <b>CẢNH BÁO SỚM DANH MỤC: {symbol} TIỆM CẬN DẢI DỪNG LỖ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Thị giá:</b> {price:,.0f} đ ({sign}{change_pct:.2f}%)\n"
            f"{pnl_line}"
            f"{date_line}"
            f"🛡️ <b>Mốc Dừng Lỗ (SL/S1):</b> {stop_val:,.0f} đ (Cách SL: <b>chỉ còn {dist_to_sl:.1f}%</b>)\n\n"
            f"👀 <i>Giá cổ phiếu đang áp sát ngưỡng phòng thủ ban đầu (cách SL < 2% hoặc lỗ > 5%). "
            f"Hãy chuẩn bị sẵn kịch bản và theo dõi sát lực cầu quanh khung 14:15 - 14:30 (ATC). "
            f"Nếu không có dòng tiền đỡ giá và đóng nến vi phạm, chủ động kích hoạt lệnh SL bảo toàn vốn.</i>\n"
        )
    elif alert_type == 'TARGET_TRIGGERED':
        r1_val = detail.get('target1', 0)
        upside_pct = round(((r1_val - price) / price * 100), 2) if price > 0 and r1_val > 0 else 0.0
        msg = (
            f"🎯 <b>CẢNH BÁO DANH MỤC: {symbol} ĐẠT MỤC TIÊU CHỐT LỜI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Thị giá:</b> {price:,.0f} đ ({sign}{change_pct:.2f}%)\n"
            f"{pnl_line}"
            f"{date_line}"
            f"🏆 <b>Mục tiêu chốt lời R1:</b> {r1_val:,.0f} đ (+{upside_pct:.1f}%)\n\n"
            f"🎉 <i>Cổ phiếu đã chạm vùng kháng cự chốt lời kỳ vọng. "
            f"Khuyến nghị hiện thực hóa lợi nhuận từng phần hoặc nâng mốc chặn lãi (Trailing Stop).</i>\n"
        )
    else:
        msg = f"🔔 <b>THÔNG BÁO DANH MỤC: {symbol}</b>\nThị giá: {price:,.0f} đ\n"

    buttons = [
        {'text': f'📊 Mở Chi Tiết {symbol}', 'url': deep_link},
        {'text': '💼 Mở Sổ Lệnh Danh Mục', 'url': f"{base_url}/?mode=portfolio{auth_param}"}
    ]
    return msg, buttons


def scan_portfolio_alerts():
    """Quét 15 phút/lần các mã Mua đang nắm giữ."""
    symbols = get_active_holding_symbols()
    if not symbols:
        return

    logger.info("Bắt đầu quét cảnh báo danh mục cho %d mã: %s", len(symbols), symbols)
    board_data = get_market_board_data() or {}
    now_ts = int(time.time())

    # Tính toán giá vốn bình quân VWAP từ sổ lệnh
    trades = get_all_trade_models()
    holdings_vwap = {}
    for t in sorted(trades, key=lambda x: (x.trade_date, str(x.id or ''))):
        sym_code = (t.symbol or '').strip().upper()
        if not sym_code:
            continue
        if sym_code not in holdings_vwap:
            holdings_vwap[sym_code] = {
                'vol': 0,
                'cost': 0.0,
                'avg_price': 0.0,
                'first_buy_date': '',
                'last_buy_date': '',
            }
        h = holdings_vwap[sym_code]
        if t.order_type == 'BUY':
            h['vol'] += t.volume
            h['cost'] += (t.volume * t.price)
            h['avg_price'] = round(h['cost'] / h['vol'], 2) if h['vol'] > 0 else 0.0
            if not h['first_buy_date']:
                h['first_buy_date'] = t.trade_date
            h['last_buy_date'] = t.trade_date
        elif t.order_type == 'SELL':
            h['vol'] = max(0, h['vol'] - t.volume)
            h['cost'] = h['vol'] * h['avg_price']

    for sym in symbols:
        try:
            board_item = board_data.get(sym, {})
            raw_price = board_item.get('matchedPrice') or board_item.get('lastPrice') or board_item.get('refPrice') or 0
            current_price = float(raw_price)
            if 0 < current_price < 1000:
                current_price *= 1000

            change_pct = float(board_item.get('priceChangePercent') or board_item.get('changePercent') or 0.0)

            # Lấy chi tiết kỹ thuật từ stock controller
            detail = handle_stock_detail(sym)
            if current_price == 0 and detail:
                current_price = float(detail.get('price') or detail.get('prevPrice') or 0.0)
                change_pct = float(detail.get('percentChange') or 0.0)
            tech = detail.get('technicals', {}) or detail.get('technical', {})
            decision = detail.get('decisionEngine', {}) or detail.get('decision', {})

            s1 = float(tech.get('support', 0) or decision.get('stop_loss', 0))
            r1 = float(tech.get('resistance', 0) or decision.get('target1', 0))

            # Trạng thái SuperTrend Ribbon
            ribbon_color = 'GREEN' if 'XANH' in str(decision.get('ribbon_status', '')).upper() or 'BULL' in str(decision.get('ribbon_status', '')).upper() else 'PINK'

            state = get_alert_state(sym)
            last_alert = state.get('last_alert_type', '')
            last_ribbon = state.get('last_ribbon_color', '')
            flip_count = state.get('flip_count_today', 0)

            # Ghi nhận biến động màu SuperTrend trong ngày (để dành gửi lúc 14h30)
            if last_ribbon and last_ribbon != ribbon_color:
                flip_count += 1
                logger.info("Mã %s đổi màu SuperTrend: %s -> %s (lần %d trong ngày)", sym, last_ribbon, ribbon_color, flip_count)

            state['last_ribbon_color'] = ribbon_color
            state['flip_count_today'] = flip_count

            h_info = holdings_vwap.get(sym, {})
            avg_price = h_info.get('avg_price', 0.0)
            trade_date = h_info.get('last_buy_date') or h_info.get('first_buy_date') or ''

            st_info = tech.get('supertrend', {})
            signal_date = st_info.get('signalDate', '')
            holding_bars = st_info.get('holdingBars', 0)

            pnl_pct = round(((current_price - avg_price) / avg_price * 100), 2) if avg_price > 0 and current_price > 0 else 0.0
            dist_to_sl = round(((current_price - s1) / current_price * 100), 2) if current_price > 0 and s1 > 0 else 0.0

            alert_data = {
                'price': current_price,
                'change_pct': change_pct,
                'stop_loss': s1,
                'target1': r1,
                'avg_price': avg_price,
                'pnl_pct': pnl_pct,
                'dist_to_sl': dist_to_sl,
                'trade_date': trade_date,
                'signal_date': signal_date,
                'holding_bars': holding_bars,
            }

            today_str = get_vn_now().strftime('%Y-%m-%d')
            sl_key = f'PORTFOLIO_STOPLOSS_{today_str}_{sym}'
            near_sl_key = f'PORTFOLIO_NEAR_SL_{today_str}_{sym}'

            # 1. Kiểm tra CẮT LỖ (Đã vi phạm S1 HOẶC lỗ >= 7.0%)
            if current_price > 0 and ((s1 > 0 and current_price <= s1) or (avg_price > 0 and pnl_pct <= -7.0)):
                if last_alert != 'STOPLOSS_TRIGGERED' and not is_alert_already_sent(sl_key, min_interval_seconds=14400):
                    # Bắn Telegram lần đầu khi vi phạm
                    msg, btns = format_portfolio_alert(sym, 'STOPLOSS_TRIGGERED', alert_data)
                    log_meta = {
                        'alert_type': 'PORTFOLIO_STOPLOSS',
                        'title': f'Cảnh báo Cắt lỗ S1: {sym}',
                        'stocks': [{
                            'symbol': sym,
                            'price': current_price,
                            'change_pct': change_pct,
                            'stop_loss': s1,
                            'avg_price': avg_price,
                            'pnl_pct': pnl_pct,
                            'action': 'STOPLOSS_TRIGGERED'
                        }]
                    }
                    if send_telegram_message(msg, buttons=btns, log_meta=log_meta):
                        record_alert_sent(sl_key, preview=f'Stoploss {sym}')
                        state['last_alert_type'] = 'STOPLOSS_TRIGGERED'
                        state['last_alert_time'] = now_ts
                        logger.info("Đã gửi cảnh báo STOPLOSS cho %s", sym)

            # 2. Kiểm tra CẬN DẢI DỪNG LỖ (Cách SL <= 2.0% HOẶC lỗ từ -5.0% đến -6.9%)
            elif current_price > 0 and (
                (s1 > 0 and 0 < dist_to_sl <= 2.0) or
                (avg_price > 0 and -6.9 <= pnl_pct <= -5.0)
            ):
                if last_alert not in ['STOPLOSS_TRIGGERED', 'NEAR_STOPLOSS'] and not is_alert_already_sent(near_sl_key, min_interval_seconds=14400):
                    # Bắn Telegram cảnh báo sớm tiệm cận SL
                    msg, btns = format_portfolio_alert(sym, 'NEAR_STOPLOSS', alert_data)
                    log_meta = {
                        'alert_type': 'PORTFOLIO_NEAR_SL',
                        'title': f'Cảnh báo Sớm Tiệm Cận SL: {sym}',
                        'stocks': [{
                            'symbol': sym,
                            'price': current_price,
                            'change_pct': change_pct,
                            'stop_loss': s1,
                            'avg_price': avg_price,
                            'pnl_pct': pnl_pct,
                            'dist_to_sl': dist_to_sl,
                            'action': 'NEAR_STOPLOSS'
                        }]
                    }
                    if send_telegram_message(msg, buttons=btns, log_meta=log_meta):
                        record_alert_sent(near_sl_key, preview=f'Near Stoploss {sym}')
                        state['last_alert_type'] = 'NEAR_STOPLOSS'
                        state['last_alert_time'] = now_ts
                        logger.info("Đã gửi cảnh báo CẬN DẢI DỪNG LỖ cho %s", sym)

            # 3. Giá trở lại vùng an toàn bình thường (Cách SL > 2.5% và PnL > -4.5%)
            else:
                if last_alert in ['STOPLOSS_TRIGGERED', 'NEAR_STOPLOSS'] and dist_to_sl > 2.5 and pnl_pct > -4.5:
                    state['last_alert_type'] = 'NORMAL'

            save_alert_state(sym, state)
        except Exception as e:
            logger.warning("Lỗi quét tín hiệu cho mã %s: %s", sym, e)


def send_daily_ribbon_digest():
    """
    Gửi báo cáo tổng kết xác nhận tín hiệu nến SuperTrend Daily chốt phiên (lúc 15:02 sau khi sàn đóng cửa) các ngày Thứ 2 đến Thứ 6.
    Lấy giá đóng cửa chính thức chuẩn 100% từ nến ngày 1D của Entrade Engine.
    Gom toàn bộ các mã nhấp nháy hoặc thay đổi xu hướng trong ngày vào 1 tin nhắn duy nhất.
    """
    symbols = get_active_holding_symbols()
    if not symbols:
        return

    logger.info("Bắt đầu tạo Báo cáo Tín hiệu SuperTrend Chốt Phiên EOD (15:00) cho %d mã...", len(symbols))
    from backend.controllers.user_portfolio_controller import get_entrade_stock_quote
    board_data = get_market_board_data() or {}
    digest_items = []

    trades = get_all_trade_models()
    holdings_vwap = {}
    for t in sorted(trades, key=lambda x: (x.trade_date, str(x.id or ''))):
        sym_code = (t.symbol or '').strip().upper()
        if not sym_code:
            continue
        if sym_code not in holdings_vwap:
            holdings_vwap[sym_code] = {'vol': 0, 'cost': 0.0, 'avg_price': 0.0, 'first_buy_date': '', 'last_buy_date': ''}
        h = holdings_vwap[sym_code]
        if t.order_type == 'BUY':
            h['vol'] += t.volume
            h['cost'] += (t.volume * t.price)
            h['avg_price'] = round(h['cost'] / h['vol'], 2) if h['vol'] > 0 else 0.0
            if not h['first_buy_date']:
                h['first_buy_date'] = t.trade_date
            h['last_buy_date'] = t.trade_date

    for sym in symbols:
        try:
            state = get_alert_state(sym)
            quote = get_entrade_stock_quote(sym, board_data)
            p = float(quote.get('current_price', 0.0))
            pct = float(quote.get('change_pct', 0.0))
            sign = '+' if pct >= 0 else ''

            detail = handle_stock_detail(sym)
            decision = detail.get('decisionEngine', {}) or detail.get('decision', {})
            ribbon_status = str(decision.get('ribbon_status', ''))
            is_green = 'XANH' in ribbon_status.upper() or 'BULL' in ribbon_status.upper()
            flip_count = state.get('flip_count_today', 0)

            color_icon = '🟢' if is_green else '🔴'
            color_name = 'VÙNG XANH (Tăng)' if is_green else 'VÙNG HỒNG (Giảm)'

            h_info = holdings_vwap.get(sym, {})
            t_date = h_info.get('last_buy_date') or h_info.get('first_buy_date') or ''
            t_status = get_t_plus_status(t_date)
            t_note = f" (Mua: {t_date}, {t_status.split(' ')[0]})" if t_date else ""

            note_whipsaw = ""
            if flip_count >= 2:
                note_whipsaw = f" <i>(⚠️ Trong phiên nhấp nháy giằng co {flip_count} lần)</i>"

            note_near_sl = ""
            if state.get('last_alert_type') == 'NEAR_STOPLOSS':
                note_near_sl = " <b>[⚠️ CẬN SL]</b>"

            digest_items.append(
                f"• <b>{sym}</b>: {color_icon} <b>{color_name}</b>{t_note} | Giá chốt phiên: <b>{p:,.0f} đ</b> ({sign}{pct:.2f}%){note_near_sl}{note_whipsaw}"
            )

            # Reset lại flip_count cho ngày hôm sau
            state['flip_count_today'] = 0
            save_alert_state(sym, state)
        except Exception as e:
            logger.warning("Lỗi tạo digest cho %s: %s", sym, e)

    if not digest_items:
        return

    base_url = get_public_url()
    access_pin = os.environ.get('APP_ACCESS_PIN', '').strip()
    auth_query = f"?auth={access_pin}" if access_pin else ""
    auth_suffix = f"&auth={access_pin}" if access_pin else ""
    home_link = f"{base_url}/{auth_query}".rstrip('/')
    portfolio_link = f"{base_url}/?mode=portfolio{auth_suffix}"

    today_str = get_vn_now().strftime('%d/%m/%Y')
    msg = (
        "📊 <b>XÁC NHẬN TÍN HIỆU SUPERTREND CHỐT PHIÊN (15:00)</b>\n"
        f"📅 <i>Ngày {today_str} - Danh mục đang nắm giữ</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(digest_items) + "\n\n"
        "💡 <i>Mức giá đóng cửa chính thức sau phiên ATC và tín hiệu nến Daily đã xác nhận hoàn tất. "
        "Hãy theo dõi để đưa ra quyết định tái cơ cấu danh mục cho phiên tiếp theo.</i>"
    )

    buttons = [
        {'text': '💼 Mở Sổ Lệnh Danh Mục', 'url': portfolio_link},
        {'text': '🌐 Mở Stock RT Live Web', 'url': home_link}
    ]

    ribbon_key = f'RIBBON_DIGEST_EOD_{today_str}'
    if not is_alert_already_sent(ribbon_key, min_interval_seconds=14400):
        log_meta = {
            'alert_type': 'RIBBON_DIGEST_EOD',
            'title': f'Xác nhận tín hiệu SuperTrend chốt phiên (15:00) - Ngày {today_str}',
            'stocks': [
                {'symbol': s, 'action': 'SUPERTREND_CHECK'} for s in symbols
            ]
        }
        if send_telegram_message(msg, buttons=buttons, log_meta=log_meta):
            record_alert_sent(ribbon_key, preview='EOD Ribbon Digest')
            logger.info("Đã gửi Báo cáo Tín hiệu SuperTrend Chốt Phiên EOD qua Telegram.")


def portfolio_worker_loop():
    """Vòng lặp chạy ngầm của Scheduler."""
    global _last_scan_ts, _last_digest_date
    logger.info("Portfolio Scheduler Worker đã khởi chạy thành công.")

    while True:
        try:
            now = get_vn_now()
            today_str = now.strftime('%Y-%m-%d')

            # 1. Kiểm tra gửi Báo cáo Chốt Phiên EOD (từ 15:02 đến 15:10, các ngày T2 - T6 sau khi kết thúc toàn phiên 15:00)
            if is_trading_day(now):
                if now.hour == 15 and 2 <= now.minute <= 10:
                    if _last_digest_date != today_str:
                        _last_digest_date = today_str
                        send_daily_ribbon_digest()

            # 2. Quét định kỳ 15 phút/lần (900 giây) trong phiên giao dịch
            if is_market_hours(now):
                now_ts = int(time.time())
                if now_ts - _last_scan_ts >= 900:  # 15 phút
                    _last_scan_ts = now_ts
                    scan_portfolio_alerts()

        except Exception as e:
            logger.error("Lỗi trong vòng lặp Portfolio Scheduler: %s", e)

        # Ngủ 30 giây mỗi chu kỳ lặp
        time.sleep(30)


def start_portfolio_scheduler():
    """Khởi động worker thread cho Portfolio Scanner."""
    t = threading.Thread(target=portfolio_worker_loop, daemon=True)
    t.start()
    return t

