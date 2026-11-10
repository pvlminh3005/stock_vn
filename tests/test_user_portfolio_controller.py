"""
Unit & Integration Tests - User Portfolio Controller
Kiểm thử toàn diện các hàm điều phối logic danh mục người dùng:
- handle_add_trade (Typed Model + Dict, Validation, Edge cases)
- handle_delete_trade
- handle_save_settings (Total NAV, validation)
- handle_get_portfolio (VWAP, Realized PnL, Unrealized PnL, Purchasing Power)
- handle_reset_portfolio
"""

import os
import unittest

os.environ['APP_ENV'] = 'testing'

from backend.models import PortfolioTrade, PortfolioSetting
from backend.controllers.user_portfolio_controller import (
    handle_add_trade,
    handle_delete_trade,
    handle_save_settings,
    handle_get_portfolio,
    handle_reset_portfolio,
)
from backend.db.portfolio_db import get_all_trades, reset_all_trades


class TestUserPortfolioController(unittest.TestCase):
    """Kiểm thử Controller Quản lý Danh mục người dùng."""

    def setUp(self):
        """Dọn dẹp dữ liệu danh mục trước mỗi test case."""
        reset_all_trades()

    def tearDown(self):
        """Dọn dẹp sau khi chạy test case."""
        reset_all_trades()

    def test_add_trade_via_dict_and_model(self):
        # 1. Thêm bằng dict chuẩn
        res1 = handle_add_trade({
            'symbol': 'HPG',
            'order_type': 'BUY',
            'volume': 1000,
            'price': 28.5,  # Tự format sang 28500.0
            'trade_date': '2026-11-09',
            'note': 'Gom vùng nền'
        })
        self.assertTrue(res1['success'])
        self.assertIn('id', res1)
        self.assertIn('HPG', res1['message'])

        # 2. Thêm bằng typed PortfolioTrade Object trực tiếp
        trade_obj = PortfolioTrade(
            symbol='FPT',
            order_type='BUY',
            volume=500,
            price=120000.0,
            trade_date='2026-11-09'
        )
        res2 = handle_add_trade(trade_obj)
        self.assertTrue(res2['success'])
        self.assertIn('FPT', res2['message'])

        # Kiểm tra danh sách có đúng 2 lệnh
        all_trades = get_all_trades()
        self.assertEqual(len(all_trades), 2)

    def test_add_trade_validation_failures(self):
        # Thiếu mã
        r1 = handle_add_trade({'symbol': '', 'volume': 100, 'price': 10000})
        self.assertFalse(r1['success'])
        self.assertIn('Vui lòng nhập mã chứng khoán', r1['error'])

        # Khối lượng <= 0
        r2 = handle_add_trade({'symbol': 'HPG', 'volume': 0, 'price': 10000})
        self.assertFalse(r2['success'])
        self.assertIn('Khối lượng phải lớn hơn 0', r2['error'])

        # Khối lượng âm
        r3 = handle_add_trade({'symbol': 'HPG', 'volume': -50, 'price': 10000})
        self.assertFalse(r3['success'])
        self.assertIn('Khối lượng phải lớn hơn 0', r3['error'])

        # Giá <= 0
        r4 = handle_add_trade({'symbol': 'HPG', 'volume': 100, 'price': 0})
        self.assertFalse(r4['success'])
        self.assertIn('Giá mua/bán phải lớn hơn 0', r4['error'])

    def test_delete_trade(self):
        # Thêm 1 lệnh để xóa
        add_res = handle_add_trade({
            'symbol': 'SSI',
            'order_type': 'BUY',
            'volume': 500,
            'price': 32000.0
        })
        trade_id = add_res['id']

        # Xóa thành công
        del_res = handle_delete_trade(trade_id)
        self.assertTrue(del_res['success'])

        # Xóa với ID rỗng
        del_empty = handle_delete_trade('')
        self.assertFalse(del_empty['success'])
        self.assertIn('Thiếu ID', del_empty['error'])

    def test_save_settings(self):
        # 1. Lưu NAV bằng dict
        res = handle_save_settings({'total_nav': 250_000_000})
        self.assertTrue(res['success'])
        self.assertEqual(res['total_nav'], 250_000_000.0)

        # 2. Lưu NAV bằng PortfolioSetting typed object
        setting = PortfolioSetting(key=PortfolioSetting.KEY_TOTAL_NAV, value='300000000.0')
        res2 = handle_save_settings(setting)
        self.assertTrue(res2['success'])
        self.assertEqual(res2['total_nav'], 300_000_000.0)

        # 3. Lỗi số âm
        res_neg = handle_save_settings({'total_nav': -100})
        self.assertFalse(res_neg['success'])

        # 4. Lỗi chuỗi không hợp lệ
        res_inv = handle_save_settings({'total_nav': 'chuỗi'})
        self.assertFalse(res_inv['success'])

    def test_portfolio_financial_calculations(self):
        """Kiểm tra độ chính xác của thuật toán tài chính VWAP và Realized PnL."""
        # Đặt tổng NAV là 100 triệu
        handle_save_settings({'total_nav': 100_000_000})

        # Lần 1: Mua 1000 HPG giá 20,000 (Vốn: 20 triệu)
        handle_add_trade({
            'symbol': 'HPG',
            'order_type': 'BUY',
            'volume': 1000,
            'price': 20000.0,
            'trade_date': '2026-11-01'
        })

        # Lần 2: Mua 1000 HPG giá 30,000 (Vốn thêm: 30 triệu, Tổng: 50 triệu / 2000 cp -> VWAP = 25,000)
        handle_add_trade({
            'symbol': 'HPG',
            'order_type': 'BUY',
            'volume': 1000,
            'price': 30000.0,
            'trade_date': '2026-11-02'
        })

        p1 = handle_get_portfolio()
        self.assertTrue(p1['success'])
        hpg1 = [h for h in p1['holdings'] if h['symbol'] == 'HPG'][0]
        self.assertEqual(hpg1['holding_volume'], 2000)
        self.assertEqual(hpg1['avg_price'], 25000.0)
        self.assertEqual(hpg1['total_cost'], 50_000_000.0)
        self.assertEqual(hpg1['realized_pnl'], 0.0)

        # Lần 3: Bán chốt lời 1000 HPG ở giá 35,000
        # Giá vốn tương ứng: 1000 * 25,000 = 25,000,000
        # Giá trị bán: 1000 * 35,000 = 35,000,000
        # Lãi đã chốt (Realized PnL): 10,000,000
        # Còn giữ: 1000 cp giá vốn 25,000 = 25,000,000
        handle_add_trade({
            'symbol': 'HPG',
            'order_type': 'SELL',
            'volume': 1000,
            'price': 35000.0,
            'trade_date': '2026-11-05'
        })

        p2 = handle_get_portfolio()
        hpg2 = [h for h in p2['holdings'] if h['symbol'] == 'HPG'][0]
        self.assertEqual(hpg2['holding_volume'], 1000)
        self.assertEqual(hpg2['avg_price'], 25000.0)
        self.assertEqual(hpg2['total_cost'], 25_000_000.0)
        self.assertEqual(hpg2['realized_pnl'], 10_000_000.0)

        # Sức mua khả dụng: NAV (100tr) - Chi phí giữ (25tr) + Lãi đã chốt (10tr) = 85 triệu
        summary = p2['summary']
        self.assertEqual(summary['realized_pnl'], 10_000_000.0)
        self.assertEqual(summary['total_buy_cost'], 25_000_000.0)
        self.assertEqual(summary['available_nav'], 85_000_000.0)

    def test_reset_portfolio(self):
        handle_add_trade({
            'symbol': 'VCI',
            'order_type': 'BUY',
            'volume': 200,
            'price': 45000.0
        })
        self.assertEqual(len(get_all_trades()), 1)

        res = handle_reset_portfolio()
        self.assertTrue(res['success'])
        self.assertEqual(len(get_all_trades()), 0)


if __name__ == '__main__':
    unittest.main()

