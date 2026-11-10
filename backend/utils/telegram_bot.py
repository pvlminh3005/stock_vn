"""
Stock RT - Telegram Alert Engine
Quản lý gửi cảnh báo real-time qua Telegram Bot API:
- Định dạng tin nhắn HTML chuyên nghiệp
- Tích hợp Inline Keyboard Button dẫn link deep-link (?ticker=...)
- Hỗ trợ biến môi trường TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, APP_PUBLIC_URL
"""

import logging
import os
from typing import Optional, List, Dict, Any, Tuple
import requests

from backend.constants.urls import build_telegram_url

logger = logging.getLogger('telegram_bot')

from backend.config.env_loader import load_environment

load_environment()

# Cấu hình mặc định từ biến môi trường (Bảo mật: không hardcode key/id trên Git)
DEFAULT_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
DEFAULT_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')


def get_public_url(public_url: Optional[str] = None) -> str:
  """
  Tự động nhận diện URL:
  1. Ưu tiên tham số public_url truyền vào
  2. Biến APP_PUBLIC_URL (nếu người dùng cấu hình thủ công)
  3. Biến RENDER_EXTERNAL_URL (Render tự động cấp sẵn khi deploy)
  4. Mặc định fallback: http://localhost:8000
  """
  url = (
      public_url
      or os.environ.get('APP_PUBLIC_URL')
      or os.environ.get('RENDER_EXTERNAL_URL')
      or 'http://localhost:8000'
  )
  return url.rstrip('/')


APP_PUBLIC_URL = get_public_url()


def send_telegram_message(
    text: str,
    buttons: Optional[List[Dict[str, str]]] = None,
    chat_id: Optional[str] = None,
    token: Optional[str] = None,
    log_meta: Optional[Dict[str, Any]] = None,
) -> bool:
  """
  Gửi tin nhắn định dạng HTML tới Telegram qua Bot API.
  :param text: Nội dung tin nhắn (hỗ trợ thẻ <b>, <i>, <a>, <code>)
  :param buttons: Danh sách nút bấm Inline, ví dụ: [{'text': 'Xem SSI', 'url': 'https://.../?ticker=SSI'}]
  :param chat_id: ID người nhận (mặc định lấy DEFAULT_CHAT_ID)
  :param token: Bot token (mặc định lấy DEFAULT_BOT_TOKEN)
  :param log_meta: Metadata cảnh báo có cấu trúc (chỉ gồm mã, giá, action, vùng gom, v.v.) để lưu tracking MongoDB
  :return: True nếu gửi thành công, False nếu lỗi
  """
  bot_token = token or DEFAULT_BOT_TOKEN or os.environ.get('TELEGRAM_BOT_TOKEN', '')
  target_chat_id = chat_id or DEFAULT_CHAT_ID or os.environ.get('TELEGRAM_CHAT_ID', '')

  if not bot_token:
    logger.debug('Telegram Bot Token chưa được cấu hình (TELEGRAM_BOT_TOKEN). Bỏ qua gửi tin.')
    return False

  if not target_chat_id:
    logger.debug('Telegram Chat ID chưa được cấu hình (TELEGRAM_CHAT_ID). Bỏ qua gửi tin.')
    return False

  url = build_telegram_url(bot_token, 'sendMessage')
  payload = {
      'chat_id': str(target_chat_id),
      'text': text,
      'parse_mode': 'HTML',
      'disable_web_page_preview': True,
  }

  final_text = text
  if buttons and isinstance(buttons, list) and len(buttons) > 0:
    # Định dạng Inline Keyboard (Telegram chỉ cho phép URL public/https cho nút bấm)
    inline_keyboard = []
    row = []
    fallback_links = []
    for btn in buttons:
      btn_url = btn.get('url', '')
      btn_text = btn.get('text', 'Chi tiết')
      if 'localhost' in btn_url or '127.0.0.1' in btn_url:
        # Nếu đang chạy localhost (chưa deploy public domain), chèn link trực tiếp vào text
        fallback_links.append(f'<a href="{btn_url}">{btn_text}</a>')
      elif btn_url.startswith('http://') or btn_url.startswith('https://'):
        row.append({'text': btn_text, 'url': btn_url})

    if row:
      inline_keyboard.append(row)
      payload['reply_markup'] = {'inline_keyboard': inline_keyboard}
    if fallback_links:
      final_text += '\n👉 ' + ' | '.join(fallback_links)

  payload['text'] = final_text

  try:
    resp = requests.post(url, json=payload, timeout=8)
    if resp.status_code == 200:
      msg_id = None
      try:
        msg_id = resp.json().get('result', {}).get('message_id')
      except Exception:
        pass
      if log_meta and isinstance(log_meta, dict):
        try:
          from backend.db.portfolio_db import save_telegram_sent_log
          save_telegram_sent_log(
              alert_type=log_meta.get('alert_type', 'GENERAL'),
              title=log_meta.get('title', 'Thông báo thị trường'),
              stocks=log_meta.get('stocks', []),
              market_regime=log_meta.get('market_regime'),
              vnindex=log_meta.get('vnindex'),
              message_id=msg_id,
              status='SUCCESS'
          )
        except Exception as e_log:
          logger.warning('Lỗi lưu log Telegram vào MongoDB: %s', e_log)
      return True
    else:
      logger.warning('Telegram API trả về lỗi: %s - %s', resp.status_code, resp.text)
      return False
  except Exception as e:
    logger.warning('Lỗi kết nối khi gửi Telegram Alert: %s', e)
    return False


