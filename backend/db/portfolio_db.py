"""
Stock RT - Portfolio Database Manager
Hỗ trợ lưu trữ kép:
1. Ưu tiên MongoDB Atlas (nếu có biến môi trường MONGODB_URI)
   - Tự động tạo TTL index xóa các lệnh đã bán sau 180 ngày (PORTFOLIO_RETENTION_DAYS).
2. Tự động fallback sang SQLite local (data/portfolio.db hoặc DB_PATH) nếu chưa cấu hình MongoDB.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import sqlite3

logger = logging.getLogger('portfolio_db')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Tự động nạp file .env nội bộ nếu có
_env_path = os.path.join(BASE_DIR, '.env')
if os.path.isfile(_env_path):
    try:
        with open(_env_path, 'r', encoding='utf-8') as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith('#') and '=' in _line:
                    _k, _v = _line.split('=', 1)
                    _k = _k.strip()
                    _v = _v.strip().strip("'\"")
                    if _k:
                        os.environ[_k] = _v
    except Exception:
        pass

MONGODB_URI = os.environ.get('MONGODB_URI', '').strip().strip("'\"")
MONGODB_DB_NAME = os.environ.get('MONGODB_DB_NAME', 'stock_pro_db').strip().strip("'\"")
RETENTION_DAYS = int(os.environ.get('PORTFOLIO_RETENTION_DAYS', 180))

# Đường dẫn DB SQLite fallback
SQLITE_PORTFOLIO_DB = os.path.join(BASE_DIR, 'data', 'portfolio.db')

_mongo_client = None
_mongo_db = None
_use_mongo = False


def init_portfolio_db():
    """Khởi tạo kết nối DB (MongoDB Atlas hoặc SQLite)."""
    global _mongo_client, _mongo_db, _use_mongo
    os.makedirs(os.path.dirname(SQLITE_PORTFOLIO_DB), exist_ok=True)

    if MONGODB_URI:
        try:
            from pymongo import MongoClient, ASCENDING, IndexModel
            mongo_kwargs = {'serverSelectionTimeoutMS': 5000}
            try:
                import certifi
                mongo_kwargs['tlsCAFile'] = certifi.where()
            except ImportError:
                pass
            client = MongoClient(MONGODB_URI, **mongo_kwargs)
            # Kiểm tra kết nối
            client.admin.command('ping')
            _mongo_client = client
            _mongo_db = _mongo_client[MONGODB_DB_NAME]
            _use_mongo = True
            logger.info("Kết nối MongoDB thành công: %s (DB: %s)", MONGODB_URI.split('@')[-1] if '@' in MONGODB_URI else 'Local Mongo', MONGODB_DB_NAME)

            # Khởi tạo TTL Index cho các lệnh đã bán/đóng sau RETENTION_DAYS
            trades_coll = _mongo_db['portfolio_trades']
            trades_coll.create_index([("expire_at", ASCENDING)], expireAfterSeconds=0)
            trades_coll.create_index([("symbol", ASCENDING)])
            trades_coll.create_index([("order_type", ASCENDING)])

            # Index cho alert states
            _mongo_db['alert_states'].create_index([("symbol", ASCENDING)], unique=True)

            # Tự động đồng bộ nếu MongoDB đang rỗng mà SQLite local có dữ liệu
            if trades_coll.count_documents({}) == 0 and os.path.exists(SQLITE_PORTFOLIO_DB):
                try:
                    from backend.db.sync_to_mongo import sync_local_sqlite_to_mongodb
                    sync_local_sqlite_to_mongodb(MONGODB_URI, MONGODB_DB_NAME)
                except Exception as e_sync:
                    logger.warning("Lỗi tự động sync SQLite lên MongoDB: %s", e_sync)

            return True
        except Exception as e:
            logger.warning("Không thể kết nối MongoDB (%s). Tự động chuyển sang dùng SQLite local.", e)
            _use_mongo = False

    # Khởi tạo bảng SQLite fallback
    try:
        with sqlite3.connect(SQLITE_PORTFOLIO_DB) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    order_type TEXT NOT NULL, -- 'BUY' hoặc 'SELL'
                    volume INTEGER NOT NULL,
                    price REAL NOT NULL,
                    trade_date TEXT NOT NULL,
                    note TEXT DEFAULT '',
                    status TEXT DEFAULT 'HOLDING', -- 'HOLDING' hoặc 'CLOSED'
                    expire_at INTEGER DEFAULT NULL,
                    created_at INTEGER NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sym ON portfolio_trades(symbol)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON portfolio_trades(order_type)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_states (
                    symbol TEXT PRIMARY KEY,
                    last_alert_type TEXT,
                    last_alert_time INTEGER,
                    flip_count_today INTEGER DEFAULT 0,
                    last_ribbon_color TEXT DEFAULT '',
                    pending_summary TEXT DEFAULT '',
                    updated_at INTEGER NOT NULL
                )
            """)
        cleanup_sqlite_expired()
        logger.info("Khởi tạo SQLite Portfolio DB thành công: %s", SQLITE_PORTFOLIO_DB)
        return True
    except Exception as e:
        logger.error("Lỗi khởi tạo SQLite Portfolio DB: %s", e)
        return False


