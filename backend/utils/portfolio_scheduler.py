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


def format_portfolio_alert(symbol: str, alert_type: str, detail: dict) -> tuple:
    """Định dạng tin nhắn cảnh báo Telegram cho vị thế trong sổ lệnh."""
    base_url = get_public_url()
    access_pin = os.environ.get('APP_ACCESS_PIN', '').strip()
    auth_param = f"&auth={access_pin}" if access_pin else ""
    deep_link = f"{base_url}/?ticker={symbol}{auth_param}"

    price = detail.get('price', 0)
    change_pct = detail.get('change_pct', 0.0)
    sign = '+' if change_pct >= 0 else ''

    if alert_type == 'STOPLOSS_TRIGGERED':
        stop_val = detail.get('stop_loss', 0)
        downside_pct = round(((stop_val - price) / price * 100), 2) if price > 0 and stop_val > 0 else 0.0
        msg = (
            f"🚨 <b>CẢNH BÁO DANH MỤC: {symbol} CHẠM NGƯỠNG CẮT LỖ!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Thị giá:</b> {price:,.0f} đ ({sign}{change_pct:.2f}%)\n"
            f"🛡️ <b>Mốc hỗ trợ S1 / Stoploss:</b> {stop_val:,.0f} đ ({downside_pct:.1f}%)\n\n"
            f"⚠️ <i>Giá cổ phiếu đã vi phạm hoặc xuyên thủng ngưỡng phòng thủ ban đầu. "
            f"Hãy xem xét hạ tỷ trọng hoặc đóng vị thế để bảo toàn vốn.</i>\n"
        )
    elif alert_type == 'TARGET_TRIGGERED':
        r1_val = detail.get('target1', 0)
        upside_pct = round(((r1_val - price) / price * 100), 2) if price > 0 and r1_val > 0 else 0.0
        msg = (
            f"🎯 <b>CẢNH BÁO DANH MỤC: {symbol} ĐẠT MỤC TIÊU CHỐT LỜI!</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Thị giá:</b> {price:,.0f} đ ({sign}{change_pct:.2f}%)\n"
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

            alert_data = {
                'price': current_price,
                'change_pct': change_pct,
                'stop_loss': s1,
                'target1': r1,
            }

            # 1. Kiểm tra CẮT LỖ S1
            today_str = get_vn_now().strftime('%Y-%m-%d')
            sl_key = f'PORTFOLIO_STOPLOSS_{today_str}_{sym}'
            tp_key = f'PORTFOLIO_TARGET_{today_str}_{sym}'

            if current_price > 0 and s1 > 0 and current_price <= s1:
                if last_alert != 'STOPLOSS_TRIGGERED' and not is_alert_already_sent(sl_key, min_interval_seconds=14400):
                    # Bắn Telegram lần đầu khi vi phạm
                    msg, btns = format_portfolio_alert(sym, 'STOPLOSS_TRIGGERED', alert_data)
                    if send_telegram_message(msg, buttons=btns):
                        record_alert_sent(sl_key, preview=f'Stoploss {sym}')
                        state['last_alert_type'] = 'STOPLOSS_TRIGGERED'
                        state['last_alert_time'] = now_ts
                        logger.info("Đã gửi cảnh báo STOPLOSS cho %s", sym)

            # 2. Kiểm tra CHỐT LỜI R1
            elif current_price > 0 and r1 > 0 and current_price >= r1:
                if last_alert != 'TARGET_TRIGGERED' and not is_alert_already_sent(tp_key, min_interval_seconds=14400):
                    # Bắn Telegram lần đầu khi chạm mục tiêu
                    msg, btns = format_portfolio_alert(sym, 'TARGET_TRIGGERED', alert_data)
                    if send_telegram_message(msg, buttons=btns):
                        record_alert_sent(tp_key, preview=f'Target {sym}')
                        state['last_alert_type'] = 'TARGET_TRIGGERED'
                        state['last_alert_time'] = now_ts
                        logger.info("Đã gửi cảnh báo TARGET cho %s", sym)

            # 3. Giá trở lại vùng bình thường
            else:
                if last_alert in ['STOPLOSS_TRIGGERED', 'TARGET_TRIGGERED']:
                    state['last_alert_type'] = 'NORMAL'

            save_alert_state(sym, state)
        except Exception as e:
            logger.warning("Lỗi quét tín hiệu cho mã %s: %s", sym, e)


def send_daily_ribbon_digest():
    """
    Gửi báo cáo tổng kết xác nhận tín hiệu nến SuperTrend Daily lúc 14:30 các ngày Thứ 2 đến Thứ 6.
    Gom toàn bộ các mã nhấp nháy hoặc thay đổi xu hướng trong ngày vào 1 tin nhắn duy nhất.
    """
    symbols = get_active_holding_symbols()
    if not symbols:
        return

    logger.info("Bắt đầu tạo Báo cáo Tín hiệu SuperTrend Cuối Phiên 14:30 cho %d mã...", len(symbols))
    board_data = get_market_board_data() or {}
    digest_items = []

    for sym in symbols:
        try:
            state = get_alert_state(sym)
            board_item = board_data.get(sym, {})
            raw_p = board_item.get('matchedPrice') or board_item.get('lastPrice') or board_item.get('refPrice') or 0
            p = float(raw_p)
            if 0 < p < 1000:
                p *= 1000
            pct = float(board_item.get('priceChangePercent') or board_item.get('changePercent') or 0.0)
            sign = '+' if pct >= 0 else ''

            detail = handle_stock_detail(sym)
            decision = detail.get('decisionEngine', {}) or detail.get('decision', {})
            ribbon_status = str(decision.get('ribbon_status', ''))
            is_green = 'XANH' in ribbon_status.upper() or 'BULL' in ribbon_status.upper()
            flip_count = state.get('flip_count_today', 0)

            color_icon = '🟢' if is_green else '🔴'
            color_name = 'VÙNG XANH (Tăng)' if is_green else 'VÙNG HỒNG (Giảm)'

            note_whipsaw = ""
            if flip_count >= 2:
                note_whipsaw = f" <i>(⚠️ Trong phiên nhấp nháy giằng co {flip_count} lần)</i>"

            digest_items.append(
                f"• <b>{sym}</b>: {color_icon} <b>{color_name}</b> | Giá: {p:,.0f} đ ({sign}{pct:.2f}%){note_whipsaw}"
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
    auth_param = f"?auth={access_pin}" if access_pin else ""
    home_link = f"{base_url}/{auth_param}".rstrip('/')

    today_str = get_vn_now().strftime('%d/%m/%Y')
    msg = (
        f"📊 <b>XÁC NHẬN TÍN HIỆU SUPERTREND CUỐI PHIÊN (14:30)</b>\n"
        f"📅 <i>Ngày {today_str} - Danh mục đang nắm giữ</i>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        + "\n".join(digest_items) + "\n\n"
        f"💡 <i>Tín hiệu nến Daily đã xác nhận trước khi bước vào phiên ATC. "
        f"Hãy theo dõi mức đóng cửa để đưa ra quyết định tái cơ cấu danh mục.</i>"
    )

    buttons = [
        {'text': '💼 Mở Sổ Lệnh Danh Mục', 'url': f"{home_link}?mode=portfolio"},
        {'text': '🌐 Mở Stock RT Live Web', 'url': home_link}
    ]

    ribbon_key = f'RIBBON_DIGEST_1430_{today_str}'
    if not is_alert_already_sent(ribbon_key, min_interval_seconds=14400):
        if send_telegram_message(msg, buttons=buttons):
            record_alert_sent(ribbon_key, preview='14:30 Ribbon Digest')
            logger.info("Đã gửi Báo cáo Tín hiệu SuperTrend Cuối Phiên 14:30 qua Telegram.")


def portfolio_worker_loop():
    """Vòng lặp chạy ngầm của Scheduler."""
    global _last_scan_ts, _last_digest_date
    logger.info("Portfolio Scheduler Worker đã khởi chạy thành công.")

    while True:
        try:
            now = get_vn_now()
            today_str = now.strftime('%Y-%m-%d')

            # 1. Kiểm tra gửi Báo cáo 14h30 (từ 14:30 đến 14:35, các ngày T2 - T6)
            if is_trading_day(now):
                if now.hour == 14 and 30 <= now.minute <= 35:
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

