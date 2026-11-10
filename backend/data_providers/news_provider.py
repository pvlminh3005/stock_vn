"""
Stock RT - Multi-Source News & Media Crawler Provider
Thu thập và truy vết tin tức doanh nghiệp, sự kiện công bố thông tin, báo cáo tài chính và tin tức vĩ mô.
"""
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
try:
  from vnstock import Company, status
except ImportError:
  try:
    from vnstock.account import status
    from vnstock.compat import Company
  except ImportError:
    Company = None
    def status(): return {}

from backend.constants.colors import (
    BADGE_COLOR_COMPANY,
    BADGE_COLOR_EVENT,
    BADGE_COLOR_FINANCE,
    BADGE_COLOR_MACRO,
    BADGE_COLOR_MARKET,
    BADGE_COLOR_PRESS,
)
from backend.constants.config import BROWSER_HEADERS
from backend.constants.urls import (
    ENTRADE_BASE_URL,
    CAFEF_BASE_URL,
    VNEXPRESS_BASE_URL,
    BAOCHINHPHU_BASE_URL,
    build_cafef_search_url,
    build_cafef_events_url,
    build_vietstock_finance_url,
)
from backend.utils.network import vnstock_call

_LIVE_NEWS_CACHE = {}
_LIVE_NEWS_CACHE_TTL = 600  # 10 phút cache cho mỗi mã cổ phiếu

def mentions_ticker(text, ticker):
  """Kiểm tra tiêu đề có nhắc đúng mã cổ phiếu (khớp nguyên từ, tránh 'VIC' khớp 'VICTORY')."""
  return bool(re.search(rf'(?<![A-Z0-9]){re.escape(ticker.upper())}(?![A-Z0-9])', str(text or '').upper()))

