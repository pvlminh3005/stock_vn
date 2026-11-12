"""
Unit Tests - Vietcap / Simplize / VNDirect Providers (Post-vnstock Removal)
Kiểm thử logic nghiệp vụ và edge cases sau khi gỡ bỏ hoàn toàn vnstock:
- market_board_provider: get_dynamic_liquid_universe (Vietcap VN100+HNX30, partial failure, Mongo fallback, VN30 seed)
- vci_provider: _parse_vietcap_quarters, fetch_vci_financial_history (lọc quarter=5, NaN/Inf, partial=True không ghi cache)
- fundamental_provider: fetch_company_fundamentals fallback sang Vietcap IQ, giữ nguyên snapshot EPS/BVPS, tính TTM YoY
- news_provider: trace_events tiếng Việt qua VNDirect Finfo API và xử lý payload rỗng/lỗi
"""

import os
import sys
import unittest
from unittest.mock import patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

os.environ['APP_ENV'] = 'testing'

from backend.data_providers import market_board_provider, vci_provider, fundamental_provider, news_provider


class TestMarketBoardUniverse(unittest.TestCase):
    """Kiểm thử nạp rổ thanh khoản VN100 + HNX30 không phụ thuộc vnstock."""

    def setUp(self):
        market_board_provider._LIQUID_UNIVERSE_CACHE['timestamp'] = 0
        market_board_provider._LIQUID_UNIVERSE_CACHE['symbols'] = []

    def test_vietcap_discovery_and_dedup(self):
        vn100 = [{'symbol': f'A{i:02d}'} for i in range(40)] + [{'symbol': 'ACB'}, {'symbol': 'INVALID4'}]
        hnx30 = [{'symbol': 'ACB'}, {'symbol': 'BVS'}, {'symbol': 'CEO'}]

        def fake_fetch(url, headers=None, timeout=5):
            return vn100 if 'VN100' in url else hnx30

        with patch.object(market_board_provider, 'fetch_json', side_effect=fake_fetch), \
             patch.object(market_board_provider, '_save_liquid_universe_to_mongo') as mock_save:
            syms = market_board_provider.get_dynamic_liquid_universe(limit=50, force_refresh=True)

        self.assertEqual(len(syms), 43)
        self.assertIn('ACB', syms)
        self.assertIn('BVS', syms)
        self.assertNotIn('INVALID4', syms)
        self.assertEqual(len(syms), len(set(syms)))
        mock_save.assert_called_once()

    def test_partial_group_failure_still_succeeds_with_vn100(self):
        vn100 = [{'symbol': f'V{i:02d}'} for i in range(35)]

        def fake_fetch(url, headers=None, timeout=5):
            if 'HNX30' in url:
                raise TimeoutError('HNX30 timeout')
            return vn100

        with patch.object(market_board_provider, 'fetch_json', side_effect=fake_fetch), \
             patch.object(market_board_provider, '_save_liquid_universe_to_mongo'):
            syms = market_board_provider.get_dynamic_liquid_universe(limit=80, force_refresh=True)

        self.assertEqual(len(syms), 35)

    def test_full_api_failure_falls_back_to_mongo_and_seed(self):
        with patch.object(market_board_provider, 'fetch_json', side_effect=OSError('network down')), \
             patch.object(market_board_provider, '_load_liquid_universe_from_mongo', return_value=[f'M{i:02d}' for i in range(25)]):
            syms = market_board_provider.get_dynamic_liquid_universe(limit=10, force_refresh=True)
        self.assertEqual(syms, [f'M{i:02d}' for i in range(10)])

        market_board_provider._LIQUID_UNIVERSE_CACHE['symbols'] = []
        with patch.object(market_board_provider, 'fetch_json', side_effect=OSError('network down')), \
             patch.object(market_board_provider, '_load_liquid_universe_from_mongo', return_value=[]):
            seed = market_board_provider.get_dynamic_liquid_universe(limit=10, force_refresh=True)
        self.assertEqual(seed, market_board_provider._VN30_SEED_STOCKS[:10])


