# tests/test_portfolio_scheduler.py
"""Unit tests for Portfolio Realtime Scanner & Telegram Alert Scheduler.

Verifies:
1. format_portfolio_alert for NEAR_STOPLOSS, STOPLOSS_TRIGGERED, TARGET_TRIGGERED.
2. scan_portfolio_alerts detects holdings tiệm cận dải dừng lỗ (NEAR_STOPLOSS).
3. Deduplication prevents spamming Telegram.
"""

import os
import unittest
from unittest.mock import patch

os.environ['APP_ENV'] = 'testing'

from backend.utils.portfolio_scheduler import (
    format_portfolio_alert,
    scan_portfolio_alerts,
)
from backend.utils.telegram_bot import (
    format_breakout_alert,
    format_actionable_buy_alert,
    format_supertrend_flip_alert,
    format_supertrend_batch_flip_alert,
)
from backend.models import PortfolioTrade
from backend.db.portfolio_db import (
    add_trade,
    reset_all_trades,
    get_alert_state,
)


class TestPortfolioSchedulerAlerts(unittest.TestCase):

  def setUp(self):
    reset_all_trades()

  def tearDown(self):
    reset_all_trades()

  def test_format_portfolio_alert_near_stoploss(self):
    """NEAR_STOPLOSS alert message must clearly display symbol, price, avg cost, SL, order date, and distance."""
    detail = {
        'price': 27300.0,
        'change_pct': -1.8,
        'stop_loss': 26800.0,
        'target1': 31000.0,
        'avg_price': 29200.0,
        'pnl_pct': -6.51,
        'dist_to_sl': 1.83,
        'trade_date': '2026-11-13',
        'signal_date': '2026-11-03',
        'holding_bars': 10,
    }
    msg, buttons = format_portfolio_alert('BSI', 'NEAR_STOPLOSS', detail)

    self.assertIn('BSI TIỆM CẬN DẢI DỪNG LỖ', msg)
    self.assertIn('27,300', msg)
    self.assertIn('29,200', msg)
    self.assertIn('-6.51%', msg)
    self.assertIn('26,800', msg)
    self.assertIn('1.8%', msg)
    self.assertIn('2026-11-13', msg)
    self.assertIn('Ngày vào lệnh', msg)
    self.assertEqual(len(buttons), 2)
    self.assertIn('BSI', buttons[0]['text'])

  @patch('backend.utils.portfolio_scheduler.send_telegram_message')
  @patch('backend.utils.portfolio_scheduler.handle_stock_detail')
  @patch('backend.utils.portfolio_scheduler.get_market_board_data')
  def test_scan_triggers_near_stoploss_alert(self, mock_board, mock_detail, mock_send):
    """When a held stock is within 2% of S1 or down -6%, trigger NEAR_STOPLOSS."""
    mock_send.return_value = True

    # Add a holding trade for BSI (bought at 29,200)
    add_trade(PortfolioTrade(
        symbol='BSI',
        order_type='BUY',
        volume=200,
        price=29200.0,
        trade_date='2026-11-13',
        status='HOLDING'
    ))

    # Mock market board: current price is 27,300 (-1.8%)
    mock_board.return_value = {
        'BSI': {
            'matchedPrice': 27300.0,
            'priceChangePercent': -1.8,
        }
    }

    # Mock stock detail: support S1 is 26,800 (distance to S1 is ~1.83% < 2.0%)
    mock_detail.return_value = {
        'technicals': {'support': 26800.0, 'resistance': 31000.0},
        'decisionEngine': {'ribbon_status': 'VÙNG XANH'},
    }

    scan_portfolio_alerts()

    # Verify send_telegram_message was called with NEAR_STOPLOSS alert
    mock_send.assert_called_once()
    args, kwargs = mock_send.call_args
    sent_msg = args[0]
    self.assertIn('BSI TIỆM CẬN DẢI DỪNG LỖ', sent_msg)
    self.assertIn('27,300', sent_msg)
    self.assertIn('-6.51%', sent_msg)
    self.assertIn('2026-11-13', sent_msg)
    self.assertIn('Ngày vào lệnh', sent_msg)

    # Check alert state was updated to NEAR_STOPLOSS
    state = get_alert_state('BSI')
    self.assertEqual(state.get('last_alert_type'), 'NEAR_STOPLOSS')

    # Scanning again immediately should NOT trigger duplicate Telegram alert
    mock_send.reset_mock()
    scan_portfolio_alerts()
    mock_send.assert_not_called()

  @patch('backend.utils.portfolio_scheduler.send_telegram_message')
  @patch('backend.utils.portfolio_scheduler.handle_stock_detail')
  @patch('backend.utils.portfolio_scheduler.get_market_board_data')
  def test_recovery_to_normal_state(self, mock_board, mock_detail, mock_send):
    """When price bounces back safely (dist > 2.5% and pnl > -4.5%), state resets to NORMAL."""
    mock_send.return_value = True

    add_trade(PortfolioTrade(
        symbol='BSI',
        order_type='BUY',
        volume=200,
        price=29200.0,
        trade_date='2026-11-13',
        status='HOLDING'
    ))

    # First pass: near stop loss
    mock_board.return_value = {'BSI': {'matchedPrice': 27300.0, 'priceChangePercent': -1.8}}
    mock_detail.return_value = {'technicals': {'support': 26800.0, 'resistance': 31000.0}}
    scan_portfolio_alerts()
    self.assertEqual(get_alert_state('BSI').get('last_alert_type'), 'NEAR_STOPLOSS')

    # Second pass: price recovers to 28,500 (dist to S1 is ~6.3%, pnl is -2.4%)
    mock_board.return_value = {'BSI': {'matchedPrice': 28500.0, 'priceChangePercent': 2.5}}
    scan_portfolio_alerts()
    self.assertEqual(get_alert_state('BSI').get('last_alert_type'), 'NORMAL')

  def test_screener_alerts_include_signal_date(self):
    """Screener breakout & actionable buy alerts must display 'Ngày phát lệnh'."""
    stock = {
        'symbol': 'FPT',
        'name': 'Công ty Cổ phần FPT',
        'price': 54200.0,
        'changePct': 3.5,
        'volRunRate': 2.1,
        'buyRatio': 68.0,
        'net_rr': 2.2,
        'support': 52000.0,
        'target1': 58000.0,
        'target2': 62000.0,
        'stop_loss': 51000.0,
        'signal_date': '2026-11-17',
    }
    msg_breakout, _ = format_breakout_alert(stock)
    self.assertIn('Ngày phát lệnh', msg_breakout)
    self.assertIn('2026-11-17', msg_breakout)

    msg_buy, _ = format_actionable_buy_alert(stock)
    self.assertIn('Ngày phát lệnh', msg_buy)
    self.assertIn('2026-11-17', msg_buy)

  def test_format_supertrend_flip_alert(self):
    """Supertrend flip alert formats correctly for both Chờ Trend (sideway) and Lật Xanh (bullish)."""
    stock_wait = {
        'symbol': 'DBC',
        'name': 'Dabaco',
        'price': 16200.0,
        'changePct': 3.85,
        'signal_date': '2026-11-09',
        'trigger_price': 16000.0,
        'support': 15100.0,
        'resistance': 16800.0,
        'adx': 16.5,
        'vol_run_rate': 2.5,
        'buy_ratio': 62.0,
    }
    msg_wait, btns_wait = format_supertrend_flip_alert(stock_wait, is_sideway=True)
    self.assertIn('CHUYỂN DẢI CHỜ TREND', msg_wait)
    self.assertIn('DBC', msg_wait)
    self.assertIn('16,200', msg_wait)
    self.assertIn('2026-11-09', msg_wait)
    self.assertIn('16,000', msg_wait)
    self.assertIn('15,100', msg_wait)
    self.assertIn('16,800', msg_wait)
    self.assertEqual(len(btns_wait), 2)

    stock_bull = {
        'symbol': 'SSI',
        'price': 28500.0,
        'changePct': 4.2,
        'signal_date': '2026-11-17',
        'trigger_price': 28000.0,
        'support': 27000.0,
        'resistance': 30500.0,
        'adx': 25.4,
        'vol_run_rate': 3.1,
        'buy_ratio': 71.0,
    }
    msg_bull, _ = format_supertrend_flip_alert(stock_bull, is_sideway=False)
    self.assertIn('LẬT DẢI XANH (BULLISH)', msg_bull)
    self.assertIn('SSI', msg_bull)
    self.assertIn('28,500', msg_bull)

  def test_format_supertrend_batch_flip_alert(self):
    """Batch alert lists multiple stocks when >= 3 flip at once."""
    flips = [
        {'symbol': 'DBC', 'price': 16200, 'changePct': 3.85, 'is_sideway': True, 'signal_date': '2026-11-09'},
        {'symbol': 'SSI', 'price': 28500, 'changePct': 4.2, 'is_sideway': False, 'signal_date': '2026-11-09'},
        {'symbol': 'HPG', 'price': 27000, 'changePct': 2.8, 'is_sideway': False, 'signal_date': '2026-11-09'},
    ]
    msg, btns = format_supertrend_batch_flip_alert(flips)
    self.assertIn('3 MÃ LẬT DẢI SUPERTREND', msg)
    self.assertIn('DBC', msg)
    self.assertIn('SSI', msg)
    self.assertIn('HPG', msg)

  @patch('backend.controllers.screener_controller.send_telegram_message')
  @patch('backend.domain.technicals.analyze_technicals_and_scoring')
  @patch('backend.data_providers.entrade_provider.fetch_chart_data')
  @patch('backend.controllers.screener_controller.get_dynamic_liquid_universe')
  @patch('backend.controllers.screener_controller.get_market_board_data')
  def test_scan_supertrend_flip_alerts_triggers_alert(
      self, mock_board, mock_univ, mock_chart, mock_tech, mock_send
  ):
    """Scanner detects SuperTrend flip on a liquid stock and alerts Telegram."""
    from backend.controllers.screener_controller import scan_supertrend_flip_alerts
    mock_send.return_value = True

    mock_board.return_value = {
        'DBC': {
            'matchedPrice': 16200.0,
            'priceChangePercent': 3.85,
            'nmTotalTradedValue': 55_000_000_000,
            'totalVolume': 3400000,
        }
    }
    mock_univ.return_value = ['DBC']
    mock_chart.return_value = {'c': [15.5] * 30, 't': [1700000000] * 30}
    mock_tech.return_value = {
        'ma20': 15800.0,
        'support': 15100.0,
        'resistance': 16800.0,
        'volMa20': 1500000,
        'adx': {'adx': 16.5, 'is_sideway': True},
        'supertrend': {
            'isFlipBuy': True,
            'isBullish': True,
            'signalDate': '2026-11-17',
            'brokenBand': 16000.0,
            'supportBand': 15100.0,
        }
    }

    scan_supertrend_flip_alerts()
    mock_send.assert_called_once()
    sent_msg = mock_send.call_args[0][0]
    self.assertIn('CHUYỂN DẢI CHỜ TREND', sent_msg)
    self.assertIn('DBC', sent_msg)
    self.assertIn('16,200', sent_msg)

    # Calling again should NOT re-alert due to 24h deduplication
    mock_send.reset_mock()
    scan_supertrend_flip_alerts()
    mock_send.assert_not_called()


if __name__ == '__main__':
  unittest.main()
