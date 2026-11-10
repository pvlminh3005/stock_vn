"""
Unit Tests - MongoDB Document Models & DTOs
Kiểm tra toàn diện tất cả các Class Models, Mappers to_doc/from_doc/to_dict,
Validation from_request, Field Constants, Index Specs và Query Builders.
"""

import os
import unittest
from datetime import datetime, timezone
from bson import ObjectId

# Bắt buộc isolate sang testing profile
os.environ['APP_ENV'] = 'testing'

from backend.models.db_models import (
    PortfolioTrade,
    PortfolioSetting,
    AlertState,
    TelegramAlertLog,
    TelegramSentLog,
    CompanyItem,
    MarketBoardSnapshot,
    ScreenerSnapshot,
    FundamentalItem,
    VciHistoryItem,
)
from backend.models.portfolio_dto import (
    PortfolioHolding,
    PortfolioSummary,
)
from backend.utils.datetime_helpers import (
    to_mongo_datetime,
    parse_db_datetime,
    to_timestamp_int,
    to_vn_datetime_str,
    VN_TZ,
)


class TestPortfolioTradeModel(unittest.TestCase):
    """Kiểm thử Model Sổ lệnh PortfolioTrade."""

    def test_trade_creation_and_to_doc(self):
        t = PortfolioTrade(
            symbol='hpg',
            order_type='buy',
            volume=1500,
            price=28.5,
            trade_date='2026-11-09',
            note='Test Note',
            status='holding'
        )
        doc = t.to_doc()
        self.assertEqual(doc[PortfolioTrade.F_SYMBOL], 'HPG')
        self.assertEqual(doc[PortfolioTrade.F_ORDER_TYPE], 'BUY')
        self.assertEqual(doc[PortfolioTrade.F_VOLUME], 1500)
        self.assertEqual(doc[PortfolioTrade.F_PRICE], 28.5)
        self.assertEqual(doc[PortfolioTrade.F_TRADE_DATE], '2026-11-09')
        self.assertEqual(doc[PortfolioTrade.F_NOTE], 'Test Note')
        self.assertEqual(doc[PortfolioTrade.F_STATUS], 'HOLDING')
        self.assertIsInstance(doc[PortfolioTrade.F_CREATED_AT], datetime)

    def test_trade_from_doc(self):
        raw_doc = {
            '_id': ObjectId('507f1f77bcf86cd799439011'),
            'symbol': 'VNM',
            'order_type': 'SELL',
            'volume': 500,
            'price': 72000.0,
            'trade_date': '2026-11-08',
            'note': 'Chốt lời',
            'status': 'CLOSED',
            'created_at': 1700000000,
        }
        t = PortfolioTrade.from_doc(raw_doc)
        self.assertEqual(t.id, '507f1f77bcf86cd799439011')
        self.assertEqual(t.symbol, 'VNM')
        self.assertEqual(t.order_type, 'SELL')
        self.assertEqual(t.volume, 500)
        self.assertEqual(t.price, 72000.0)
        self.assertEqual(t.status, 'CLOSED')
        self.assertIsInstance(t.created_at, datetime)

    def test_trade_normalize_price(self):
        # Giá < 1000 tự nhân 1000 (định dạng 28.5 -> 28500)
        self.assertEqual(PortfolioTrade.normalize_price(28.5), 28500.0)
        self.assertEqual(PortfolioTrade.normalize_price('31.25'), 31250.0)
        # Giá >= 1000 giữ nguyên
        self.assertEqual(PortfolioTrade.normalize_price(105000), 105000.0)
        # Giá không hợp lệ
        self.assertEqual(PortfolioTrade.normalize_price('abc'), 0.0)
        self.assertEqual(PortfolioTrade.normalize_price(-10), 0.0)

    def test_trade_from_request_validation_success(self):
        payload = {
            'symbol': '  fpt  ',
            'order_type': 'buy',
            'volume': '2000',
            'price': '125.5',
            'trade_date': '2026-11-09',
            'note': ' Mua thêm ',
        }
        trade, err = PortfolioTrade.from_request(payload)
        self.assertIsNone(err)
        self.assertIsNotNone(trade)
        self.assertEqual(trade.symbol, 'FPT')
        self.assertEqual(trade.order_type, 'BUY')
        self.assertEqual(trade.volume, 2000)
        self.assertEqual(trade.price, 125500.0)
        self.assertEqual(trade.trade_date, '2026-11-09')
        self.assertEqual(trade.note, 'Mua thêm')
        self.assertEqual(trade.status, 'HOLDING')

    def test_trade_from_request_validation_edge_cases(self):
        # 1. Payload rỗng
        trade, err = PortfolioTrade.from_request({})
        self.assertIn('Vui lòng nhập mã chứng khoán', err)

        # 2. Symbol quá dài (> 10 ký tự)
        trade, err = PortfolioTrade.from_request({'symbol': 'VERYLONGSYMBOL123', 'volume': 100, 'price': 10000})
        self.assertIn('tối đa 10 ký tự', err)

        # 3. Volume <= 0
        trade, err = PortfolioTrade.from_request({'symbol': 'SSI', 'volume': 0, 'price': 10000})
        self.assertIn('Khối lượng phải lớn hơn 0', err)
        trade, err = PortfolioTrade.from_request({'symbol': 'SSI', 'volume': -50, 'price': 10000})
        self.assertIn('Khối lượng phải lớn hơn 0', err)

        # 4. Volume không phải số
        trade, err = PortfolioTrade.from_request({'symbol': 'SSI', 'volume': 'năm trăm', 'price': 10000})
        self.assertIn('Khối lượng không hợp lệ', err)

        # 5. Price <= 0
        trade, err = PortfolioTrade.from_request({'symbol': 'SSI', 'volume': 100, 'price': 0})
        self.assertIn('Giá mua/bán phải lớn hơn 0', err)
        trade, err = PortfolioTrade.from_request({'symbol': 'SSI', 'volume': 100, 'price': -100})
        self.assertIn('Giá mua/bán phải lớn hơn 0', err)

        # 6. Order type SELL tự gán status CLOSED
        trade, err = PortfolioTrade.from_request({'symbol': 'SSI', 'volume': 100, 'price': 30000, 'order_type': 'sell'})
        self.assertIsNone(err)
        self.assertEqual(trade.order_type, 'SELL')
        self.assertEqual(trade.status, 'CLOSED')

        # 7. Order type không hợp lệ tự fallback về BUY
        trade, err = PortfolioTrade.from_request({'symbol': 'SSI', 'volume': 100, 'price': 30000, 'order_type': 'UNKNOWN'})
        self.assertIsNone(err)
        self.assertEqual(trade.order_type, 'BUY')

    def test_trade_query_builders(self):
        self.assertEqual(PortfolioTrade.filter_by_symbol('hpg'), {'symbol': 'HPG'})
        self.assertEqual(PortfolioTrade.filter_by_order_type('buy'), {'order_type': 'BUY'})
        self.assertEqual(PortfolioTrade.filter_active_holdings(), {'order_type': 'BUY'})
        self.assertEqual(PortfolioTrade.filter_by_symbol_and_type('fpt', 'sell'), {'symbol': 'FPT', 'order_type': 'SELL'})
        self.assertEqual(PortfolioTrade.filter_by_id_str('12345'), {'id': '12345'})