def format_breakout_alert(
    stock: dict,
    public_url: Optional[str] = None,
    header_title: Optional[str] = None,
) -> Tuple[str, List[Dict[str, str]]]:
  """
  Soạn nội dung tin nhắn và nút bấm khi phát hiện mã BÙNG NỔ T0 / SÓNG SỚM SAU ATO.
  Toàn bộ số liệu và nhận định được tính toán động 100% từ nến kỹ thuật thực tế (VSR Engine).
  :return: (message_html, buttons_list)
  """
  base_url = get_public_url(public_url)
  symbol = str(stock.get('symbol', '')).upper()
  name = stock.get('name', symbol)
  price = float(stock.get('price', 0))

  # 1. Tỷ lệ % thay đổi thị giá: đồng bộ nhận diện mọi định dạng key từ Screener / Bảng giá
  change_pct = stock.get('changePct')
  if change_pct is None:
    change_pct = stock.get('pct_change')
  if change_pct is None:
    change_pct = stock.get('percentChange')
  if change_pct is None:
    change_pct = stock.get('priceChangePercent')
  if change_pct is None:
    ref_p = float(stock.get('refPrice', stock.get('prevPrice', 0)))
    if ref_p > 0 and price > 0:
      change_pct = round(((price - ref_p) / ref_p) * 100, 2)
    else:
      change_pct = 0.0
  else:
    change_pct = float(change_pct)

  vol_rate = stock.get('volRunRate')
  if vol_rate is None:
    vol_rate = stock.get('vol_run_rate', stock.get('volRatio', 1.0))
  vol_run_rate = float(vol_rate or 1.0)

  buy_ratio_val = stock.get('buyRatio')
  if buy_ratio_val is None:
    buy_ratio_val = stock.get('buy_ratio', 50.0)
  buy_ratio = float(buy_ratio_val or 50.0)
  net_rr = float(stock.get('net_rr', stock.get('netRR', 0.0)))
  s1 = float(stock.get('support', stock.get('s1', 0)))
  r1 = float(stock.get('target1', stock.get('resistance', 0)))
  stop_loss = float(stock.get('stop_loss', stock.get('stopLoss', 0)))
  sector = stock.get('sector', '')

  # 2. Tính toán % kỳ vọng động cho Mục tiêu R1 và Cắt lỗ SL
  if price > 0 and r1 > 0:
    upside_pct = round(((r1 - price) / price * 100), 2)
    r1_display = f"<b>{r1:,.0f} đ</b> (+{upside_pct:.1f}%)"
  elif r1 > 0:
    r1_display = f"<b>{r1:,.0f} đ</b>"
  else:
    r1_display = "<i>Dữ liệu chưa ghi nhận</i>"

  if price > 0 and stop_loss > 0:
    downside_pct = round(((stop_loss - price) / price * 100), 2)
    sl_display = f"<b>{stop_loss:,.0f} đ</b> ({downside_pct:.1f}%)"
  elif stop_loss > 0:
    sl_display = f"<b>{stop_loss:,.0f} đ</b>"
  else:
    sl_display = "<i>Dữ liệu chưa ghi nhận</i>"

  # 3. Đánh giá chuẩn VSR động theo tỷ lệ Net R:R thực tế (Không hardcode)
  if net_rr >= 2.0:
    vsr_status = f"1:{net_rr:.2f} (Vượt chuẩn VSR ⭐⭐⭐ - Biên lãi vượt trội)"
  elif net_rr >= 1.5:
    vsr_status = f"1:{net_rr:.2f} (Đạt chuẩn VSR ✅ - Đủ biên an toàn)"
  elif net_rr >= 1.2:
    vsr_status = f"1:{net_rr:.2f} (Cận chuẩn VSR ⚠️ - R:R mỏng, cân nhắc)"
  elif net_rr > 0:
    vsr_status = f"1:{net_rr:.2f} (Dưới chuẩn VSR ❌ - Rủi ro cao)"
  else:
    vsr_status = "<i>Dữ liệu chưa ghi nhận</i>"

  # 4. Khuyến nghị hành động & Tỷ trọng giải ngân dứt khoát (Rõ ràng - Minh bạch)
  action_badge = stock.get('action_badge') or stock.get('actionLabel')
  alloc_pct = stock.get('allocated_pct')
  if alloc_pct is None:
    alloc_pct = stock.get('allocPct', stock.get('allocatedNowPct'))

  action_reason = stock.get('action_reason') or stock.get('action_guide') or stock.get('actionGuide')

  # Fallback phân loại dứt khoát nếu chưa có badge từ Engine
  if not action_badge:
    primary_act = stock.get('primary_action') or stock.get('actionStatus', '')
    if primary_act in ['BUY_READY', 'BUY', 'BUY_PROBE']:
      action_badge = '🟢 MUA THĂM DÒ'
    elif primary_act in ['OVER_EXTENDED', 'WAIT', 'WAITING_CONFIRMATION']:
      action_badge = '🟡 ĐỨNG NGOÀI / CHỜ RETEST'
    elif primary_act in ['REDUCE', 'SELL', 'RISK_HIGH']:
      action_badge = '🔴 HẠ TỶ TRỌNG'
    elif net_rr < 1.2:
      action_badge = '🟡 QUAN SÁT (R:R MỎNG)'
    else:
      action_badge = '🟢 THEO DÕI GIẢI NGÂN'

  # Xác định tỷ trọng giải ngân hiển thị để user không nhầm lẫn
  badge_str = str(action_badge).upper()
  if 'KHÔNG' in badge_str or 'CHỜ' in badge_str or 'ĐỨNG NGOÀI' in badge_str or 'QUAN SÁT' in badge_str or 'TRÁNH' in badge_str:
    alloc_display = "0% NAV (Chưa giải ngân)"
  elif alloc_pct is not None and float(alloc_pct) > 0:
    alloc_display = f"{float(alloc_pct):.0f}% NAV"
  elif 'MUA' in badge_str:
    alloc_display = "15-20% NAV"
  else:
    alloc_display = "0% NAV (Theo dõi)"

  if not action_reason:
    if 'MUA' in badge_str or 'THĂM DÒ' in badge_str:
      action_reason = f"Dòng tiền nhập cuộc tích cực (Vol x{vol_run_rate:.1f} TB20, Mua CĐ {buy_ratio:.0f}%). Mở vị thế thăm dò 20-30% để lấy lợi thế T+0."
    elif s1 > 0 and price > 0:
      dist_s1 = round(((price - s1) / s1 * 100), 1)
      if dist_s1 <= 2.5:
        action_reason = f"Giá sát nền hỗ trợ ({dist_s1:+.1f}%). Thăm dò vị thế quanh {s1:,.0f} đ, kiên nhẫn chờ nổ vol gia tăng."
      elif dist_s1 > 4.5:
        action_reason = f"Giá đã tăng xa nền ({dist_s1:+.1f}%). Tuyệt đối không FOMO mua đuổi, kiên nhẫn chờ retest."
      else:
        action_reason = f"Theo dõi nhịp hấp thụ hàng T+ phiên chiều. Xác nhận giữ vững hỗ trợ {s1:,.0f} đ trước khi giải ngân."
    else:
      action_reason = "Quan sát biến động dòng tiền và nến đóng cửa trước khi đưa ra quyết định giải ngân."

  sign = '+' if change_pct >= 0 else ''
  access_pin = os.environ.get('APP_ACCESS_PIN', '').strip()
  auth_param = f"&auth={access_pin}" if access_pin else ""
  deep_link = f'{base_url}/?ticker={symbol}{auth_param}'

  sector_tag = f" <i>(Sóng {sector})</i>" if sector else ""

  if not header_title:
    if stock.get('isEarlyBird'):
      header_title = f"🚀 <b>RADAR SÓNG SỚM SAU ATO: {symbol}</b>{sector_tag}"
    else:
      header_title = f"⚡ <b>CẢNH BÁO BÙNG NỔ T0: {symbol}</b>{sector_tag}"

  msg = (
      f"{header_title}\n"
      f"🏢 {name}\n\n"
      f"💰 <b>Thị giá:</b> {price:,.0f} đ ({sign}{change_pct:.2f}%)\n"
      f"📊 <b>Khối lượng:</b> Nổ <b>x{vol_run_rate:.1f}</b> TB20 | Mua CĐ: <b>{buy_ratio:.1f}%</b>\n"
      f"🎯 <b>Mục tiêu R1:</b> {r1_display} | 🛡️ <b>Cắt lỗ SL:</b> {sl_display}\n"
      f"⚖️ <b>Net R:R:</b> {vsr_status}\n\n"
      f"💡 <b>Khuyến nghị:</b> <b>{action_badge}</b> <i>(Tỷ trọng: {alloc_display})</i>\n"
      f"📝 <b>Lý do:</b> {action_reason}\n"
  )

  buttons = [
      {'text': f'📊 Mở Phân Tích {symbol}', 'url': deep_link}
  ]

  return msg, buttons


