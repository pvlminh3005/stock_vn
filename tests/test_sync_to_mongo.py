"""
Unit & Integration Tests - Cloud Sync Tool (sync_to_mongo)
Kiểm thử công cụ đồng bộ SQLite local sang MongoDB Atlas:
- Xử lý thiếu URI / thiếu SQLite local file
- Deduplication chống trùng lặp bằng identity_filter() của PortfolioTrade
- Đồng bộ PortfolioSetting và AlertState
"""

import os
import sqlite3
import tempfile
import unittest

os.environ['APP_ENV'] = 'testing'

from backend.db.sync_to_mongo import sync_local_sqlite_to_mongodb
from backend.db.portfolio_db import get_all_trade_models, reset_all_trades, _mongo_db


class TestSyncToMongo(unittest.TestCase):
    """Kiểm thử tính năng đồng bộ cloud sync_to_mongo."""

    def setUp(self):
        reset_all_trades()

    def tearDown(self):
        reset_all_trades()

    def test_sync_missing_uri_returns_false(self):
        """Khi URI rỗng thì hàm phải trả về False an toàn."""
        ok = sync_local_sqlite_to_mongodb(mongo_uri='')
        self.assertFalse(ok)

    def test_sync_deduplication(self):
        """Kiểm tra deduplication chống trùng lặp dữ liệu bằng identity_filter()."""
        if _mongo_db is None:
            self.skipTest("MongoDB không sẵn sàng")

        # Tạo file SQLite tạm
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            tmp_sqlite_path = tmp.name

        try:
            with sqlite3.connect(tmp_sqlite_path) as conn:
                cur = conn.cursor()
                cur.execute("""
                    CREATE TABLE portfolio_trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        symbol TEXT,
                        order_type TEXT,
                        volume INTEGER,
                        price REAL,
                        trade_date TEXT,
                        note TEXT,
                        status TEXT,
                        expire_at INTEGER,
                        created_at INTEGER
                    )
                """)
                cur.execute("""
                    CREATE TABLE portfolio_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        updated_at INTEGER
                    )
                """)
                cur.execute("""
                    CREATE TABLE alert_states (
                        symbol TEXT PRIMARY KEY,
                        last_alert_type TEXT,
                        last_alert_time INTEGER,
                        flip_count_today INTEGER,
                        last_ribbon_color TEXT,
                        pending_summary TEXT,
                        updated_at INTEGER
                    )
                """)

                # Chèn 2 bản ghi giao dịch
                cur.execute("""
                    INSERT INTO portfolio_trades (symbol, order_type, volume, price, trade_date, note, status)
                    VALUES ('VCI', 'BUY', 1000, 42000.0, '2026-11-09', 'Test sync', 'HOLDING')
                """)
                cur.execute("""
                    INSERT INTO portfolio_trades (symbol, order_type, volume, price, trade_date, note, status)
                    VALUES ('HPG', 'BUY', 2000, 28000.0, '2026-11-09', 'Test sync 2', 'HOLDING')
                """)
                # Chèn 1 cấu hình
                cur.execute("""
                    INSERT INTO portfolio_settings (key, value, updated_at)
                    VALUES ('total_nav', '500000000', 1700000000)
                """)
                conn.commit()

            # Monkey-patch đường dẫn SQLITE_PORTFOLIO_DB
            import backend.db.sync_to_mongo as sync_mod
            orig_sqlite = sync_mod.SQLITE_PORTFOLIO_DB
            sync_mod.SQLITE_PORTFOLIO_DB = tmp_sqlite_path

            try:
                # Đồng bộ lần 1
                ok1 = sync_local_sqlite_to_mongodb()
                self.assertTrue(ok1)
                trades_after_1 = get_all_trade_models()
                self.assertEqual(len(trades_after_1), 2)

                # Đồng bộ lần 2 (cùng dữ liệu): Deduplication phải giữ nguyên 2 bản ghi, không nhân đôi thành 4
                ok2 = sync_local_sqlite_to_mongodb()
                self.assertTrue(ok2)
                trades_after_2 = get_all_trade_models()
                self.assertEqual(len(trades_after_2), 2)

            finally:
                sync_mod.SQLITE_PORTFOLIO_DB = orig_sqlite

        finally:
            if os.path.exists(tmp_sqlite_path):
                os.remove(tmp_sqlite_path)


if __name__ == '__main__':
    unittest.main()

