"""
Stock RT - Stock Controller
Xử lý logic chi tiết cổ phiếu (/api/stock):
Tổng hợp dữ liệu giá realtime từ SSI, nến lịch sử từ Entrade,
hồ sơ tài chính chuẩn hóa VCI, phân tích kỹ thuật, tin tức và báo cáo định lượng rủi ro.
"""

import time

from backend.constants.config import DAILY_HISTORY_DAYS
from backend.utils.ohlc_helpers import format_candles, merge_live_candle_to_chart_data
from backend.data_providers.market_board_provider import get_market_board_data
from backend.data_providers.entrade_provider import fetch_chart_data, fetch_intraday_snapshot
from backend.data_providers.news_provider import fetch_live_multi_sources
from backend.domain.valuation import get_fundamental_profile
from backend.domain.technicals import analyze_technicals_and_scoring
from backend.domain.regime import evaluate_market_regime
from backend.domain.risk_engine import evaluate_securities_risk_engine
from backend.domain.decision_engine import evaluate_unified_decision


def handle_stock_detail(ticker, resolution='1D'):
  """Tổng hợp toàn bộ thông tin mã cổ phiếu (bảng giá, nến, cơ bản, kỹ thuật, tin tức, rủi ro)."""
  ticker = ticker.strip().upper()
  market_board = get_market_board_data()
  board_item = market_board.get(ticker, {})

  # Nếu bảng giá ngoài phiên rỗng -> Tự động Fallback sang Entrade Intraday Live 1-min
  if not board_item or board_item.get('matchedPrice', 0) <= 0:
    entrade_snap = fetch_intraday_snapshot(ticker)
    if entrade_snap and entrade_snap.get('matchedPrice', 0) > 0:
      board_item = entrade_snap

  # Toàn bộ phân tích (RSI, MA, ATR, hỗ trợ/kháng cự, kế hoạch T+) luôn chạy trên nến NGÀY;
  # resolution chỉ quyết định dữ liệu nến vẽ biểu đồ.
  chart_data = fetch_chart_data(ticker, days=DAILY_HISTORY_DAYS, resolution='1D', ssi_item=board_item)
  # Ghép cây nến realtime tại thời điểm search từ Entrade vào chuỗi nến ngày
  chart_data = merge_live_candle_to_chart_data(chart_data, board_item, resolution='1D')

  t_list = chart_data.get('t', [])
  h_list = chart_data.get('h', [])
  l_list = chart_data.get('l', [])
  c_list = chart_data.get('c', [])
  v_list = chart_data.get('v', [])

  if not c_list:
    raise ValueError(f'Không tìm thấy dữ liệu cho mã {ticker}')

  scale = 1000 if c_list[-1] < 1000 else 1
  latest_c = c_list[-1] * scale
  prev_c = (c_list[-2] * scale) if len(c_list) > 1 else latest_c

  # Dữ liệu realtime từ Entrade Market Board nếu có phiên đang mở
  if board_item and board_item.get('matchedPrice', 0) > 0:
    current_price = board_item['matchedPrice']
    price_change = board_item.get('priceChange', current_price - prev_c)
    pct_change = board_item.get(
        'priceChangePercent',
        round((price_change / prev_c) * 100, 2) if prev_c else 0,
    )
    company_name = board_item.get(
        'companyNameVi', board_item.get('clientName', f'Cổ phiếu {ticker}')
    )
    exchange = board_item.get('exchange', 'HOSE').upper()
    band = 0.07 if exchange == 'HOSE' else (0.10 if exchange == 'HNX' else 0.15)
    ceiling = board_item.get('ceiling') or round(current_price * (1 + band))
    floor = board_item.get('floor') or round(current_price * (1 - band))
    ref_price = board_item.get('refPrice', prev_c)
    highest_price = board_item.get('highest') or (h_list[-1] * scale if h_list else current_price)
    lowest_price = board_item.get('lowest') or (l_list[-1] * scale if l_list else current_price)
    total_vol = board_item.get('stockVol', v_list[-1] if v_list else 0)
    foreign_net = board_item.get('buyForeignQtty', 0) - board_item.get(
        'sellForeignQtty', 0
    )
  elif board_item and board_item.get('refPrice', 0) > 0:
    ref_price = board_item['refPrice']
    current_price = board_item.get('matchedPrice') or ref_price
    price_change = board_item.get('priceChange', current_price - ref_price)
    pct_change = board_item.get('priceChangePercent', 0)
    company_name = board_item.get(
        'companyNameVi', board_item.get('clientName', f'Cổ phiếu {ticker}')
    )
    exchange = board_item.get('exchange', 'HOSE').upper()
    band = 0.07 if exchange == 'HOSE' else (0.10 if exchange == 'HNX' else 0.15)
    ceiling = board_item.get('ceiling') or round(ref_price * (1 + band))
    floor = board_item.get('floor') or round(ref_price * (1 - band))
    highest_price = board_item.get('highest') or (h_list[-1] * scale if h_list else current_price)
    lowest_price = board_item.get('lowest') or (l_list[-1] * scale if l_list else current_price)
    total_vol = board_item.get('stockVol', v_list[-1] if v_list else 0)
    foreign_net = board_item.get('buyForeignQtty', 0) - board_item.get(
        'sellForeignQtty', 0
    )
  else:
    current_price = latest_c
    price_change = latest_c - prev_c
    pct_change = round((price_change / prev_c) * 100, 2) if prev_c else 0
    company_name = f'Cổ phiếu {ticker}'
    exchange = 'HOSE'
    band = 0.07
    ref_price = prev_c
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

  # Định dạng nến cho Lightweight Charts (TradingView)
  if resolution == '1D':
    candles_series = format_candles(chart_data, resolution='1D')
  else:
    alt_data = fetch_chart_data(ticker, resolution=resolution, ssi_item=board_item)
    alt_data = merge_live_candle_to_chart_data(alt_data, board_item, resolution=resolution)
    candles_series = format_candles(alt_data, resolution=resolution)

  # Cơ bản doanh nghiệp
  fundamental_info = get_fundamental_profile(ticker, current_price)
  if company_name == f'Cổ phiếu {ticker}' and fundamental_info.get('name'):
    company_name = fundamental_info['name']

  # Phân tích kỹ thuật & Chấm điểm
  market_regime = evaluate_market_regime(market_board)
  analysis = analyze_technicals_and_scoring(
      chart_data, board_item, current_price, fundamental_info, ticker=ticker, exchange=exchange,
      regime=market_regime,
  )

  date_str = (
      time.strftime('%d/%m/%Y', time.localtime(t_list[-1]))
      if t_list
      else time.strftime('%d/%m/%Y')
  )
  sector_name = fundamental_info.get('sector', 'Thị trường')
  news_list = fetch_live_multi_sources(
      ticker, board_item, fundamental_info, current_price, pct_change, sector_name
  )

  risk_engine_report = evaluate_securities_risk_engine(
      ticker=ticker,
      sector=sector_name,
      current_price=current_price,
      fundamental_info=fundamental_info,
      technical_info=analysis,
      ssi_item=board_item,
      ssi_board=market_board,
      news_list=news_list,
  )

  # Tạo future_outlook tương thích ngược trực tiếp từ risk_engine_report (tránh tính toán lặp)
  fg = risk_engine_report.get('marketFlow', {})
  act = risk_engine_report.get('actionConclusion', {})
  scen = risk_engine_report.get('scenarioMatrix', {})
  bull_scen = scen.get('bullCase', {})
  bear_scen = scen.get('bearCase', {})
  future_outlook = {
      'consensus': act.get('status', 'THEO DÕI').upper(),
      'consensusColor': act.get('statusColor', 'slate'),
      'confidence': f"Fear & Greed: {fg.get('fearGreedScore', 50)}/100 ({fg.get('fearGreedLabel', 'Cân bằng')})",
      'macroSummary': f"[{risk_engine_report.get('macroSector', {}).get('environment', 'Chưa đánh giá')}] {risk_engine_report.get('macroSector', {}).get('macroImpact', '')}",
      'fundamentalSummary': f"{risk_engine_report.get('fundamentalRisk', {}).get('growthQuality', '')} {risk_engine_report.get('fundamentalRisk', {}).get('governanceDilutionRisk', '')}",
      'flowSummary': f"{fg.get('foreignFlow', '')} {fg.get('sentimentLiquidity', '')}",
      'bullScenario': f"Mục tiêu {bull_scen.get('targetDisplay', '')}. Kích hoạt: {bull_scen.get('trigger', '')}",
      'bearScenario': f"{bear_scen.get('supportDisplay', '')}. Rủi ro kích hoạt: {bear_scen.get('trigger', '')}",
      'tailLockRisk': risk_engine_report.get('tailLockRisk', False),
      'tailLockReasons': risk_engine_report.get('tailLockReasons', []),
      'dcScore': risk_engine_report.get('dcScore', 80),
      'dcRating': risk_engine_report.get('dcRating', 'CAO'),
      'bottomLine': risk_engine_report.get('bottomLine', ''),
      'riskEngine': risk_engine_report,
  }

  # Động cơ ra quyết định trung tâm VSR Unified Decision Engine
  decision_output = evaluate_unified_decision(
      ticker=ticker,
      exchange=exchange,
      current_price=current_price,
      fundamental_info=fundamental_info,
      technical_info=analysis,
      regime=market_regime,
      risk_engine_report=risk_engine_report,
      resolution=resolution,
  )

  # Lịch sử VCI chỉ dùng nội bộ để định giá, không trả về giao diện
  fundamental_info.pop('vciHistory', None)

  return {
      'code': ticker,
      'name': company_name,
      'exchange': exchange,
      'date': date_str,
      'price': current_price,
      'prevPrice': ref_price,
      'priceChange': price_change,
      'percentChange': pct_change,
      'highest': highest_price,
      'lowest': lowest_price,
      'highPrice': highest_price,
      'lowPrice': lowest_price,
      'ceiling': ceiling,
      'floor': floor,
      'refPrice': ref_price,
      'totalVolume': total_vol,
      'foreignNet': foreign_net,
      'fundamentals': fundamental_info,
      'technicals': analysis,
      'candles': candles_series,
      'news': news_list,
      'futureOutlook': future_outlook,
      'riskEngine': risk_engine_report,
      'decisionEngine': decision_output,
  }