class TestPortfolioSettingModel(unittest.TestCase):
    """Kiểm thử Model Cấu hình PortfolioSetting."""

    def test_setting_to_doc_and_from_doc(self):
        s = PortfolioSetting(key='total_nav', value='500000000')
        doc = s.to_doc()
        self.assertEqual(doc['key'], 'total_nav')
        self.assertEqual(doc['value'], '500000000')
        self.assertIsInstance(doc['updated_at'], datetime)

        recovered = PortfolioSetting.from_doc(doc)
        self.assertEqual(recovered.key, 'total_nav')
        self.assertEqual(recovered.value, '500000000')
        self.assertIsInstance(recovered.updated_at, datetime)

    def test_setting_from_request_validation(self):
        # Hợp lệ
        s, err = PortfolioSetting.from_request({'total_nav': 100_000_000})
        self.assertIsNone(err)
        self.assertEqual(s.key, PortfolioSetting.KEY_TOTAL_NAV)
        self.assertEqual(s.value, '100000000.0')

        # Số âm
        s, err = PortfolioSetting.from_request({'total_nav': -500})
        self.assertIn('không được âm', err)

        # Chuỗi không hợp lệ
        s, err = PortfolioSetting.from_request({'total_nav': 'mot_trieu'})
        self.assertIn('không hợp lệ', err)

        # Key-Value tự do
        s, err = PortfolioSetting.from_request({'key': 'risk_pct', 'value': '7.5'})
        self.assertIsNone(err)
        self.assertEqual(s.key, 'risk_pct')
        self.assertEqual(s.value, '7.5')


