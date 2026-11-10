"""
Unit & Integration Tests - Portfolio DB Layer
Kiểm thử toàn diện tầng cơ sở dữ liệu MongoDB Atlas (Dev/Test Environment):
- add_trade, get_all_trade_models, get_all_trades
- delete_trade (hỗ trợ ObjectId và string ID, tự dọn alert_states)
- get_active_holding_symbols (distinct với filter active holdings)
- save_setting, get_setting (PortfolioSetting)
- get_alert_state, save_alert_state (AlertState)
- is_alert_already_sent, record_alert_sent (TelegramAlertLog)
- save_telegram_sent_log, get_telegram_sent_logs (TelegramSentLog)
- reset_all_trades (Prod safety check)
"""

import os
import unittest

os.environ['APP_ENV'] = 'testing'

from backend.models import (
    PortfolioTrade,
    PortfolioSetting,
    AlertState,
)
from backend.db.portfolio_db import (
    add_trade,
    get_all_trade_models,
    get_all_trades,
    delete_trade,
    get_active_holding_symbols,
    reset_all_trades,
    save_setting,
    get_setting,
    get_alert_state,
    save_alert_state,
    is_alert_already_sent,
    record_alert_sent,
    save_telegram_sent_log,
    get_telegram_sent_logs,
)


class TestPortfolioDBLayer(unittest.TestCase):
    """Kiểm thử tầng Portfolio DB."""

    def setUp(self):
        reset_all_trades()

    def tearDown(self):
        reset_all_trades()

    def test_trade_crud_with_typed_models(self):
        # 1. Thêm bằng Typed PortfolioTrade Model
        trade1 = PortfolioTrade(
            symbol='MWG',
            order_type=PortfolioTrade.ORDER_BUY,
            volume=1000,
            price=65000.0,
            trade_date='2026-11-09',
            note='Mua gia tăng'
        )
        trade1_id = add_trade(trade1)
        self.assertIsNotNone(trade1_id)

        # 2. Lấy danh sách dạng typed objects
        trade_models = get_all_trade_models()
        self.assertEqual(len(trade_models), 1)
        self.assertIsInstance(trade_models[0], PortfolioTrade)
        self.assertEqual(trade_models[0].symbol, 'MWG')
        self.assertEqual(trade_models[0].price, 65000.0)

        # 3. Lấy danh sách dạng dict
        trades_dict = get_all_trades()
        self.assertEqual(len(trades_dict), 1)
        self.assertEqual(trades_dict[0]['symbol'], 'MWG')
        self.assertEqual(trades_dict[0]['id'], trade1_id)

        # 4. Kiểm tra active holding symbols
        active_symbols = get_active_holding_symbols()
        self.assertEqual(active_symbols, ['MWG'])

        # 5. Xóa trade
        deleted = delete_trade(trade1_id)
        self.assertTrue(deleted)
        self.assertEqual(len(get_all_trade_models()), 0)

    def test_delete_trade_cleans_up_alert_state(self):
        """Xóa lệnh BUY cuối cùng của 1 mã thì tự dọn alert_states tương ứng."""
        sym = 'TCB'
        t_id = add_trade(PortfolioTrade(symbol=sym, order_type='BUY', volume=500, price=24000.0))

        # Lưu alert state cho mã này
        save_alert_state(sym, AlertState(symbol=sym, last_alert_type='BUY_BREAKOUT'))
        st = get_alert_state(sym)
        self.assertEqual(st.get('last_alert_type'), 'BUY_BREAKOUT')

        # Xóa lệnh BUY
        delete_trade(t_id)

        # Alert state của mã đó phải được dọn sạch về mặc định
        st_after = get_alert_state(sym)
        self.assertEqual(st_after.get('last_alert_type'), '')

    def test_settings_crud(self):
        # Lưu setting qua key hằng số
        ok = save_setting(PortfolioSetting.KEY_TOTAL_NAV, '450000000')
        self.assertTrue(ok)

        val = get_setting(PortfolioSetting.KEY_TOTAL_NAV, default='0')
        self.assertEqual(val, '450000000')

    def test_telegram_deduplication_logs(self):
        import time
        key = f'TEST_ALERT_KEY_{int(time.time() * 1000)}'
        self.assertFalse(is_alert_already_sent(key, min_interval_seconds=3600))

        # Ghi nhận đã gửi
        record_alert_sent(key, preview='Test Alert')
        self.assertTrue(is_alert_already_sent(key, min_interval_seconds=3600))

    def test_telegram_sent_logs(self):
        log_id = save_telegram_sent_log(
            alert_type='PORTFOLIO_ALERT',
            title='Thông báo chốt lời HPG',
            stocks=[{'symbol': 'HPG', 'price': 29.5, 'action': 'CHỐT LỜI'}]
        )
        self.assertTrue(bool(log_id))

        logs = get_telegram_sent_logs(limit=5)
        self.assertGreater(len(logs), 0)
        self.assertEqual(logs[0]['alert_type'], 'PORTFOLIO_ALERT')


if __name__ == '__main__':
    unittest.main()