def cleanup_sqlite_expired():
    """Tự động xóa các bản ghi lệnh đã bán quá hạn trong SQLite."""
    if _use_mongo:
        return
    try:
        now_ts = int(time.time())
        with sqlite3.connect(SQLITE_PORTFOLIO_DB) as conn:
            conn.execute(
                "DELETE FROM portfolio_trades WHERE expire_at IS NOT NULL AND expire_at <= ?",
                (now_ts,)
            )
    except Exception as e:
        logger.warning("Lỗi dọn dẹp SQLite expired records: %s", e)


# Tự động init khi import
init_portfolio_db()


def save_setting(key: str, value: str) -> bool:
    """Lưu cài đặt danh mục (ví dụ total_nav)."""
    now_ts = int(time.time())
    if _use_mongo and _mongo_db is not None:
        try:
            _mongo_db['portfolio_settings'].update_one(
                {'key': key},
                {'$set': {'key': key, 'value': str(value), 'updated_at': now_ts}},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error("MongoDB save_setting error: %s", e)

    try:
        with sqlite3.connect(SQLITE_PORTFOLIO_DB) as conn:
            conn.execute(
                "INSERT INTO portfolio_settings (key, value, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, str(value), now_ts)
            )
        return True
    except Exception as e:
        logger.error("SQLite save_setting error: %s", e)
        return False


def get_setting(key: str, default: str = "") -> str:
    """Lấy giá trị cài đặt danh mục."""
    if _use_mongo and _mongo_db is not None:
        try:
            doc = _mongo_db['portfolio_settings'].find_one({'key': key})
            if doc:
                return doc.get('value', default)
        except Exception as e:
            logger.error("MongoDB get_setting error: %s", e)

    try:
        with sqlite3.connect(SQLITE_PORTFOLIO_DB) as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM portfolio_settings WHERE key = ?", (key,))
            row = cur.fetchone()
            if row:
                return row[0]
    except Exception as e:
        logger.error("SQLite get_setting error: %s", e)
    return default


def add_trade(trade: Dict[str, Any]) -> Optional[str]:
    """
    Thêm giao dịch mới.
    trade = {
        'symbol': 'HPG',
        'order_type': 'BUY' | 'SELL',
        'volume': 5000,
        'price': 27500,
        'trade_date': '2026-11-05',
        'note': 'Gom theo SuperTrend',
        'status': 'HOLDING' | 'CLOSED'
    }
    """
    symbol = trade.get('symbol', '').strip().upper()
    order_type = trade.get('order_type', 'BUY').strip().upper()
    volume = int(trade.get('volume', 0))
    price = float(trade.get('price', 0))
    trade_date = trade.get('trade_date', datetime.now().strftime('%Y-%m-%d')).strip()
    note = trade.get('note', '').strip()
    status = trade.get('status', 'HOLDING' if order_type == 'BUY' else 'CLOSED')

    now_dt = datetime.now()
    now_ts = int(time.time())

    # Tính hạn expire_at nếu là lệnh BÁN (hoặc đã đóng) -> Sau RETENTION_DAYS ngày tự xóa
    expire_dt = None
    expire_ts = None
    if order_type == 'SELL' or status == 'CLOSED':
        expire_dt = now_dt + timedelta(days=RETENTION_DAYS)
        expire_ts = int(expire_dt.timestamp())

    if _use_mongo and _mongo_db is not None:
        try:
            doc = {
                'symbol': symbol,
                'order_type': order_type,
                'volume': volume,
                'price': price,
                'trade_date': trade_date,
                'note': note,
                'status': status,
                'created_at': now_dt,
                'expire_at': expire_dt
            }
            res = _mongo_db['portfolio_trades'].insert_one(doc)
            return str(res.inserted_id)
        except Exception as e:
            logger.error("MongoDB add_trade error: %s", e)

    try:
        with sqlite3.connect(SQLITE_PORTFOLIO_DB) as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO portfolio_trades (symbol, order_type, volume, price, trade_date, note, status, expire_at, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, order_type, volume, price, trade_date, note, status, expire_ts, now_ts))
            return str(cur.lastrowid)
    except Exception as e:
        logger.error("SQLite add_trade error: %s", e)
        return None