class TestAlertAndTelegramModels(unittest.TestCase):
    """Kiểm thử AlertState, TelegramAlertLog, TelegramSentLog."""

    def test_alert_state(self):
        a = AlertState(symbol='vci', last_alert_type='BUY_BREAKOUT', last_alert_time=1700000000)
        doc = a.to_doc()
        self.assertEqual(doc['symbol'], 'VCI')
        self.assertEqual(doc['last_alert_type'], 'BUY_BREAKOUT')
        self.assertEqual(AlertState.filter_by_symbol('vci'), {'symbol': 'VCI'})

    def test_telegram_alert_log(self):
        log = TelegramAlertLog(key='breakout_HPG_2026-11-09', preview='Breakout HPG')
        doc = log.to_doc()
        self.assertEqual(doc['key'], 'breakout_HPG_2026-11-09')
        self.assertEqual(doc['preview'], 'Breakout HPG')
        self.assertEqual(TelegramAlertLog.filter_by_key('k1'), {'key': 'k1'})

    def test_telegram_sent_log(self):
        sent = TelegramSentLog(
            alert_type='BUY_SIGNAL',
            title='Tín hiệu MUA FPT',
            stocks=[{'symbol': 'FPT', 'price': 120.0}],
            market_regime='RISK_ON'
        )
        doc = sent.to_doc()
        self.assertEqual(doc['alert_type'], 'BUY_SIGNAL')
        self.assertEqual(doc['title'], 'Tín hiệu MUA FPT')
        self.assertEqual(TelegramSentLog.SORT_SENT_AT_DESC, ('sent_at', -1))


class TestCompanyItemModel(unittest.TestCase):
    """Kiểm thử Model CompanyItem."""

    def test_company_item_to_doc_and_filter(self):
        c = CompanyItem(
            ticker='mwg',
            name='Thế Giới Di Động',
            name_vi='Thế Giới Di Động',
            name_unaccent='the gioi di dong',
            exchange='hose',
            sector='Bán lẻ'
        )
        doc = c.to_doc()
        self.assertEqual(doc[CompanyItem.F_TICKER], 'MWG')
        self.assertEqual(doc[CompanyItem.F_EXCHANGE], 'HOSE')
        self.assertEqual(CompanyItem.filter_by_ticker('mwg'), {'ticker': 'MWG'})

        # Prefix search builder
        p_flt = CompanyItem.filter_by_ticker_prefix('MW', exclude_tickers=['MWG'])
        self.assertIn('$regex', p_flt['ticker'])
        self.assertEqual(p_flt['ticker']['$nin'], ['MWG'])

        # Text search builder
        s_flt = CompanyItem.filter_search_text('thép', 'thep', exclude_tickers=['HPG'])
        self.assertIn('$or', s_flt)
        self.assertEqual(s_flt['ticker'], {'$nin': ['HPG']})


