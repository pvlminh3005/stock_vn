"""
Stock RT - Portfolio Database Manager (Pure MongoDB Atlas Cloud)
Quản lý toàn bộ giao dịch danh mục, cấu hình, cảnh báo và log Telegram 100% trên MongoDB Atlas.
Loại bỏ hoàn toàn SQLite local.
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union

logger = logging.getLogger('portfolio_db')

from backend.config.env_loader import (
    load_environment,
    get_app_env,
    is_production,
    get_mongodb_config,
)
from backend.constants.db import (
    COLL_PORTFOLIO_TRADES,
    COLL_PORTFOLIO_SETTINGS,
    COLL_ALERT_STATES,
    COLL_TELEGRAM_ALERT_LOGS,
    COLL_TELEGRAM_SENT_LOGS,
    COLL_FUNDAMENTALS,
    COLL_VCI_HISTORY,
    COLL_MARKET_SNAPSHOT,
)
from backend.models.db_models import (
    PortfolioTrade,
    PortfolioSetting,
    AlertState,
    TelegramAlertLog,
    TelegramSentLog,
    FundamentalItem,
    VciHistoryItem,
    MarketBoardSnapshot,
)
from backend.utils.datetime_helpers import VN_TZ

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Tự động nạp cấu hình đa môi trường
load_environment()
MONGODB_URI, MONGODB_DB_NAME = get_mongodb_config()
RETENTION_DAYS = int(os.environ.get('PORTFOLIO_RETENTION_DAYS', 180))

_mongo_client = None
_mongo_db = None
_use_mongo = False
_last_reconnect_attempt = 0.0
_RECONNECT_COOLDOWN_SEC = 5.0


def init_portfolio_db(retries: int = 3, retry_delay: float = 2.0) -> bool:
    """Khởi tạo kết nối MongoDB Atlas theo profile môi trường có cơ chế retry tự động."""
    global _mongo_client, _mongo_db, _use_mongo, MONGODB_URI, MONGODB_DB_NAME

    # Cập nhật cấu hình mới nhất từ env_loader
    MONGODB_URI, MONGODB_DB_NAME = get_mongodb_config()
    current_env = get_app_env()

    if not MONGODB_URI:
        logger.warning(
            "CẢNH BÁO [%s]: MONGODB_URI chưa được cấu hình! Tạm thời vô hiệu hóa MongoDB.",
            current_env.upper()
        )
        return False

    from pymongo import MongoClient
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

    for attempt in range(1, retries + 1):
        try:
            client = MongoClient(MONGODB_URI, **mongo_kwargs)
            # Ping kiểm tra kết nối với cụm replica set
            client.admin.command('ping')
            _mongo_client = client
            _mongo_db = _mongo_client[MONGODB_DB_NAME]
            _use_mongo = True

            env_tag = "🔴 PROD (DỮ LIỆU THẬT)" if is_production() else f"🟢 {current_env.upper()} (CÁCH LY AN TOÀN)"
            logger.info(
                "Kết nối MongoDB thành công [%s]: %s (Database: %s)",
                env_tag,
                MONGODB_URI.split('@')[-1] if '@' in MONGODB_URI else 'Local Mongo',
                MONGODB_DB_NAME
            )

            # 1. Index cho portfolio_trades
            trades_coll = _mongo_db[COLL_PORTFOLIO_TRADES]
            trades_coll.create_index(PortfolioTrade.INDEX_EXPIRE_AT, expireAfterSeconds=0)
            trades_coll.create_index(PortfolioTrade.INDEX_SYMBOL)
            trades_coll.create_index(PortfolioTrade.INDEX_ORDER_TYPE)

            # 2. Index cho portfolio_settings
            _mongo_db[COLL_PORTFOLIO_SETTINGS].create_index(PortfolioSetting.INDEX_KEY, unique=True)

            # 3. Index cho alert states & telegram alert logs
            _mongo_db[COLL_ALERT_STATES].create_index(AlertState.INDEX_SYMBOL, unique=True)
            _mongo_db[COLL_TELEGRAM_ALERT_LOGS].create_index(TelegramAlertLog.INDEX_KEY, unique=True)
            _mongo_db[COLL_TELEGRAM_ALERT_LOGS].create_index(TelegramAlertLog.INDEX_SENT_AT, expireAfterSeconds=86400 * 7)
            _mongo_db[COLL_TELEGRAM_SENT_LOGS].create_index(TelegramSentLog.INDEX_SENT_AT_DESC)
            _mongo_db[COLL_TELEGRAM_SENT_LOGS].create_index(TelegramSentLog.INDEX_SENT_AT_ASC, expireAfterSeconds=86400 * 30)

            # 4. Index cho fundamentals & market snapshot
            _mongo_db[COLL_FUNDAMENTALS].create_index(FundamentalItem.INDEX_SYMBOL, unique=True)
            _mongo_db[COLL_VCI_HISTORY].create_index(VciHistoryItem.INDEX_SYMBOL, unique=True)
            _mongo_db[COLL_MARKET_SNAPSHOT].create_index(MarketBoardSnapshot.INDEX_KEY, unique=True)

            return True
        except Exception as e:
            if attempt < retries:
                logger.warning("Thử lại kết nối MongoDB Atlas lần %d/%d (lỗi: %s)...", attempt, retries, e)
                time.sleep(retry_delay)
            else:
                logger.error("Lỗi kết nối MongoDB Atlas sau %d lần thử: %s", retries, e)

    _use_mongo = False
    return False


def get_mongo_db():
    """Lấy database MongoDB instance, tự động kết nối lại (auto-reconnect) nếu bị ngắt kết nối."""
    global _last_reconnect_attempt
    if _use_mongo and _mongo_db is not None:
        return _mongo_db

    now = time.time()
    if now - _last_reconnect_attempt >= _RECONNECT_COOLDOWN_SEC:
        _last_reconnect_attempt = now
        if init_portfolio_db(retries=2, retry_delay=1.0):
            return _mongo_db
    return None


# Tự động init khi import
init_portfolio_db()


def save_setting(key: str, value: str) -> bool:
    """Lưu cài đặt danh mục (ví dụ total_nav) vào MongoDB thông qua PortfolioSetting Model."""
    db = get_mongo_db()
    if db is None:
        logger.warning("MongoDB chưa sẵn sàng, bỏ qua save_setting (%s)", key)
        return False

    setting = PortfolioSetting(key=key, value=str(value))
    try:
        db[COLL_PORTFOLIO_SETTINGS].update_one(
            PortfolioSetting.filter_by_key(setting.key),
            {'$set': setting.to_doc()},
            upsert=True
        )
        return True
    except Exception as e:
        logger.error("MongoDB save_setting error: %s", e)
        return False


def get_setting(key: str, default: str = "") -> str:
    """Lấy giá trị cài đặt danh mục từ MongoDB thông qua PortfolioSetting Model."""
    db = get_mongo_db()
    if db is None:
        return default

    try:
        doc = db[COLL_PORTFOLIO_SETTINGS].find_one(PortfolioSetting.filter_by_key(key))
        if doc:
            return PortfolioSetting.from_doc(doc).value
    except Exception as e:
        logger.error("MongoDB get_setting error: %s", e)
    return default


def add_trade(trade: Union[PortfolioTrade, Dict[str, Any]]) -> Optional[str]:
    """Thêm giao dịch mới vào MongoDB thông qua PortfolioTrade Model."""
    db = get_mongo_db()
    if db is None:
        logger.error("MongoDB chưa sẵn sàng, không thể thêm giao dịch!")
        return None

    trade_obj = trade if isinstance(trade, PortfolioTrade) else PortfolioTrade.from_doc(trade)
    now_dt = datetime.now(VN_TZ)

    if trade_obj.order_type == 'SELL' or trade_obj.status == 'CLOSED':
        trade_obj.expire_at = now_dt + timedelta(days=RETENTION_DAYS)

    try:
        res = db[COLL_PORTFOLIO_TRADES].insert_one(trade_obj.to_doc())
        return str(res.inserted_id)
    except Exception as e:
        logger.error("MongoDB add_trade error: %s", e)
        return None


def get_all_trade_models() -> List[PortfolioTrade]:
    """Lấy danh sách tất cả các giao dịch trong sổ lệnh dưới dạng typed PortfolioTrade Object."""
    db = get_mongo_db()
    if db is None:
        return []

    try:
        cursor = db[COLL_PORTFOLIO_TRADES].find().sort([PortfolioTrade.SORT_TRADE_DATE_DESC])
        return [PortfolioTrade.from_doc(doc) for doc in cursor]
    except Exception as e:
        logger.error("MongoDB get_all_trade_models error: %s", e)
        return []


def get_all_trades() -> List[Dict[str, Any]]:
    """Lấy danh sách tất cả các giao dịch trong sổ lệnh từ MongoDB thông qua PortfolioTrade Model."""
    return [t.to_dict() for t in get_all_trade_models()]


def delete_trade(trade_id: str) -> bool:
    """
    Xóa một giao dịch theo id thông qua PortfolioTrade Model.
    Đồng thời kiểm tra nếu mã đó không còn lệnh MUA nào đang nắm giữ,
    tự động dọn sạch alert_states tương ứng để tránh bị rác hoặc cảnh báo sót.
    """
    db = get_mongo_db()
    if db is None:
        logger.error("MongoDB chưa sẵn sàng, không thể xóa giao dịch!")
        return False

    trade = None
    query_id = PortfolioTrade.filter_by_id(trade_id)
    try:
        trade = db[COLL_PORTFOLIO_TRADES].find_one(query_id)
    except Exception:
        pass

    if not trade:
        try:
            trade = db[COLL_PORTFOLIO_TRADES].find_one(PortfolioTrade.filter_by_id_str(str(trade_id)))
        except Exception:
            pass

    deleted = False
    try:
        res = db[COLL_PORTFOLIO_TRADES].delete_one(query_id)
        deleted = res.deleted_count > 0
    except Exception:
        pass

    if not deleted:
        try:
            res = db[COLL_PORTFOLIO_TRADES].delete_one(PortfolioTrade.filter_by_id_str(str(trade_id)))
            deleted = res.deleted_count > 0
        except Exception as e:
            logger.error("MongoDB delete_trade error: %s", e)
            return False

    if deleted and trade:
        sym = trade.get(PortfolioTrade.F_SYMBOL, '').strip().upper()
        if sym:
            remaining = db[COLL_PORTFOLIO_TRADES].count_documents(
                PortfolioTrade.filter_by_symbol_and_type(sym, 'BUY')
            )
            if remaining == 0:
                try:
                    db[COLL_ALERT_STATES].delete_one(AlertState.filter_by_symbol(sym))
                    logger.info("Đã xóa alert_states cho mã %s vì không còn lệnh BUY trong danh mục.", sym)
                except Exception as e_alert:
                    logger.warning("Lỗi xóa alert_states cho mã %s: %s", sym, e_alert)

    return deleted


def reset_all_trades(force_prod: bool = False) -> bool:
    """Xóa trắng toàn bộ giao dịch trong sổ lệnh và dọn sạch alert_states trong MongoDB.
    Trên môi trường PRODUCTION, bắt buộc phải truyền force_prod=True để tránh xóa nhầm dữ liệu thật.
    """
    db = get_mongo_db()
    if db is None:
        return False

    if is_production() and not force_prod:
        logger.warning(
            "CẢNH BÁO AN TOÀN: Thao tác reset toàn bộ sổ lệnh trên môi trường PRODUCTION bị chặn! "
            "Cần truyền force_prod=True để xác nhận xóa thật."
        )
        return False

    try:
        db[COLL_PORTFOLIO_TRADES].delete_many({})
        db[COLL_ALERT_STATES].delete_many({})
        logger.info("Đã xóa sạch portfolio_trades và alert_states trong MongoDB (%s).", MONGODB_DB_NAME)
        return True
    except Exception as e:
        logger.error("MongoDB reset_all_trades error: %s", e)
        return False


def get_active_holding_symbols() -> List[str]:
    """Lấy danh sách mã CK duy nhất đang có vị thế MUA (HOLDING) từ MongoDB."""
    db = get_mongo_db()
    if db is None:
        return []

    try:
        symbols = db[COLL_PORTFOLIO_TRADES].distinct(
            PortfolioTrade.F_SYMBOL,
            PortfolioTrade.filter_active_holdings()
        )
        return sorted([s.strip().upper() for s in symbols if s and s.strip()])
    except Exception as e:
        logger.error("MongoDB get_active_holding_symbols error: %s", e)
        return []


# ==================== ALERT STATES (Chống spam Telegram) ====================
def get_alert_state(symbol: str) -> Dict[str, Any]:
    """Lấy trạng thái cảnh báo gần nhất của một mã từ MongoDB thông qua AlertState Model."""
    sym = symbol.upper()
    db = get_mongo_db()
    if db is None:
        return AlertState(symbol=sym).to_dict()

    try:
        doc = db[COLL_ALERT_STATES].find_one(AlertState.filter_by_symbol(sym))
        if doc:
            doc.pop('_id', None)
            return AlertState.from_doc(doc, symbol=sym).to_dict()
    except Exception as e:
        logger.error("MongoDB get_alert_state error: %s", e)

    return AlertState(symbol=sym).to_dict()


def save_alert_state(symbol: str, data: Union[AlertState, Dict[str, Any]]) -> bool:
    """Cập nhật trạng thái cảnh báo của một mã vào MongoDB thông qua AlertState Model."""
    db = get_mongo_db()
    if db is None:
        return False

    sym = symbol.upper()
    if isinstance(data, AlertState):
        state_obj = data
    else:
        state_obj = AlertState.from_doc(data, symbol=sym)

    try:
        db[COLL_ALERT_STATES].update_one(
            AlertState.filter_by_symbol(sym),
            {'$set': state_obj.to_doc()},
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
    db = get_mongo_db()
    if db is None:
        return False

    now_ts = int(time.time())
    try:
        doc = db[COLL_TELEGRAM_ALERT_LOGS].find_one(TelegramAlertLog.filter_by_key(alert_key))
        if doc:
            log_item = TelegramAlertLog.from_doc(doc)
            from backend.utils.datetime_helpers import to_timestamp_int
            sent_ts = to_timestamp_int(log_item.sent_at)
            if now_ts - sent_ts < min_interval_seconds:
                return True
        return False
    except Exception as e:
        logger.warning("MongoDB is_alert_already_sent error: %s", e)
        return False


def record_alert_sent(alert_key: str, preview: str = '') -> bool:
    """Ghi nhận cảnh báo Telegram đã gửi thành công để chống trùng lặp đa tiến trình/đám mây."""
    db = get_mongo_db()
    if db is None:
        return False

    log_item = TelegramAlertLog(key=alert_key, preview=preview)
    try:
        db[COLL_TELEGRAM_ALERT_LOGS].update_one(
            TelegramAlertLog.filter_by_key(alert_key),
            {'$set': log_item.to_doc()},
            upsert=True
        )
        return True
    except Exception as e:
        logger.warning("MongoDB record_alert_sent error: %s", e)
        return False


def save_telegram_sent_log(
    alert_type: Any,
    title: str = '',
    stocks: Optional[list] = None,
    market_regime: Optional[str] = None,
    vnindex: Optional[dict] = None,
    message_id: Optional[int] = None,
    status: str = 'SUCCESS',
) -> bool:
    """
    Lưu log cảnh báo đã push qua Telegram vào MongoDB Atlas.
    Chỉ lưu các thông tin cần thiết và có cấu trúc (mã, giá, % thay đổi, action, vùng gom, R:R),
    không lưu HTML dài để tối ưu dung lượng và tiện tra cứu audit.
    Hỗ trợ cả truyền dict (log_meta) hoặc các tham số rời.
    """
    db = get_mongo_db()
    if db is None:
        return False

    if isinstance(alert_type, dict):
        d = alert_type
        title = d.get('title', title)
        stocks = d.get('stocks', stocks)
        market_regime = d.get('market_regime', market_regime)
        vnindex = d.get('vnindex', vnindex)
        message_id = d.get('message_id', message_id)
        status = d.get('status', status)
        alert_type = d.get('alert_type', 'GENERAL_ALERT')

    now_ts = int(time.time())
    # Giờ chuẩn Việt Nam GMT+7
    vn_time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(now_ts + 7 * 3600))

    clean_stocks = []
    for s in (stocks or []):
        if not isinstance(s, dict):
            continue
        clean_stocks.append({
            'symbol': s.get('symbol', '').upper(),
            'name': s.get('name', ''),
            'price': float(s.get('price', 0)),
            'change_pct': float(s.get('change_pct') if s.get('change_pct') is not None else (s.get('changePct') if s.get('changePct') is not None else s.get('percentChange', 0.0))),
            'vol_ratio': float(s.get('vol_ratio') if s.get('vol_ratio') is not None else (s.get('volRunRate') if s.get('volRunRate') is not None else s.get('volRatio', 1.0))),
            'action': s.get('actionLabel') or s.get('action') or s.get('badge', ''),
            'entry_zone': s.get('entry_zone') or s.get('entryZone') or s.get('buyZone', ''),
            'target1': s.get('target1') or s.get('target1Display', ''),
            'target2': s.get('target2') or s.get('target2Display', ''),
            'stop_loss': s.get('stop_loss') or s.get('stopLoss') or s.get('stopLossDisplay', ''),
            'net_rr': float(s.get('net_rr') if s.get('net_rr') is not None else (s.get('netRR', 0.0) if s.get('netRR') is not None else 0.0)),
        })

    sent_log = TelegramSentLog(
        alert_type=str(alert_type).upper(),
        title=title,
        sent_at=now_ts,
        sent_time_vn=vn_time_str,
        market_regime=market_regime,
        vnindex=vnindex,
        stocks=clean_stocks,
        message_id=message_id,
        status=status,
    )

    try:
        res = db[COLL_TELEGRAM_SENT_LOGS].insert_one(sent_log.to_doc())
        return str(res.inserted_id) if res.inserted_id else True
    except Exception as e:
        logger.warning("MongoDB save_telegram_sent_log error: %s", e)
        return False


def get_telegram_sent_logs(limit: int = 50) -> list:
    """Lấy danh sách lịch sử cảnh báo Telegram đã gửi từ MongoDB Atlas thông qua TelegramSentLog Model."""
    db = get_mongo_db()
    if db is None:
        return []

    try:
        cursor = db[COLL_TELEGRAM_SENT_LOGS].find().sort([TelegramSentLog.SORT_SENT_AT_DESC]).limit(limit)
        return [TelegramSentLog.from_doc(doc).to_dict() for doc in cursor]
    except Exception as e:
        logger.warning("MongoDB get_telegram_sent_logs error: %s", e)
        return []
