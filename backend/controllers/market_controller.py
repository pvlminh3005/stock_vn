"""
Stock RT - Market Controller
Xử lý các endpoint thị trường chung:
- /api/market-regime: Chấm điểm 5 điều kiện Regime (Risk-on, Neutral, Defensive, No-new-risk)
- /api/chart: Lấy nến biểu đồ nhanh
- /api/market-sentiment: Chỉ số tâm lý thị trường Fear & Greed
"""

from backend.data_providers.market_board_provider import get_market_board_data, get_vnindex_summary
from backend.data_providers.entrade_provider import handle_chart_only
from backend.domain.regime import evaluate_market_regime
from backend.domain.risk_engine import calculate_market_fear_greed_index

_MARKET_OVERVIEW_CACHE = {'time': 0, 'data': None}


def handle_chart(ticker, resolution='1D'):
  """Xử lý yêu cầu nến biểu đồ nhanh (/api/chart)."""
  return handle_chart_only(ticker, resolution=resolution)


def handle_market_regime():
  """Xử lý yêu cầu regime thị trường (/api/market-regime)."""
  market_board = get_market_board_data()
  return evaluate_market_regime(market_board)


def handle_market_sentiment():
  """Xử lý yêu cầu tâm lý thị trường (/api/market-sentiment)."""
  market_board = get_market_board_data()
  score, label, color = calculate_market_fear_greed_index(market_board, {}, {})
  return {
      'fearGreedScore': score,
      'fearGreedLabel': label,
      'fearGreedColor': color,
  }


def handle_market_overview():
  """
  Tổng hợp toàn diện dữ liệu thị trường chung:
  - Chỉ số VN-Index thời gian thực (Giá, Thay đổi, %, Khối lượng, Độ rộng Tăng/Giảm/Đứng).
  - Đánh giá Regime thị trường (5 điều kiện, Điểm số, Hệ số phân bổ rủi ro).
  - Chỉ số tâm lý Fear & Greed.
  - Nhận định thị trường hiện tại ngắn gọn và khuyến nghị tỷ trọng danh mục.
  """
  import time
  global _MARKET_OVERVIEW_CACHE
  now = time.time()
  if _MARKET_OVERVIEW_CACHE['data'] and (now - _MARKET_OVERVIEW_CACHE['time'] < 15):
    return _MARKET_OVERVIEW_CACHE['data']

  market_board = get_market_board_data()
  vnindex_summary = get_vnindex_summary()
  regime_info = evaluate_market_regime(market_board)
  sentiment_score, sentiment_label, sentiment_color = calculate_market_fear_greed_index(market_board, {}, {})

  regime = regime_info.get('regime', 'DEFENSIVE')
  score = regime_info.get('score', 0)
  coeff = regime_info.get('coefficient', 0.5)
  conditions = regime_info.get('conditions', [])

  regime_meta = {
      'RISK_ON': {
          'label': 'UPTREND (TÍCH CỰC)',
          'status_color': 'emerald',
          'diagnosis': 'Thị trường vận động tích cực trên các đường MA chủ chốt, dòng tiền lan tỏa diện rộng.',
          'action': 'Duy trì tỷ trọng cổ phiếu cao (70 - 100% NAV). Tiếp tục gồng lãi theo xu hướng, ưu tiên nhóm dẫn dắt.',
          'risk_level': 'Thấp (Risk-On)',
      },
      'NEUTRAL': {
          'label': 'SIDEWAY (PHÂN HÓA)',
          'status_color': 'amber',
          'diagnosis': 'Thị trường trong pha giằng co, dòng tiền phân hóa mạnh giữa các nhóm ngành.',
          'action': 'Duy trì tỷ trọng cổ phiếu trung bình (50 - 70% NAV). Ưu tiên mua tại hỗ trợ, chốt lời từng phần tại kháng cự.',
          'risk_level': 'Trung bình (Neutral)',
      },
      'DEFENSIVE': {
          'label': 'DEFENSIVE (PHÒNG THỦ)',
          'status_color': 'rose',
          'diagnosis': 'VN-Index suy yếu dưới vùng kháng cự, độ rộng thị trường thu hẹp, áp lực điều chỉnh chi phối.',
          'action': 'Hạ tỷ trọng cổ phiếu về 30 - 50% NAV. Tạm dừng mở vị thế mua đuổi, ưu tiên quản trị rủi ro và bảo toàn vốn.',
          'risk_level': 'Cao (Defensive)',
      },
      'NO_NEW_RISK': {
          'label': 'THẬN TRỌNG (RỦI RO CAO)',
          'status_color': 'rose',
          'diagnosis': 'Áp lực bán chiếm ưu thế tuyệt đối, đa số cổ phiếu gãy MA ngắn và trung hạn.',
          'action': 'Ưu tiên giữ tiền mặt (tỷ trọng CP < 20% NAV hoặc 0%). Tuyệt đối không bắt đáy khi chưa có tín hiệu cân bằng.',
          'risk_level': 'Rất cao (No-New-Risk)',
      },
  }

  meta = regime_meta.get(regime, regime_meta['DEFENSIVE'])

  breadth_pct = None
  for c in conditions:
    if 'Top 200' in c.get('name', '') or 'mã trên MA20' in c.get('name', ''):
      detail = c.get('detail', '')
      if '(' in detail and '%)' in detail:
        try:
          breadth_pct = float(detail.split('(')[1].split('%)')[0])
        except Exception:
          pass
      break

  vol = vnindex_summary.get('volume', 0)
  price = vnindex_summary.get('price', 0.0)

  # Ưu tiên lấy GTGD chuẩn từ VPS Datafeed; nếu chưa có thì fallback
  est_val_trillion = vnindex_summary.get('estValueTrillion', 0.0)
  if not est_val_trillion or est_val_trillion <= 0:
    total_board_val = sum(float(item.get('nmTotalTradedValue') or 0.0) for item in market_board.values()) if market_board else 0.0
    if total_board_val > 0:
      est_val_trillion = round(total_board_val / 1e12, 2)
    elif vol > 0:
      est_val_trillion = round((vol * 22000) / 1e12, 2)
    else:
      est_val_trillion = 0.0

  result = {
      'vnindex': {
          'price': price,
          'change': vnindex_summary.get('change', 0.0),
          'changePercent': vnindex_summary.get('changePercent', 0.0),
          'volume': vol,
          'ref': vnindex_summary.get('ref', 0.0),
          'advances': vnindex_summary.get('advances'),
          'declines': vnindex_summary.get('declines'),
          'noChange': vnindex_summary.get('noChange'),
          'source': vnindex_summary.get('source', 'VPS_REALTIME'),
          'estValueTrillion': est_val_trillion,
      },
      'regime': {
          'code': regime,
          'label': meta['label'],
          'statusColor': meta['status_color'],
          'score': score,
          'maxScore': 5,
          'coefficient': coeff,
          'riskLevel': meta['risk_level'],
          'conditions': conditions,
          'asOf': regime_info.get('asOf', ''),
          'breadthPctAboveMa20': breadth_pct,
      },
      'sentiment': {
          'score': sentiment_score,
          'label': sentiment_label,
          'color': sentiment_color,
      },
      'assessment': {
          'diagnosis': meta['diagnosis'],
          'action': meta['action'],
          'shortSummary': f"{meta['diagnosis']} {meta['action']}",
      },
      'updatedAt': int(now),
  }

  _MARKET_OVERVIEW_CACHE['time'] = now
  _MARKET_OVERVIEW_CACHE['data'] = result
  return result