class TestMarketSnapshotsAndDTOs(unittest.TestCase):
    """Kiểm thử Snapshot models và DTOs."""

    def test_market_board_and_screener_snapshots(self):
        board = MarketBoardSnapshot(data={'HPG': {'lastPrice': 28.5}})
        self.assertEqual(board.key, MarketBoardSnapshot.KEY_LATEST_BOARD)
        self.assertEqual(MarketBoardSnapshot.filter_by_key(), {'key': 'latest_board'})

        screener = ScreenerSnapshot(data={'top': ['FPT', 'VCI']})
        self.assertEqual(screener.key, ScreenerSnapshot.KEY_TOP_TPLUS)
        self.assertEqual(ScreenerSnapshot.filter_by_key(), {'key': 'top_tplus'})

    def test_dto_serialization(self):
        holding = PortfolioHolding(
            symbol='HPG',
            holding_volume=1000,
            avg_price=28000.0,
            current_price=29000.0,
            unrealized_pnl=1000000.0
        )
        d = holding.to_dict()
        self.assertEqual(d['symbol'], 'HPG')
        self.assertEqual(d['holding_volume'], 1000)
        self.assertEqual(d['unrealized_pnl'], 1000000.0)

        summary = PortfolioSummary(
            total_nav=500_000_000.0,
            total_buy_cost=200_000_000.0,
            current_market_val=210_000_000.0,
            holdings_count=2
        )
        s_dict = summary.to_dict()
        self.assertEqual(s_dict['total_nav'], 500_000_000.0)
        self.assertEqual(s_dict['holdings_count'], 2)