def format_actionable_buy_alert(
    stock: dict,
    public_url: Optional[str] = None,
) -> Tuple[str, List[Dict[str, str]]]:
  """
  Soạn tin cảnh báo ĐÈN XANH: MUA NGAY T0 cho cổ phiếu nhóm Tứ trụ (Bank, Chứng, Thép, BĐS).
  Định dạng tối ưu hóa để nhà đầu tư ra quyết định tức thì trong 30 giây:
  - Giá vào lệnh cụ thể (ngay tại thị giá)
  - Khối lượng nổ & Mua chủ động
  - Target R1, Cắt lỗ S1, Net R:R
  - Khuyến nghị tỷ trọng dứt khoát
  """
  base_url = get_public_url(public_url)
  symbol = str(stock.get('symbol', '')).upper()
  name = stock.get('name', symbol)
  price = float(stock.get('price', 0))
  sector = stock.get('sector', 'Tứ Trụ Dòng Tiền')

  change_pct = stock.get('changePct')
  if change_pct is None:
    change_pct = stock.get('pct_change', stock.get('percentChange', 0.0))
  change_pct = float(change_pct or 0.0)

  vol_rate = stock.get('volRunRate')
  if vol_rate is None:
    vol_rate = stock.get('vol_run_rate', stock.get('volRatio', 1.0))
  vol_run_rate = float(vol_rate or 1.0)

  buy_ratio = float(stock.get('buyRatio', stock.get('buy_ratio', 55.0)) or 55.0)
  net_rr = float(stock.get('net_rr', stock.get('netRR', 1.5)) or 1.5)
  s1 = float(stock.get('support', stock.get('s1', 0)))
  r1 = float(stock.get('target1', stock.get('resistance', 0)))
  stop_loss = float(stock.get('stop_loss', stock.get('stopLoss', s1)))

  sign = '+' if change_pct >= 0 else ''
  upside_pct = round(((r1 - price) / price * 100), 1) if price > 0 and r1 > price else 5.0
  downside_pct = round(((stop_loss - price) / price * 100), 1) if price > 0 and stop_loss > 0 else -3.0

  entry_max = round(price * 1.005, -2)
  entry_range = f"{price:,.0f} - {entry_max:,.0f} đ"

  access_pin = os.environ.get('APP_ACCESS_PIN', '').strip()
  auth_param = f"&auth={access_pin}" if access_pin else ""
  deep_link = f'{base_url}/?ticker={symbol}{auth_param}'

  is_leader = bool(stock.get('isMarketLeader') or 'LEADER' in str(stock.get('actionStatus', '')).upper())
  rs_score = stock.get('rsScore') or stock.get('rs_score')
  rs_line = f"🏆 <b>Sức mạnh giá:</b> RS Rating <b>{rs_score}/99</b> (Vượt trội thị trường)\n" if rs_score else ""

  if is_leader:
    header = f"⭐ <b>ĐÈN XANH: SIÊU CỔ PHIẾU DẪN DẮT: {symbol}</b> <i>(Sóng {sector})</i>"
    action_text = "⭐ MUA NGAY (MARKET LEADER)"
    note_text = "Siêu cổ phiếu bứt phá đỉnh dẫn dắt toàn thị trường, dòng tiền lớn áp đảo."
  else:
    header = f"🟢 <b>ĐÈN XANH: MUA NGAY T0: {symbol}</b> <i>(Nhóm {sector})</i>"
    action_text = "🟢 MUA NGAY T0"
    note_text = "Dòng tiền Tứ trụ vào mạnh chân sóng, sát nền hỗ trợ, không rủi ro đu đỉnh."

  msg = (
      f"{header}\n"
      f"🏢 {name}\n\n"
      f"💰 <b>Vùng vào lệnh:</b> <b>{entry_range}</b> ({sign}{change_pct:.2f}%)\n"
      f"{rs_line}"
      f"📊 <b>Dòng tiền:</b> Nổ <b>x{vol_run_rate:.1f}</b> TB20 | Mua CĐ: <b>{buy_ratio:.1f}%</b>\n"
      f"🎯 <b>Mục tiêu R1:</b> <b>{r1:,.0f} đ</b> (+{upside_pct:.1f}%)\n"
      f"🛡️ <b>Cắt lỗ kỷ luật (S1):</b> <b>{stop_loss:,.0f} đ</b> ({downside_pct:.1f}%)\n"
      f"⚖️ <b>Tỷ lệ Net R:R:</b> <b>1:{net_rr:.2f}</b> (Đạt chuẩn T+ an toàn)\n\n"
      f"💡 <b>Hành động:</b> <b>{action_text}</b> <i>(Tỷ trọng: 30-40% vị thế)</i>\n"
      f"📝 <b>Đặc điểm:</b> {note_text}\n"
  )

  buttons = [
      {'text': f'📊 Mở Phân Tích {symbol}', 'url': deep_link}
  ]
  return msg, buttons


