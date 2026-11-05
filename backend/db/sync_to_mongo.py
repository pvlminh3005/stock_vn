"""
Stock RT - Đồng Bộ Dữ Liệu SQLite Sang MongoDB (Cloud Sync Tool)
Chức năng:
Đọc toàn bộ dữ liệu danh mục từ SQLite local (data/portfolio.db)
và đẩy lên MongoDB Atlas/Cloud theo MONGODB_URI.
Chống trùng lặp tự động dựa vào (symbol, order_type, volume, price, trade_date).
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime

# Setup sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Nạp .env
env_file = os.path.join(BASE_DIR, '.env')
if os.path.isfile(env_file):
    try:
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v
    except Exception:
        pass

from backend.db.portfolio_db import RETENTION_DAYS
SQLITE_PORTFOLIO_DB = os.path.join(BASE_DIR, 'data', 'portfolio.db')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s')
logger = logging.getLogger('sync_to_mongo')


def sync_local_sqlite_to_mongodb(mongo_uri: str = None, db_name: str = None) -> bool:
    """Thực hiện đồng bộ dữ liệu từ SQLite local sang MongoDB."""
    uri = mongo_uri or os.environ.get('MONGODB_URI', '').strip()
    target_db = db_name or os.environ.get('MONGODB_DB_NAME', 'stock_pro_db').strip()

    if not uri:
        logger.error("❌ Không tìm thấy biến môi trường MONGODB_URI trong file .env!")
        logger.info("👉 Vui lòng cấu hình MONGODB_URI trong file .env trước khi chạy sync.")
        return False

    if not os.path.exists(SQLITE_PORTFOLIO_DB):
        logger.info("ℹ️ File SQLite local (%s) chưa tồn tại hoặc chưa có dữ liệu.", SQLITE_PORTFOLIO_DB)
        return False

    try:
        from pymongo import MongoClient, ASCENDING
        mongo_kwargs = {'serverSelectionTimeoutMS': 8000}
        try:
            import certifi
            mongo_kwargs['tlsCAFile'] = certifi.where()
        except ImportError:
            pass
        client = MongoClient(uri, **mongo_kwargs)
        client.admin.command('ping')
        db = client[target_db]
        logger.info("✅ Kết nối MongoDB Atlas thành công (DB: %s)", target_db)
    except Exception as e:
        logger.error("❌ Lỗi kết nối MongoDB Atlas: %s", e)
        return False

    # 1. Đảm bảo Index trên MongoDB
    trades_coll = db['portfolio_trades']
    trades_coll.create_index([("expire_at", ASCENDING)], expireAfterSeconds=0)
    trades_coll.create_index([("symbol", ASCENDING)])
    trades_coll.create_index([("order_type", ASCENDING)])

    settings_coll = db['portfolio_settings']
    settings_coll.create_index([("key", ASCENDING)], unique=True)

    alert_coll = db['alert_states']
    alert_coll.create_index([("symbol", ASCENDING)], unique=True)

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
                    settings_coll.update_one(
                        {'key': r['key']},
                        {'$set': {'key': r['key'], 'value': str(r['value']), 'updated_at': r['updated_at']}},
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
                    filter_query = {
                        'symbol': t['symbol'],
                        'order_type': t['order_type'],
                        'volume': t['volume'],
                        'price': t['price'],
                        'trade_date': t['trade_date'],
                    }
                    existing = trades_coll.find_one(filter_query)
                    if not existing:
                        expire_dt = datetime.fromtimestamp(t['expire_at']) if t['expire_at'] else None
                        created_dt = datetime.fromtimestamp(t['created_at']) if t['created_at'] else datetime.now()
                        doc = {
                            'symbol': t['symbol'],
                            'order_type': t['order_type'],
                            'volume': t['volume'],
                            'price': t['price'],
                            'trade_date': t['trade_date'],
                            'note': t['note'] or '',
                            'status': t['status'] or 'HOLDING',
                            'created_at': created_dt,
                            'expire_at': expire_dt
                        }
                        trades_coll.insert_one(doc)
                        synced_trades += 1
            except Exception as e:
                logger.warning("Lỗi đọc portfolio_trades từ SQLite: %s", e)

            # C. Đồng bộ alert_states
            try:
                cur.execute("SELECT symbol, last_alert_type, last_alert_time, flip_count_today, last_ribbon_color, pending_summary, updated_at FROM alert_states")
                alerts = cur.fetchall()
                for a in alerts:
                    alert_coll.update_one(
                        {'symbol': a['symbol']},
                        {'$set': dict(a)},
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


if __name__ == '__main__':
    print("=" * 60)
    print(" STOCK RT - MONGODB CLOUD SYNC TOOL")
    print("=" * 60)
    success = sync_local_sqlite_to_mongodb()
    if success:
        print("\n✅ Hoàn tất đồng bộ dữ liệu lên MongoDB Atlas!")
    else:
        print("\n⚠️ Đồng bộ chưa hoàn thành. Vui lòng kiểm tra lại cấu hình MONGODB_URI.")

