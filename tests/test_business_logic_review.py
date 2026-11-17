"""
Unit test suite verifying the refined business logic:
1. Screener Engine Market Regime Kill-Switch (NO_NEW_RISK blocks all new buys).
2. Screener Engine Defensive Regime Sizing (DEFENSIVE scales down alloc_pct by 50%).
3. Screener Engine Afternoon Breakout Volume Filter (low volume waits confirmation).
4. Screener Engine Afternoon Pullback Low Volume Preservation (cạn cung test nền).
5. Portfolio Bundler Market Regime Allocation (88% RISK_ON, 55% DEFENSIVE/NO_NEW_RISK, 75% NEUTRAL).
"""

import unittest
from unittest.mock import patch
import datetime

from backend.domain.screener_engine import evaluate_single_stock_opportunity
from backend.domain.portfolio_bundler import generate_portfolio_bundle


class TestBusinessLogicReview(unittest.TestCase):

  def setUp(self):
    self.now_afternoon = datetime.datetime(2026, 11, 16, 14, 0, tzinfo=datetime.timezone(datetime.timedelta(hours=7)))

  @patch('backend.domain.screener_engine.fetch_chart_data')
  @patch('backend.domain.screener_engine.analyze_technicals_and_scoring')
  def test_screener_kill_switch_no_new_risk(self, mock_tech, mock_chart):
    """Khi thị trường rơi vào NO_NEW_RISK, Kill-Switch ngắt mạch toàn bộ (MARKET_RISK, allocPct=0)."""
    mock_chart.return_value = {'c': [10400, 10500], 'v': [1500000], 'h': [10550], 'l': [10400]}
    mock_tech.return_value = {
        'atr14': 300,
        'support': 10400,
        'resistance': 11500,
        'resistance2': 12000,
        'supertrend': {'isBullish': True, 'isFlipBuy': True},
        'ema9': 10450,
        'volMa20': 1500000,
        'relativeStrength': {'rsScore': 80},
    }
    market_item = {
        'matchedPrice': 10500,
        'refPrice': 10400,
        'highest': 10550,
        'lowest': 10400,
        'stockVol': 1800000,
        'nmTotalTradedValue': 20000000000,
        'buyVol': 1200000,
        'sellVol': 600000,
        'exchange': 'HOSE',
    }

    res = evaluate_single_stock_opportunity('SSI', market_item=market_item, regime={'regime': 'NO_NEW_RISK'}, now=self.now_afternoon)
    self.assertIsNotNone(res)
    self.assertEqual(res['actionStatus'], 'MARKET_RISK')
    self.assertEqual(res['actionLabel'], '⚠️ THỊ TRƯỜNG RỦI RO')
    self.assertEqual(res['allocPct'], 0)
    self.assertIn('Không giải ngân', res['allocAdvice'])

  @patch('backend.domain.screener_engine.fetch_chart_data')
  @patch('backend.domain.screener_engine.analyze_technicals_and_scoring')
  def test_screener_defensive_regime_scales_down_alloc(self, mock_tech, mock_chart):
    """Khi thị trường ở chế độ DEFENSIVE, không chặn mua nhưng tự động hạ 50% quy mô vị thế."""
    mock_chart.return_value = {'c': [10400, 10500], 'v': [1500000], 'h': [10550], 'l': [10400]}
    mock_tech.return_value = {
        'atr14': 300,
        'support': 10400,
        'resistance': 11500,
        'resistance2': 12000,
        'supertrend': {'isBullish': True, 'isFlipBuy': True},
        'ema9': 10450,
        'volMa20': 1500000,
        'relativeStrength': {'rsScore': 80},
    }
    market_item = {
        'matchedPrice': 10500,
        'refPrice': 10400,
        'highest': 10550,
        'lowest': 10400,
        'stockVol': 1800000,
        'nmTotalTradedValue': 20000000000,
        'buyVol': 1200000,
        'sellVol': 600000,
        'exchange': 'HOSE',
    }

    res = evaluate_single_stock_opportunity('SSI', market_item=market_item, regime={'regime': 'DEFENSIVE'}, now=self.now_afternoon)
    self.assertIsNotNone(res)
    self.assertEqual(res['actionStatus'], 'ACTIONABLE_LEADER_BUY')
    self.assertEqual(res['allocPct'], 17)  # 35 * 0.5 = 17
    self.assertIn('Thị trường Phòng thủ: giảm 50% size', res['allocAdvice'])

  @patch('backend.domain.screener_engine.fetch_chart_data')
  @patch('backend.domain.screener_engine.analyze_technicals_and_scoring')
  def test_screener_afternoon_breakout_low_volume_waits(self, mock_tech, mock_chart):
    """Cổ phiếu breakout phiên chiều nhưng thiếu vol (< 0.85 TB20) phải chờ xác nhận dòng tiền."""
    mock_chart.return_value = {'c': [10400, 10500], 'v': [1500000], 'h': [10550], 'l': [10400]}
    mock_tech.return_value = {
        'atr14': 300,
        'support': 10400,
        'resistance': 11500,
        'resistance2': 12000,
        'supertrend': {'isBullish': True, 'isFlipBuy': True},
        'ema9': 10450,
        'volMa20': 1500000,
        'relativeStrength': {'rsScore': 50},  # Không phải siêu cổ leader
    }
    # stockVol 600k / volMa20 1500k -> vol_run_rate ~ 0.48 (< 0.85)
    market_item = {
        'matchedPrice': 10500,
        'refPrice': 10400,
        'highest': 10550,
        'lowest': 10400,
        'stockVol': 600000,
        'nmTotalTradedValue': 6500000000,
        'buyVol': 350000,
        'sellVol': 250000,
        'exchange': 'HOSE',
        'sector': 'Dệt may',
    }

    res = evaluate_single_stock_opportunity('TCM', market_item=market_item, regime={'regime': 'NEUTRAL'}, now=self.now_afternoon)
    self.assertIsNotNone(res)
    self.assertEqual(res['actionStatus'], 'WAITING_CONFIRMATION')
    self.assertEqual(res['actionLabel'], '⏳ CHỜ VOL XÁC NHẬN')

  @patch('backend.domain.screener_engine.fetch_chart_data')
  @patch('backend.domain.screener_engine.analyze_technicals_and_scoring')
  def test_screener_afternoon_breakout_high_volume_buys_ready(self, mock_tech, mock_chart):
    """Cổ phiếu breakout phiên chiều có nổ vol đạt chuẩn (>= 0.85 TB20) được xác nhận MUA NGAY."""
    mock_chart.return_value = {'c': [10400, 10500], 'v': [1500000], 'h': [10550], 'l': [10400]}
    mock_tech.return_value = {
        'atr14': 300,
        'support': 10400,
        'resistance': 11500,
        'resistance2': 12000,
        'supertrend': {'isBullish': True, 'isFlipBuy': True},
        'ema9': 10450,
        'volMa20': 1500000,
        'relativeStrength': {'rsScore': 50},
    }
    # stockVol 1.8M / volMa20 1.5M -> vol_run_rate ~ 1.44 (>= 0.85)
    market_item = {
        'matchedPrice': 10500,
        'refPrice': 10400,
        'highest': 10550,
        'lowest': 10400,
        'stockVol': 1800000,
        'nmTotalTradedValue': 20000000000,
        'buyVol': 1000000,
        'sellVol': 800000,
        'exchange': 'HOSE',
        'sector': 'Dệt may',
    }

    res = evaluate_single_stock_opportunity('TCM', market_item=market_item, regime={'regime': 'NEUTRAL'}, now=self.now_afternoon)
    self.assertIsNotNone(res)
    self.assertEqual(res['actionStatus'], 'BUY_READY')
    self.assertEqual(res['actionLabel'], '🟢 MUA NGAY')

  @patch('backend.domain.portfolio_bundler.evaluate_market_regime')
  @patch('backend.domain.portfolio_bundler.get_market_board_data')
  def test_portfolio_bundler_regime_allocation_rates(self, mock_board, mock_regime):
    """Kiểm tra Portfolio Bundler tự động co giãn tỷ lệ tiền mặt / giải ngân theo đúng 4 chế độ thị trường."""
    mock_board.return_value = {
        'HPG': {'stockType': 's', 'stockSymbol': 'HPG', 'matchedPrice': 25000, 'refPrice': 24500, 'nmTotalTradedValue': 50000000000, 'companyNameVi': 'Tập đoàn Hòa Phát'},
        'MBB': {'stockType': 's', 'stockSymbol': 'MBB', 'matchedPrice': 22000, 'refPrice': 21800, 'nmTotalTradedValue': 40000000000, 'companyNameVi': 'Ngân hàng MB'},
    }

    test_cases = [
        ('RISK_ON', 88),
        ('DEFENSIVE', 55),
        ('NO_NEW_RISK', 55),
        ('NEUTRAL', 75),
    ]

    for regime_name, expected_rate in test_cases:
      mock_regime.return_value = {'regime': regime_name, 'score': 3, 'recommendation': 'Thị trường'}
      bundle = generate_portfolio_bundle(capital=50_000_000)
      self.assertEqual(bundle['regime']['allocationRate'], expected_rate, f"Regime {regime_name} expected rate {expected_rate}")


if __name__ == '__main__':
  unittest.main()