def get_all_trades() -> List[Dict[str, Any]]:
    """Lấy danh sách tất cả các giao dịch trong sổ lệnh."""
    if _use_mongo and _mongo_db is not None:
        try:
            cursor = _mongo_db['portfolio_trades'].find().sort('trade_date', -1)
            trades = []
            for doc in cursor:
                doc['id'] = str(doc.get('_id'))
                doc.pop('_id', None)
                if isinstance(doc.get('created_at'), datetime):
                    doc['created_at'] = int(doc['created_at'].timestamp())
                if isinstance(doc.get('expire_at'), datetime):
                    doc['expire_at'] = int(doc['expire_at'].timestamp())
                trades.append(doc)
            return trades
        except Exception as e:
            logger.error("MongoDB get_all_trades error: %s", e)

    cleanup_sqlite_expired()
    trades = []
    try:
        with sqlite3.connect(SQLITE_PORTFOLIO_DB) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM portfolio_trades ORDER BY trade_date DESC, id DESC")
            rows = cur.fetchall()
            for r in rows:
                trades.append(dict(r))
    except Exception as e:
        logger.error("SQLite get_all_trades error: %s", e)
    return trades


def delete_trade(trade_id: str) -> bool:
    """Xóa một giao dịch theo id."""
    if _use_mongo and _mongo_db is not None:
        try:
            from bson import ObjectId
            res = _mongo_db['portfolio_trades'].delete_one({'_id': ObjectId(trade_id)})
            return res.deleted_count > 0
        except Exception:
            # Fallback nếu id là string thường
            try:
                res = _mongo_db['portfolio_trades'].delete_one({'id': trade_id})
                return res.deleted_count > 0
            except Exception as e:
                logger.error("MongoDB delete_trade error: %s", e)

    try:
        with sqlite3.connect(SQLITE_PORTFOLIO_DB) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM portfolio_trades WHERE id = ?", (trade_id,))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("SQLite delete_trade error: %s", e)
        return False


def reset_all_trades() -> bool:
    """Xóa trắng toàn bộ giao dịch trong sổ lệnh (Reset)."""
    if _use_mongo and _mongo_db is not None:
        try:
            _mongo_db['portfolio_trades'].delete_many({})
            return True
        except Exception as e:
            logger.error("MongoDB reset_all_trades error: %s", e)

    try:
        with sqlite3.connect(SQLITE_PORTFOLIO_DB) as conn:
            conn.execute("DELETE FROM portfolio_trades")
        return True
    except Exception as e:
        logger.error("SQLite reset_all_trades error: %s", e)
        return False


def get_active_holding_symbols() -> List[str]:
    """Lấy danh sách mã CK duy nhất đang có vị thế MUA (HOLDING)."""
    trades = get_all_trades()
    symbols = set()
    for t in trades:
        if t.get('order_type') == 'BUY':
            sym = t.get('symbol', '').strip().upper()
            if sym:
                symbols.add(sym)
    return sorted(list(symbols))


# Quản lý Alert State (Chống spam Telegram)
def get_alert_state(symbol: str) -> Dict[str, Any]:
    """Lấy trạng thái cảnh báo gần nhất của một mã."""
    sym = symbol.upper()
    if _use_mongo and _mongo_db is not None:
        try:
            doc = _mongo_db['alert_states'].find_one({'symbol': sym})
            if doc:
                doc.pop('_id', None)
                return doc
        except Exception as e:
            logger.error("MongoDB get_alert_state error: %s", e)

    try:
        with sqlite3.connect(SQLITE_PORTFOLIO_DB) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM alert_states WHERE symbol = ?", (sym,))
            row = cur.fetchone()
            if row:
                return dict(row)
    except Exception as e:
        logger.error("SQLite get_alert_state error: %s", e)
    return {
        'symbol': sym,
        'last_alert_type': '',
        'last_alert_time': 0,
        'flip_count_today': 0,
        'last_ribbon_color': '',
        'pending_summary': '',
        'updated_at': 0
    }


def save_alert_state(symbol: str, data: Dict[str, Any]) -> bool:
    """Cập nhật trạng thái cảnh báo của một mã."""
    sym = symbol.upper()
    now_ts = int(time.time())
    data['updated_at'] = now_ts
    data['symbol'] = sym

    if _use_mongo and _mongo_db is not None:
        try:
            _mongo_db['alert_states'].update_one(
                {'symbol': sym},
                {'$set': data},
                upsert=True
            )
            return True
        except Exception as e:
            logger.error("MongoDB save_alert_state error: %s", e)

    try:
        with sqlite3.connect(SQLITE_PORTFOLIO_DB) as conn:
            conn.execute("""
                INSERT INTO alert_states (symbol, last_alert_type, last_alert_time, flip_count_today, last_ribbon_color, pending_summary, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    last_alert_type = excluded.last_alert_type,
                    last_alert_time = excluded.last_alert_time,
                    flip_count_today = excluded.flip_count_today,
                    last_ribbon_color = excluded.last_ribbon_color,
                    pending_summary = excluded.pending_summary,
                    updated_at = excluded.updated_at
            """, (
                sym,
                data.get('last_alert_type', ''),
                data.get('last_alert_time', 0),
                data.get('flip_count_today', 0),
                data.get('last_ribbon_color', ''),
                data.get('pending_summary', ''),
                now_ts
            ))
        return True
    except Exception as e:
        logger.error("SQLite save_alert_state error: %s", e)
        return False

