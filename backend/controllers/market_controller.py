"""
Stock RT - Market Controller
Xử lý các endpoint thị trường chung:
- /api/market-regime: Chấm điểm 5 điều kiện Regime (Risk-on, Neutral, Defensive, No-new-risk)
- /api/chart: Lấy nến biểu đồ nhanh
- /api/market-sentiment: Chỉ số tâm lý thị trường Fear & Greed
"""

from backend.data_providers.ssi_provider import get_ssi_board_data
from backend.data_providers.entrade_provider import handle_chart_only
from backend.domain.regime import evaluate_market_regime
from backend.domain.risk_engine import calculate_market_fear_greed_index


def handle_chart(ticker, resolution='1D'):
  """Xử lý yêu cầu nến biểu đồ nhanh (/api/chart)."""
  return handle_chart_only(ticker, resolution=resolution)


def handle_market_regime():
  """Xử lý yêu cầu regime thị trường (/api/market-regime)."""
  ssi_board = get_ssi_board_data()
  return evaluate_market_regime(ssi_board)


def handle_market_sentiment():
  """Xử lý yêu cầu tâm lý thị trường (/api/market-sentiment)."""
  ssi_board = get_ssi_board_data()
  score, label, color = calculate_market_fear_greed_index(ssi_board, {}, {})
  return {
      'fearGreedScore': score,
      'fearGreedLabel': label,
      'fearGreedColor': color,
  }
