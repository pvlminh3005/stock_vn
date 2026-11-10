"""
Stock RT - Đồng Bộ Dữ Liệu SQLite Sang MongoDB (Cloud Sync Tool)
Chức năng:
Đọc toàn bộ dữ liệu danh mục từ SQLite local (data/portfolio.db)
và đẩy lên MongoDB Atlas/Cloud theo MONGODB_URI.
Chống trùng lặp tự động dựa vào (symbol, order_type, volume, price, trade_date).
"""

import os
import sys
import time
import sqlite3
import logging

# Setup sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.config.env_loader import load_environment, get_mongodb_config
from backend.constants.db import (
    COLL_PORTFOLIO_TRADES,
    COLL_PORTFOLIO_SETTINGS,
    COLL_ALERT_STATES,
)
from backend.models.db_models import PortfolioTrade, PortfolioSetting, AlertState

load_environment()

SQLITE_PORTFOLIO_DB = os.path.join(BASE_DIR, 'data', 'portfolio.db')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger('sync_to_mongo')


def sync_local_sqlite_to_mongodb(mongo_uri: str = None, db_name: str = None) -> bool:
    """Thực hiện đồng bộ dữ liệu từ SQLite local sang MongoDB."""
    default_uri, default_db = get_mongodb_config()
    uri = default_uri if mongo_uri is None else mongo_uri
    target_db = default_db if db_name is None else db_name

    if not uri or not str(uri).strip():
        logger.error("❌ Không tìm thấy biến môi trường MONGODB_URI trong cấu hình môi trường (envs/)!")
        logger.info("👉 Vui lòng cấu hình MONGODB_URI trong file envs/.env.development hoặc envs/.env.production.")
        return False

    if not os.path.exists(SQLITE_PORTFOLIO_DB):
        logger.info("ℹ️ File SQLite local (%s) chưa tồn tại hoặc chưa có dữ liệu.", SQLITE_PORTFOLIO_DB)
        return False

    client = None
    mongo_kwargs = {
        'serverSelectionTimeoutMS': 15000,
        'connectTimeoutMS': 10000,
        'socketTimeoutMS': 20000,
        'retryWrites': True,
        'retryReads': True,
    }
    try:
        import certifi
        mongo_kwargs['tlsCAFile'] = certifi.where()
    except ImportError:
        pass

    db = None
    for attempt in range(1, 4):
        try:
            from pymongo import MongoClient
            client = MongoClient(uri, **mongo_kwargs)
            client.admin.command('ping')
            db = client[target_db]
            logger.info("✅ Kết nối MongoDB Atlas thành công (DB: %s)", target_db)
            break
        except Exception as e:
            if attempt < 3:
                logger.warning("Thử lại kết nối MongoDB Atlas lần %d/3...", attempt)
                time.sleep(1.5)
            else:
                logger.error("❌ Lỗi kết nối MongoDB Atlas sau 3 lần thử: %s", e)
                if client:
                    client.close()
                return False

    if db is None:
        logger.error("❌ Không thể kết nối tới cơ sở dữ liệu MongoDB Atlas.")
        return False

    # 1. Đảm bảo Index trên MongoDB
    trades_coll = db[COLL_PORTFOLIO_TRADES]
    trades_coll.create_index(PortfolioTrade.INDEX_EXPIRE_AT, expireAfterSeconds=0)
    trades_coll.create_index(PortfolioTrade.INDEX_SYMBOL)
    trades_coll.create_index(PortfolioTrade.INDEX_ORDER_TYPE)

    settings_coll = db[COLL_PORTFOLIO_SETTINGS]
    settings_coll.create_index(PortfolioSetting.INDEX_KEY, unique=True)

    alert_coll = db[COLL_ALERT_STATES]
    alert_coll.create_index(AlertState.INDEX_SYMBOL, unique=True)

    # 2. Đọc từ SQLite và đẩy sang Mongo
    synced_trades = 0
    synced_settings = 0
    synced_alerts = 0

    try:
        with sqlite3.connect(SQLITE_PORTFOLIO_DB) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            # A. Đồng bộ settings (Tổng NAV)
            try:
                cur.execute("SELECT key, value, updated_at FROM portfolio_settings")
                rows = cur.fetchall()
                for r in rows:
                    setting = PortfolioSetting(key=r['key'], value=str(r['value']), updated_at=int(r['updated_at'] or 0))
                    settings_coll.update_one(
                        PortfolioSetting.filter_by_key(setting.key),
                        {'$set': setting.to_doc()},
                        upsert=True
                    )
                    synced_settings += 1
            except Exception as e:
                logger.warning("Lỗi đọc portfolio_settings từ SQLite: %s", e)

            # B. Đồng bộ trades
            try:
                cur.execute("SELECT symbol, order_type, volume, price, trade_date, note, status, expire_at, created_at FROM portfolio_trades")
                trades = cur.fetchall()
                for t in trades:
                    trade_obj = PortfolioTrade.from_doc(dict(t))
                    existing = trades_coll.find_one(trade_obj.identity_filter())
                    if not existing:
                        trades_coll.insert_one(trade_obj.to_doc())
                        synced_trades += 1
            except Exception as e:
                logger.warning("Lỗi đọc portfolio_trades từ SQLite: %s", e)

            # C. Đồng bộ alert_states
            try:
                cur.execute("SELECT symbol, last_alert_type, last_alert_time, flip_count_today, last_ribbon_color, pending_summary, updated_at FROM alert_states")
                alerts = cur.fetchall()
                for a in alerts:
                    alert_obj = AlertState.from_doc(dict(a))
                    alert_coll.update_one(
                        AlertState.filter_by_symbol(alert_obj.symbol),
                        {'$set': alert_obj.to_doc()},
                        upsert=True
                    )
                    synced_alerts += 1
            except Exception as e:
                logger.warning("Lỗi đọc alert_states từ SQLite: %s", e)

        logger.info(
            "🎉 ĐỒNG BỘ THÀNH CÔNG:\n"
            "   - Giao dịch (Trades): %d bản ghi mới\n"
            "   - Cấu hình (Settings): %d bản ghi\n"
            "   - Trạng thái Cảnh báo (Alerts): %d bản ghi",
            synced_trades, synced_settings, synced_alerts
        )
        return True
    except Exception as e:
        logger.error("❌ Lỗi trong quá trình đồng bộ: %s", e)
        return False
    finally:
        if client:
            client.close()


if __name__ == '__main__':
    print("=" * 60)
    print(" STOCK RT - MONGODB CLOUD SYNC TOOL")
    print("=" * 60)
    success = sync_local_sqlite_to_mongodb()
    if success:
        print("\n✅ Hoàn tất đồng bộ dữ liệu lên MongoDB Atlas!")
    else:
        print("\n⚠️ Đồng bộ chưa hoàn thành. Vui lòng kiểm tra lại cấu hình MONGODB_URI.")

