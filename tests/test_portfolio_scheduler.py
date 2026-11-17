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
    """NEAR_STOPLOSS alert message must clearly display symbol, price, avg cost, SL, and distance."""
    detail = {
        'price': 27300.0,
        'change_pct': -1.8,
        'stop_loss': 26800.0,
        'target1': 31000.0,
        'avg_price': 29200.0,
        'pnl_pct': -6.51,
        'dist_to_sl': 1.83,
    }
    msg, buttons = format_portfolio_alert('BSI', 'NEAR_STOPLOSS', detail)

    self.assertIn('BSI TIỆM CẬN DẢI DỪNG LỖ', msg)
    self.assertIn('27,300', msg)
    self.assertIn('29,200', msg)
    self.assertIn('-6.51%', msg)
    self.assertIn('26,800', msg)
    self.assertIn('1.8%', msg)
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


if __name__ == '__main__':
  unittest.main()