class TestDatetimeHelpers(unittest.TestCase):
    """Kiểm thử tiện ích chuyển đổi Datetime dùng chung cho MongoDB."""

    def test_to_mongo_datetime_from_various_inputs(self):
        # 1. Từ datetime trực tiếp (local VN -> UTC)
        dt_in = datetime(2026, 11, 9, 15, 3, 54)
        dt_utc = to_mongo_datetime(dt_in)
        self.assertEqual(dt_utc.tzinfo, timezone.utc)
        self.assertEqual(dt_utc.hour, 8)  # 15:03 GMT+7 -> 08:03 UTC
        self.assertEqual(to_vn_datetime_str(dt_utc), '2026-11-09 15:03:54')

        # 2. Từ UNIX timestamp seconds (1700000000)
        dt_ts = to_mongo_datetime(1700000000)
        self.assertIsInstance(dt_ts, datetime)
        self.assertEqual(int(dt_ts.timestamp()), 1700000000)

        # 3. Từ UNIX timestamp milliseconds (1700000000000)
        dt_ms = to_mongo_datetime(1700000000000)
        self.assertIsInstance(dt_ms, datetime)
        self.assertEqual(int(dt_ms.timestamp()), 1700000000)

        # 4. Từ ISO 8601 string có múi giờ UTC
        iso_str = '2026-11-09T08:03:54.456+00:00'
        dt_iso = to_mongo_datetime(iso_str)
        self.assertIsInstance(dt_iso, datetime)
        self.assertEqual(dt_iso.year, 2026)
        self.assertEqual(dt_iso.month, 11)
        self.assertEqual(dt_iso.day, 9)
        self.assertEqual(dt_iso.hour, 8)
        self.assertEqual(to_vn_datetime_str(dt_iso), '2026-11-09 15:03:54')

        # 5. Từ chuỗi 'YYYY-MM-DD HH:MM:SS'
        dt_fmt = to_mongo_datetime('2026-11-09 15:03:54')
        self.assertEqual(dt_fmt.year, 2026)
        self.assertEqual(dt_fmt.hour, 8)  # Chuyển đổi chuẩn sang UTC
        self.assertEqual(to_vn_datetime_str(dt_fmt), '2026-11-09 15:03:54')

        # 6. Từ None (default_now=True vs False)
        self.assertIsInstance(to_mongo_datetime(None, default_now=True), datetime)
        self.assertIsNone(to_mongo_datetime(None, default_now=False))

    def test_parse_db_datetime_backward_compatibility(self):
        # Khôi phục từ bản ghi cũ (integer timestamp)
        recovered_from_int = parse_db_datetime(1700000000)
        self.assertIsInstance(recovered_from_int, datetime)
        self.assertEqual(int(recovered_from_int.timestamp()), 1700000000)
        self.assertEqual(recovered_from_int.tzinfo, VN_TZ)

        # Khôi phục từ bản ghi mới (ISODate / datetime từ MongoDB lưu UTC)
        mongo_utc_dt = datetime(2026, 11, 9, 8, 3, 54, tzinfo=timezone.utc)
        recovered_from_dt = parse_db_datetime(mongo_utc_dt)
        self.assertEqual(recovered_from_dt.tzinfo, VN_TZ)
        self.assertEqual(recovered_from_dt.hour, 15)  # Trả về đúng 15:03 giờ VN
        self.assertEqual(to_vn_datetime_str(recovered_from_dt), '2026-11-09 15:03:54')

        # Khôi phục khi field rỗng
        self.assertIsNone(parse_db_datetime(None))

    def test_to_timestamp_int(self):
        dt = datetime(2026, 11, 9, 10, 0, 0)
        self.assertEqual(to_timestamp_int(dt), int(dt.timestamp()))
        self.assertEqual(to_timestamp_int(1700000000), 1700000000)
        self.assertEqual(to_timestamp_int(None), 0)

    def test_all_10_models_save_isodate(self):
        """Đảm bảo to_doc() của toàn bộ 10 Model đều lưu datetime (BSON ISODate) vào MongoDB."""
        now_dt = datetime.now()

        # 1. PortfolioTrade
        t_doc = PortfolioTrade(symbol='HPG', created_at=now_dt, expire_at=now_dt).to_doc()
        self.assertIsInstance(t_doc['created_at'], datetime)
        self.assertIsInstance(t_doc['expire_at'], datetime)

        # 2. PortfolioSetting
        s_doc = PortfolioSetting(key='total_nav', value='100', updated_at=1700000000).to_doc()
        self.assertIsInstance(s_doc['updated_at'], datetime)

        # 3. AlertState
        a_doc = AlertState(symbol='HPG', updated_at='2026-11-09T15:00:00').to_doc()
        self.assertIsInstance(a_doc['updated_at'], datetime)

        # 4. TelegramAlertLog
        tal_doc = TelegramAlertLog(key='k1', sent_at=1700000000).to_doc()
        self.assertIsInstance(tal_doc['sent_at'], datetime)

        # 5. TelegramSentLog
        tsl_doc = TelegramSentLog(alert_type='BUY', sent_at=now_dt, expire_at=now_dt).to_doc()
        self.assertIsInstance(tsl_doc['sent_at'], datetime)
        self.assertIsInstance(tsl_doc['expire_at'], datetime)

        # 6. CompanyItem
        c_doc = CompanyItem(ticker='HPG', updated_at=1700000000).to_doc()
        self.assertIsInstance(c_doc['updated_at'], datetime)

        # 7. MarketBoardSnapshot
        mb_doc = MarketBoardSnapshot(data={}, updated_at=1700000000).to_doc()
        self.assertIsInstance(mb_doc['updated_at'], datetime)

        # 8. ScreenerSnapshot
        sc_doc = ScreenerSnapshot(data={}, updated_at=1700000000).to_doc()
        self.assertIsInstance(sc_doc['updated_at'], datetime)

        # 9. FundamentalItem
        f_doc = FundamentalItem(symbol='HPG', data={}, updated_at=1700000000).to_doc()
        self.assertIsInstance(f_doc['updated_at'], datetime)

        # 10. VciHistoryItem
        v_doc = VciHistoryItem(symbol='HPG', payload={}, updated_at=1700000000).to_doc()
        self.assertIsInstance(v_doc['updated_at'], datetime)


if __name__ == '__main__':
    unittest.main()