def news_age_days(date_str):
  """Số ngày kể từ ngày đăng tin (định dạng YYYY-MM-DD...). Trả về None nếu không rõ ngày."""
  m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', str(date_str or ''))
  if not m:
    return None
  try:
    ts = time.mktime(time.strptime(m.group(0), '%Y-%m-%d'))
    return max(0, int((time.time() - ts) // 86400))
  except Exception:
    return None

def fetch_live_multi_sources(ticker, market_item=None, fundamental_info=None, current_price=0, pct_change=0.0, sector_name='', ssi_item=None):
  """
  Truy vết Real-time dữ liệu Tin tức, BCTC, Sự kiện & Vĩ mô từ nhiều nguồn độc lập:
  (Tin doanh nghiệp FiinGroup/VCI, Cổng Sự kiện HoSE/HNX, CafeF, VnExpress Kinh Doanh, Bảng Giá Thị Trường Realtime, Cổng TTĐT Chính Phủ).
  """
  item = market_item or ssi_item
  now = time.time()
  cached = _LIVE_NEWS_CACHE.get(ticker)
  if cached and (now - cached['time'] < _LIVE_NEWS_CACHE_TTL):
    records = [dict(r) for r in cached['data']]
    # Cập nhật số liệu bảng giá realtime mới nhất nếu có
    for r in records:
      if r.get('source') == 'Bảng Giá Thị Trường Realtime':
        vol = item.get('stockVol', 0) if item else 0
        buy_vol = item.get('stockBUVol', 0) if item else 0
        sell_vol = item.get('stockSDVol', 0) if item else 0
        f_net = (item.get('buyForeignQtty', 0) - item.get('sellForeignQtty', 0)) if item else 0
        r['title'] = (
            f"Khớp lệnh {current_price:,.0f} ({pct_change:+.2f}%) | KL: {vol:,.0f} cp | "
            f"Mua CĐ: {buy_vol:,.0f} vs Bán CĐ: {sell_vol:,.0f} | NN ròng: {f_net:,.0f} cp"
        )
        r['date'] = time.strftime('%d/%m/%Y %H:%M')
    return records

  news_records = []

  # 1. CafeF Doanh nghiệp: thu thập các tin tức báo chí mới nhất có nhắc đúng mã cổ phiếu
  def trace_cafef():
    items = []
    try:
      url = build_cafef_search_url(ticker)
      req = urllib.request.Request(url, headers=BROWSER_HEADERS)
      with urllib.request.urlopen(req, timeout=3.5) as res:
        soup = BeautifulSoup(res.read(), 'html.parser')
      for h in soup.find_all(['h3', 'h4']):
        a = h.find('a')
        if a and a.get_text(strip=True):
          txt = a.get_text(strip=True)
          if len(txt) <= 15 or not mentions_ticker(txt, ticker):
            continue
          link = a.get('href', '')
          if not link.startswith('http'):
            link = CAFEF_BASE_URL + link
          items.append({
              'source': 'CafeF Doanh Nghiệp',
              'badge': 'TIN TỨC BÁO CHÍ',
              'badgeColor': BADGE_COLOR_COMPANY,
              'title': txt,
              'date': '',
              'url': link,
              'tickerSpecific': True,
          })
          if len(items) >= 3:
            break
    except Exception:
      pass
    return items

  # 2. Cổng Sự kiện Doanh Nghiệp (HoSE/HNX): sự kiện mới nhất theo ngày công bố
  def trace_events():
    try:
      # vnstock 5.x yêu cầu tài khoản bản quyền/Pro cho Company.events()
      s = status()
      if not s.get('authenticated', False) and s.get('tier') == 'guest':
        return None
      if Company is None:
        return None
      events = vnstock_call(lambda: Company(symbol=ticker, source='VCI').events())
      if events is not None and not events.empty:
        if 'public_date' in events.columns:
          events = events.sort_values('public_date', ascending=False)
        e0 = events.iloc[0]
        title = str(
            e0.get('event_title_vi')
            or e0.get('event_name_vi')
            or f'Công bố thông tin {ticker}'
        )
        pub_date = e0.get('public_date')
        return {
            'source': 'Cổng Sự Kiện Doanh Nghiệp (HoSE/HNX)',
            'badge': 'SỰ KIỆN & CỔ TỨC',
            'badgeColor': BADGE_COLOR_EVENT,
            'title': title,
            'date': str(pub_date)[:10] if isinstance(pub_date, str) else '',
            'url': build_cafef_events_url(ticker),
            'tickerSpecific': True,
        }
    except Exception:
      pass
    return None

  # 4. VnExpress Kinh Doanh RSS
  def trace_vne():
    try:
      url = f'{VNEXPRESS_BASE_URL}/rss/kinh-doanh.rss'
      req = urllib.request.Request(url, headers=BROWSER_HEADERS)
      with urllib.request.urlopen(req, timeout=3.5) as res:
        root = ET.fromstring(res.read())
      items = root.findall('.//item')

      def _to_record(item, ticker_specific):
        return {
            'source': 'VnExpress Kinh Doanh',
            'badge': 'TIN DOANH NGHIỆP' if ticker_specific else 'THỜI SỰ KINH TẾ (CHUNG)',
            'badgeColor': BADGE_COLOR_PRESS,
            'title': item.findtext('title', ''),
            'date': item.findtext('pubDate', '')[:16],
            'url': item.findtext('link', ''),
            'tickerSpecific': ticker_specific,
        }

      for item in items[:30]:
        if mentions_ticker(item.findtext('title', ''), ticker):
          return _to_record(item, True)
      if items:
        return _to_record(items[0], False)
    except Exception:
      pass
    return None

  # 5. Vĩ mô Cổng Thông Tin Điện Tử Chính Phủ
  def trace_gov():
    try:
      url = f'{BAOCHINHPHU_BASE_URL}/kinh-te.rss'
      req = urllib.request.Request(url, headers=BROWSER_HEADERS)
      with urllib.request.urlopen(req, timeout=3.5) as res:
        root = ET.fromstring(res.read())
      items = root.findall('.//item')
      if items:
        it0 = items[0]
        return {
            'source': 'Cổng TTĐT Chính Phủ (Vĩ Mô)',
            'badge': 'VĨ MÔ NHÀ NƯỚC',
            'badgeColor': BADGE_COLOR_MACRO,
            'title': it0.findtext('title', ''),
            'date': it0.findtext('pubDate', ''),
            'url': it0.findtext('link', ''),
            'tickerSpecific': False,
        }
    except Exception:
      pass
    return None

  # Thực thi crawl song song 4 luồng
  with ThreadPoolExecutor(max_workers=4) as ex:
    f_cafef = ex.submit(trace_cafef)
    f_events = ex.submit(trace_events)
    f_vne = ex.submit(trace_vne)
    f_gov = ex.submit(trace_gov)

    cafef_items = f_cafef.result()
    events_item = f_events.result()
    vne_item = f_vne.result()
    gov_item = f_gov.result()

  # 1. Tin doanh nghiệp gắn mã từ CafeF
  if cafef_items:
    news_records.extend(cafef_items)

  # 2. Cổng Sự kiện Doanh Nghiệp (HoSE/HNX)
  if events_item:
    news_records.append(events_item)

  # 3. Chỉ số BCTC chuẩn hóa từ VCI (Vietcap qua vnstock)
  pe = fundamental_info.get('pe', 0.0) if fundamental_info else 0.0
  pb = fundamental_info.get('pb', 0.0) if fundamental_info else 0.0
  roe = fundamental_info.get('roe', 0.0) if fundamental_info else 0.0
  eps = fundamental_info.get('eps', 0.0) if fundamental_info else 0.0
  gross_margin = fundamental_info.get('grossMargin', 0.0) if fundamental_info else 0.0
  growth = fundamental_info.get('profitGrowth', 0.0) if fundamental_info else 0.0
  is_audited = fundamental_info.get('isAudited', False) if fundamental_info else False
  report_period = fundamental_info.get('reportPeriod', '') if fundamental_info else ''

  if is_audited and (pe > 0 or pb > 0 or roe != 0 or eps > 0):
    metrics = []
    if pe > 0:
      metrics.append(f'P/E {pe:.1f}x')
    if pb > 0:
      metrics.append(f'P/B {pb:.1f}x')
    if roe != 0:
      metrics.append(f'ROE {roe:.1f}%')
    if eps > 0:
      metrics.append(f'EPS {eps:,.0f}đ')
    if gross_margin > 0:
      metrics.append(f'Biên LN gộp {gross_margin:.1f}%')
    if growth != 0:
      metrics.append(f'Tăng trưởng LN {growth:+.1f}%')
    period_txt = f' kỳ {report_period}' if report_period else ''
    fin_title = f'Chỉ số BCTC{period_txt} mã {ticker}: ' + ' | '.join(metrics)
  else:
    fin_title = (
        f'Chỉ số tài chính mã {ticker}: Dữ liệu BCTC chưa ghi nhận'
        ' đầy đủ từ nguồn dữ liệu.'
    )
  news_records.append({
      'source': 'Chỉ số BCTC (VCI qua vnstock)',
      'badge': 'BÁO CÁO TÀI CHÍNH',
      'badgeColor': BADGE_COLOR_FINANCE,
      'title': fin_title,
      'date': report_period,
      'url': build_vietstock_finance_url(ticker),
      'tickerSpecific': False,
  })

  # 4. VnExpress Kinh Doanh
  if vne_item:
    news_records.append(vne_item)

  # 5. Bảng Giá Thị Trường Realtime
  vol = item.get('stockVol', 0) if item else 0
  buy_vol = item.get('stockBUVol', 0) if item else 0
  sell_vol = item.get('stockSDVol', 0) if item else 0
  f_net = (item.get('buyForeignQtty', 0) - item.get('sellForeignQtty', 0)) if item else 0
  flow_title = (
      f"Khớp lệnh {current_price:,.0f} ({pct_change:+.2f}%) | KL: {vol:,.0f} cp | "
      f"Mua CĐ: {buy_vol:,.0f} vs Bán CĐ: {sell_vol:,.0f} | Khối ngoại ròng: {f_net:,.0f} cp"
  )
  news_records.append({
      'source': 'Bảng Giá Thị Trường Realtime',
      'badge': 'DÒNG TIỀN REALTIME',
      'badgeColor': BADGE_COLOR_MARKET,
      'title': flow_title,
      'date': time.strftime('%d/%m/%Y %H:%M'),
      'url': f'{ENTRADE_BASE_URL}/',
      'tickerSpecific': False,
  })

  # 6. Cổng TTĐT Chính Phủ
  if gov_item:
    news_records.append(gov_item)

  # Lưu cache
  _LIVE_NEWS_CACHE[ticker] = {'time': now, 'data': [dict(r) for r in news_records]}
  return news_records
