"""
Stock RT - Portfolio Database Manager (Pure MongoDB Atlas Cloud)
Quản lý toàn bộ giao dịch danh mục, cấu hình, cảnh báo và log Telegram 100% trên MongoDB Atlas.
Loại bỏ hoàn toàn SQLite local.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from bson import ObjectId

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

_mongo_client = None
_mongo_db = None
_use_mongo = False


def init_portfolio_db() -> bool:
    """Khởi tạo kết nối MongoDB Atlas."""
    global _mongo_client, _mongo_db, _use_mongo

    if not MONGODB_URI:
        logger.warning("CẢNH BÁO: MONGODB_URI chưa được cấu hình trong biến môi trường!")
        return False

    try:
        from pymongo import MongoClient, ASCENDING
        mongo_kwargs = {'serverSelectionTimeoutMS': 5000}
        try:
            import certifi
            mongo_kwargs['tlsCAFile'] = certifi.where()
        except ImportError:
            pass

        client = MongoClient(MONGODB_URI, **mongo_kwargs)
        # Ping kiểm tra kết nối
        client.admin.command('ping')
        _mongo_client = client
        _mongo_db = _mongo_client[MONGODB_DB_NAME]
        _use_mongo = True
        logger.info(
            "Kết nối MongoDB thành công: %s (DB: %s)",
            MONGODB_URI.split('@')[-1] if '@' in MONGODB_URI else 'Local Mongo',
            MONGODB_DB_NAME
        )

        # 1. Index cho portfolio_trades
        trades_coll = _mongo_db['portfolio_trades']
        trades_coll.create_index([("expire_at", ASCENDING)], expireAfterSeconds=0)
        trades_coll.create_index([("symbol", ASCENDING)])
        trades_coll.create_index([("order_type", ASCENDING)])

        # 2. Index cho portfolio_settings
        _mongo_db['portfolio_settings'].create_index([("key", ASCENDING)], unique=True)

        # 3. Index cho alert states & telegram alert logs
        _mongo_db['alert_states'].create_index([("symbol", ASCENDING)], unique=True)
        _mongo_db['telegram_alert_logs'].create_index([("key", ASCENDING)], unique=True)
        _mongo_db['telegram_alert_logs'].create_index([("sent_at", ASCENDING)], expireAfterSeconds=86400 * 7)

        # 4. Index cho fundamentals & market snapshot
        _mongo_db['fundamentals'].create_index([("symbol", ASCENDING)], unique=True)
        _mongo_db['vci_history'].create_index([("symbol", ASCENDING)], unique=True)
        _mongo_db['market_board_snapshot'].create_index([("key", ASCENDING)], unique=True)

        return True
    except Exception as e:
        logger.error("Lỗi kết nối MongoDB Atlas: %s", e)
        _use_mongo = False
        return False


# Tự động init khi import
init_portfolio_db()


def save_setting(key: str, value: str) -> bool:
    """Lưu cài đặt danh mục (ví dụ total_nav) vào MongoDB."""
    if not _use_mongo or _mongo_db is None:
        logger.warning("MongoDB chưa sẵn sàng, bỏ qua save_setting (%s)", key)
        return False

    now_ts = int(time.time())
    try:
        _mongo_db['portfolio_settings'].update_one(
            {'key': key},
            {'$set': {'key': key, 'value': str(value), 'updated_at': now_ts}},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error("MongoDB save_setting error: %s", e)
        return False


def get_setting(key: str, default: str = "") -> str:
    """Lấy giá trị cài đặt danh mục từ MongoDB."""
    if not _use_mongo or _mongo_db is None:
        return default

    try:
        doc = _mongo_db['portfolio_settings'].find_one({'key': key})
        if doc:
            return doc.get('value', default)
    except Exception as e:
        logger.error("MongoDB get_setting error: %s", e)
    return default


def add_trade(trade: Dict[str, Any]) -> Optional[str]:
    """Thêm giao dịch mới vào MongoDB."""
    if not _use_mongo or _mongo_db is None:
        logger.error("MongoDB chưa sẵn sàng, không thể thêm giao dịch!")
        return None

    symbol = trade.get('symbol', '').strip().upper()
    order_type = trade.get('order_type', 'BUY').strip().upper()
    volume = int(trade.get('volume', 0))
    price = float(trade.get('price', 0))
    trade_date = trade.get('trade_date', datetime.now().strftime('%Y-%m-%d')).strip()
    note = trade.get('note', '').strip()
    status = trade.get('status', 'HOLDING' if order_type == 'BUY' else 'CLOSED')

    now_dt = datetime.now()

    expire_dt = None
    if order_type == 'SELL' or status == 'CLOSED':
        expire_dt = now_dt + timedelta(days=RETENTION_DAYS)

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
        return None


def get_all_trades() -> List[Dict[str, Any]]:
    """Lấy danh sách tất cả các giao dịch trong sổ lệnh từ MongoDB."""
    if not _use_mongo or _mongo_db is None:
        return []

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
        return []


def delete_trade(trade_id: str) -> bool:
    """
    Xóa một giao dịch theo id.
    Đồng thời kiểm tra nếu mã đó không còn lệnh MUA nào đang nắm giữ,
    tự động dọn sạch alert_states tương ứng để tránh bị rác hoặc cảnh báo sót.
    """
    if not _use_mongo or _mongo_db is None:
        logger.error("MongoDB chưa sẵn sàng, không thể xóa giao dịch!")
        return False

    trade = None
    try:
        trade = _mongo_db['portfolio_trades'].find_one({'_id': ObjectId(trade_id)})
    except Exception:
        pass
    if not trade:
        trade = _mongo_db['portfolio_trades'].find_one({'id': trade_id})

    deleted = False
    try:
        res = _mongo_db['portfolio_trades'].delete_one({'_id': ObjectId(trade_id)})
        deleted = res.deleted_count > 0
    except Exception:
        pass

    if not deleted:
        try:
            res = _mongo_db['portfolio_trades'].delete_one({'id': trade_id})
            deleted = res.deleted_count > 0
        except Exception as e:
            logger.error("MongoDB delete_trade error: %s", e)
            return False

    if deleted and trade:
        sym = trade.get('symbol', '').strip().upper()
        if sym:
            remaining = _mongo_db['portfolio_trades'].count_documents({'symbol': sym, 'order_type': 'BUY'})
            if remaining == 0:
                try:
                    _mongo_db['alert_states'].delete_one({'symbol': sym})
                    logger.info("Đã xóa alert_states cho mã %s vì không còn lệnh BUY trong danh mục.", sym)
                except Exception as e_alert:
                    logger.warning("Lỗi xóa alert_states cho mã %s: %s", sym, e_alert)

    return deleted


def reset_all_trades() -> bool:
    """Xóa trắng toàn bộ giao dịch trong sổ lệnh và dọn sạch alert_states trong MongoDB."""
    if not _use_mongo or _mongo_db is None:
        return False

    try:
        _mongo_db['portfolio_trades'].delete_many({})
        _mongo_db['alert_states'].delete_many({})
        logger.info("Đã xóa sạch portfolio_trades và alert_states trong MongoDB.")
        return True
    except Exception as e:
        logger.error("MongoDB reset_all_trades error: %s", e)
        return False


def get_active_holding_symbols() -> List[str]:
    """Lấy danh sách mã CK duy nhất đang có vị thế MUA (HOLDING) từ MongoDB."""
    if not _use_mongo or _mongo_db is None:
        return []

    try:
        symbols = _mongo_db['portfolio_trades'].distinct('symbol', {'order_type': 'BUY'})
        return sorted([s.strip().upper() for s in symbols if s and s.strip()])
    except Exception as e:
        logger.error("MongoDB get_active_holding_symbols error: %s", e)
        return []


# ==================== ALERT STATES (Chống spam Telegram) ====================
def get_alert_state(symbol: str) -> Dict[str, Any]:
    """Lấy trạng thái cảnh báo gần nhất của một mã từ MongoDB."""
    sym = symbol.upper()
    default_state = {
        'symbol': sym,
        'last_alert_type': '',
        'last_alert_time': 0,
        'flip_count_today': 0,
        'last_ribbon_color': '',
        'pending_summary': '',
        'updated_at': 0
    }
    if not _use_mongo or _mongo_db is None:
        return default_state

    try:
        doc = _mongo_db['alert_states'].find_one({'symbol': sym})
        if doc:
            doc.pop('_id', None)
            return doc
    except Exception as e:
        logger.error("MongoDB get_alert_state error: %s", e)

    return default_state


def save_alert_state(symbol: str, data: Dict[str, Any]) -> bool:
    """Cập nhật trạng thái cảnh báo của một mã vào MongoDB."""
    if not _use_mongo or _mongo_db is None:
        return False

    sym = symbol.upper()
    now_ts = int(time.time())
    data['updated_at'] = now_ts
    data['symbol'] = sym

    try:
        _mongo_db['alert_states'].update_one(
            {'symbol': sym},
            {'$set': data},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error("MongoDB save_alert_state error: %s", e)
        return False


# ==================== DEDUPLICATION TELEGRAM PERSISTENCE ====================
def is_alert_already_sent(alert_key: str, min_interval_seconds: int = 7200) -> bool:
    """
    Kiểm tra xem một loại cảnh báo đã được gửi qua Telegram gần đây hay chưa (hỗ trợ phân tán Multi-Instance / Render + Local).
    Trả về True nếu ĐÃ gửi trong vòng min_interval_seconds giây qua.
    """
    if not _use_mongo or _mongo_db is None:
        return False

    now_ts = int(time.time())
    try:
        doc = _mongo_db['telegram_alert_logs'].find_one({'key': alert_key})
        if doc:
            sent_at = doc.get('sent_at', 0)
            if now_ts - sent_at < min_interval_seconds:
                return True
        return False
    except Exception as e:
        logger.warning("MongoDB is_alert_already_sent error: %s", e)
        return False


def record_alert_sent(alert_key: str, preview: str = '') -> bool:
    """Ghi nhận cảnh báo Telegram đã gửi thành công để chống trùng lặp đa tiến trình/đám mây."""
    if not _use_mongo or _mongo_db is None:
        return False

    now_ts = int(time.time())
    try:
        _mongo_db['telegram_alert_logs'].update_one(
            {'key': alert_key},
            {'$set': {'key': alert_key, 'sent_at': now_ts, 'preview': preview[:100]}},
            upsert=True
        )
        return True
    except Exception as e:
        logger.warning("MongoDB record_alert_sent error: %s", e)
        return False