class TestVciProviderMigration(unittest.TestCase):
    """Kiểm thử chuẩn hóa Vietcap IQ cho lịch sử BCTC VCI."""

    def test_parse_filters_annual_and_non_finite_values(self):
        rows = [
            {'yearReport': 2025, 'quarter': 5, 'pe': 99.0},  # Annual row must be ignored
            {'yearReport': 2026, 'quarter': 1, 'pe': 10.5, 'roe': float('nan')},
            {'yearReport': 2026, 'quarter': 2, 'pe': 11.2, 'roe': 0.25},
            {'yearReport': None, 'quarter': 3, 'pe': 12.0},
        ]
        parsed = vci_provider._parse_vietcap_quarters(rows, {'pe': 'pe', 'roe': 'roe'}, quarter_key='quarter')
        self.assertEqual(list(parsed['pe'].keys()), ['2026-Q1', '2026-Q2'])
        self.assertNotIn('2026-Q1', parsed['roe'])
        self.assertEqual(parsed['roe']['2026-Q2'], 0.25)

    def test_partial_failure_does_not_cache_to_mongo(self):
        def fake_report(symbol, report_type, fields):
            if report_type == 'ratio':
                return {'pe': {'2026-Q1': 10.0, '2026-Q2': 11.0}}
            return None  # simulate BALANCE_SHEET or CASH_FLOW network failure

        class FakeColl:
            def __init__(self):
                self.updated = False

            def find_one(self, *args, **kwargs):
                return None

            def update_one(self, *args, **kwargs):
                self.updated = True

        fake_coll = FakeColl()
        with patch.object(vci_provider, '_vci_quarterly_report', side_effect=fake_report), \
             patch.object(vci_provider, '_get_vci_mongo', return_value=fake_coll):
            hist = vci_provider.get_vci_financial_history('VNM')

        self.assertIsNotNone(hist)
        self.assertTrue(hist['partial'])
        self.assertFalse(fake_coll.updated)


class TestFundamentalAndNewsMigration(unittest.TestCase):
    """Kiểm thử fallback Vietcap IQ và sự kiện VNDirect."""

    def test_simplize_failure_falls_back_to_vietcap_with_invariant_eps_bvps(self):
        comp_payload = {
            'status': 200,
            'data': {
                'viOrganName': 'Công ty Test',
                'sectorVn': 'Công nghệ thông tin',
                'currentPrice': 100000.0,
                'profile': '<p>Hồ sơ doanh nghiệp test dài hơn hai mươi ký tự.</p>',
            },
        }
        sf_payload = {
            'status': 200,
            'data': [
                {
                    'yearReport': 2026, 'quarter': 3,
                    'pe': 10.0, 'pb': 2.0, 'ps': 1.5,
                    'roe': 0.20, 'roa': 0.10, 'grossMargin': 0.40, 'afterTaxProfitMargin': 0.15,
                    'debtPerEquity': 0.30, 'marketCap': 100_000_000_000.0, 'numberOfSharesMktCap': 1_000_000,
                }
            ],
        }
        is_quarters = [
            {'yearReport': 2024 + (i // 4), 'lengthReport': (i % 4) + 1, 'isa3': 1000.0, 'isa22': 100.0}
            for i in range(4)
        ] + [
            {'yearReport': 2025 + (i // 4), 'lengthReport': (i % 4) + 1, 'isa3': 1200.0, 'isa22': 150.0}
            for i in range(4)
        ]
        is_payload = {'status': 200, 'data': {'quarters': is_quarters}}

        def fake_fetch(url, headers=None, timeout=6):
            if 'statistics-financial' in url:
                return sf_payload
            if 'financial-statement' in url:
                return is_payload
            return comp_payload

        with patch.object(fundamental_provider, 'fetch_from_simplize', return_value=None), \
             patch.object(fundamental_provider, 'fetch_json', side_effect=fake_fetch):
            # Pass a live price (120,000) different from snapshot price (100,000)
            res = fundamental_provider.fetch_company_fundamentals('FPT', current_price=120000.0)

        self.assertIsNotNone(res)
        # Snapshot price is 100,000 -> EPS = 10,000, BVPS = 50,000
        self.assertEqual(res['eps'], 10000)
        self.assertEqual(res['bvps'], 50000)
        # Dynamic P/E and P/B use live current_price 120,000
        self.assertEqual(res['pe'], 12.0)
        self.assertEqual(res['pb'], 2.4)
        self.assertEqual(res['revGrowth'], 20.0)
        self.assertEqual(res['profitGrowth'], 50.0)
        self.assertEqual(res['reportPeriod'], '2026-Q3')

    def test_news_provider_events_fallback_on_empty_or_error(self):
        news_provider._LIVE_NEWS_CACHE.clear()
        with patch.object(news_provider, 'fetch_json', side_effect=OSError('timeout')):
            records = news_provider.fetch_live_multi_sources('VNM', current_price=54500)
        self.assertTrue(any(r['source'] == 'Bảng Giá Thị Trường Realtime' for r in records))
        self.assertFalse(any(r['source'] == 'Cổng Sự Kiện Doanh Nghiệp (HoSE/HNX)' for r in records))


if __name__ == '__main__':
    unittest.main()

