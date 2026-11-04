"""
Stock RT - Telegram Alert Engine
Quản lý gửi cảnh báo real-time qua Telegram Bot API:
- Định dạng tin nhắn HTML chuyên nghiệp
- Tích hợp Inline Keyboard Button dẫn link deep-link (?ticker=...)
- Hỗ trợ biến môi trường TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, APP_PUBLIC_URL
"""

import logging
import os
import requests

logger = logging.getLogger('telegram_bot')

# Cấu hình mặc định từ biến môi trường (Bảo mật: không hardcode key/id trên Git)
DEFAULT_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
DEFAULT_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')


def get_public_url(public_url: str = None) -> str:
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


def send_telegram_message(text: str, buttons: list = None, chat_id: str = None, token: str = None) -> bool:
  """
  Gửi tin nhắn định dạng HTML tới Telegram qua Bot API.
  :param text: Nội dung tin nhắn (hỗ trợ thẻ <b>, <i>, <a>, <code>)
  :param buttons: Danh sách nút bấm Inline, ví dụ: [{'text': 'Xem SSI', 'url': 'https://.../?ticker=SSI'}]
  :param chat_id: ID người nhận (mặc định lấy DEFAULT_CHAT_ID)
  :param token: Bot token (mặc định lấy DEFAULT_BOT_TOKEN)
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

  url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
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
      return True
    else:
      logger.warning('Telegram API trả về lỗi: %s - %s', resp.status_code, resp.text)
      return False
  except Exception as e:
    logger.warning('Lỗi kết nối khi gửi Telegram Alert: %s', e)
    return False


def format_breakout_alert(stock: dict, public_url: str = None) -> tuple:
  """
  Soạn nội dung tin nhắn và nút bấm khi phát hiện mã BÙNG NỔ T0.
  :return: (message_html, buttons_list)
  """
  base_url = get_public_url(public_url)
  symbol = str(stock.get('symbol', '')).upper()
  name = stock.get('name', symbol)
  price = stock.get('price', 0)
  change_pct = stock.get('pct_change', stock.get('percentChange', 0.0))
  vol_run_rate = stock.get('vol_run_rate', 1.0)
  buy_ratio = stock.get('buy_ratio', 50.0)
  net_rr = stock.get('net_rr', stock.get('netRR', 1.5))
  s1 = stock.get('support', 0)
  r1 = stock.get('target1', stock.get('resistance', 0))
  stop_loss = stock.get('stop_loss', stock.get('stopLoss', 0))
  sector = stock.get('sector', '')

  sign = '+' if change_pct >= 0 else ''
  access_pin = os.environ.get('APP_ACCESS_PIN', '').strip()
  auth_param = f"&auth={access_pin}" if access_pin else ""
  deep_link = f'{base_url}/?ticker={symbol}{auth_param}'

  sector_tag = f" <i>(Sóng {sector})</i>" if sector else ""

  msg = (
      f"⚡ <b>CẢNH BÁO BÙNG NỔ T0: {symbol}</b>{sector_tag}\n"
      f"🏢 {name}\n\n"
      f"💰 <b>Thị giá:</b> {price:,.0f} đ ({sign}{change_pct:.2f}%)\n"
      f"📊 <b>Khối lượng:</b> Nổ <b>x{vol_run_rate:.1f}</b> TB20 | Mua CĐ: <b>{buy_ratio}%</b>\n"
      f"🎯 <b>Mục tiêu R1:</b> {r1:,.0f} đ | <b>Cắt lỗ SL:</b> {stop_loss:,.0f} đ\n"
      f"⚖️ <b>Net R:R:</b> 1:{net_rr:.2f} (Đạt chuẩn VSR)\n\n"
      f"💡 <b>Hành động:</b> Thăm dò 20-30% vị thế trong phiên. Theo dõi nến ATC giữ vững để gia tăng.\n"
  )

  buttons = [
      {'text': f'📊 Mở Phân Tích {symbol}', 'url': deep_link}
  ]

  return msg, buttons


def format_session_digest(title: str, stocks: list, regime: str, public_url: str = None) -> tuple:
  """
  Soạn tin tổng kết phiên (Bản tin trưa 11:35 hoặc Tổng kết ATC 14:50).
  """
  base_url = get_public_url(public_url)
  regime_icon = '🟢' if 'BULL' in str(regime).upper() else ('🔴' if 'BEAR' in str(regime).upper() else '🟡')

  msg = (
      f"📊 <b>{title.upper()}</b>\n"
      f"🌐 <b>Xu hướng thị trường:</b> {regime_icon} {regime}\n"
      f"━━━━━━━━━━━━━━━━━━━━\n"
  )

  if not stocks:
    msg += "<i>Chưa ghi nhận mã đạt chuẩn bùng nổ vượt trội trong khung thời gian này.</i>\n"
    return msg, [{'text': '🌐 Mở Stock RT Dashboard', 'url': base_url}]

  msg += "🔥 <b>TOP CƠ HỘI NỔI BẬT:</b>\n"
  for idx, s in enumerate(stocks[:4], 1):
    sym = s.get('symbol', '').upper()
    p = s.get('price', 0)
    pct = s.get('pct_change', s.get('percentChange', 0.0))
    vol_rate = s.get('vol_run_rate', 1.0)
    badge = s.get('badge', 'BÙNG NỔ')
    sign = '+' if pct >= 0 else ''
    msg += f"<b>{idx}. {sym}</b>: {p:,.0f} đ ({sign}{pct:.2f}%) | Vol x{vol_rate:.1f} TB20 | {badge}\n"

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