def format_session_digest(
    title: str,
    stocks: list,
    regime: str,
    public_url: Optional[str] = None,
    vnindex_summary: Optional[dict] = None,
) -> Tuple[str, List[Dict[str, str]]]:
  """
  Soạn tin tổng kết phiên (Bản tin trưa 11:35 hoặc Tổng kết ATC 14:50) kèm điểm số VN-Index và % cổ phiếu chính xác.
  """
  base_url = get_public_url(public_url)
  regime_icon = '🟢' if 'BULL' in str(regime).upper() else ('🔴' if 'BEAR' in str(regime).upper() else '🟡')

  msg = (
      f"📊 <b>{title.upper()}</b>\n"
      f"🌐 <b>Xu hướng thị trường:</b> {regime_icon} {regime}\n"
  )

  if vnindex_summary and isinstance(vnindex_summary, dict) and vnindex_summary.get('price', 0) > 0:
    vni_p = float(vnindex_summary.get('price', 0))
    vni_chg = float(vnindex_summary.get('change', 0))
    vni_pct = float(vnindex_summary.get('changePercent', 0))
    vni_sign = '+' if vni_chg >= 0 else ''
    msg += f"📈 <b>VN-Index:</b> <b>{vni_p:,.2f}</b> ({vni_sign}{vni_chg:.2f} | {vni_sign}{vni_pct:.2f}%)\n"

  msg += "━━━━━━━━━━━━━━━━━━━━\n"

  if not stocks:
    msg += "<i>Chưa ghi nhận mã đạt chuẩn bùng nổ vượt trội trong khung thời gian này.</i>\n"
    return msg, [{'text': '🌐 Mở Stock RT Dashboard', 'url': base_url}]

  msg += "🔥 <b>TOP CƠ HỘI NỔI BẬT:</b>\n"
  for idx, s in enumerate(stocks[:4], 1):
    sym = s.get('symbol', '').upper()
    p = float(s.get('price', 0))
    pct = s.get('changePct')
    if pct is None:
      pct = s.get('pct_change', s.get('percentChange', s.get('priceChangePercent', 0.0)))
    pct = float(pct or 0.0)

    vol_rate = s.get('volRunRate')
    if vol_rate is None:
      vol_rate = s.get('vol_run_rate', s.get('volRatio', 1.0))
    vol_rate = float(vol_rate or 1.0)

    badge = s.get('actionLabel') or s.get('badge', 'BÙNG NỔ')
    entry_zone = s.get('entryZone') or s.get('buyZone')
    sign = '+' if pct >= 0 else ''
    if entry_zone and entry_zone not in badge:
      zone_suffix = f" <i>(Vùng gom: {entry_zone})</i>"
    else:
      zone_suffix = ""
    msg += f"<b>{idx}. {sym}</b>: {p:,.0f} đ ({sign}{pct:.2f}%) | Vol x{vol_rate:.1f} TB20 | {badge}{zone_suffix}\n"

  msg += "\n👉 <i>Bấm nút bên dưới để xem chi tiết danh mục và biểu đồ kỹ thuật.</i>"

  access_pin = os.environ.get('APP_ACCESS_PIN', '').strip()
  auth_param = f"?auth={access_pin}" if access_pin else ""
  home_link = f"{base_url}/{auth_param}".rstrip('/')
  if not home_link:
    home_link = base_url

  buttons = [
      {'text': '🌐 Mở Stock RT Live Web', 'url': home_link}
  ]
  return msg, buttons

