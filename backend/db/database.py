"""
Stock RT - Quản lý Lưu trữ Cơ sở Dữ liệu (Pure MongoDB Atlas Cloud)
Hồ sơ phân tích cơ bản (fundamentals) và lịch sử VCI được lưu trữ 100% trên MongoDB Atlas.
Loại bỏ hoàn toàn SQLite local.
"""
import time

_MEM_FUNDAMENTALS_CACHE = {}


def _get_mongo():
    """Lấy kết nối MongoDB Atlas nếu có cấu hình (hỗ trợ auto-reconnect)."""
    try:
        from backend.db.portfolio_db import get_mongo_db
        return get_mongo_db()
    except Exception:
        pass
    return None


def init_all_db():
    """Khởi tạo kết nối MongoDB Atlas."""
    pass


init_db = init_all_db


def get_cached_fundamental(symbol):
    """Lấy hồ sơ cơ bản từ cache bộ nhớ hoặc MongoDB Atlas."""
    sym = symbol.upper()
    if sym in _MEM_FUNDAMENTALS_CACHE:
        item, ts = _MEM_FUNDAMENTALS_CACHE[sym]
        if time.time() - ts < 604800:  # 7 ngày
            # Chỉ trả về nếu cache có số liệu định giá thực tế (không phải bản 0.0)
            if item.get('pe', 0) > 0 or item.get('pb', 0) > 0 or item.get('eps', 0) > 0 or item.get('roe', 0) != 0:
                return item

    # Đọc từ MongoDB Atlas Cloud
    mongo = _get_mongo()
    if mongo is not None:
        try:
            from backend.constants.db import COLL_FUNDAMENTALS
            from backend.models.db_models import FundamentalItem
            doc = mongo[COLL_FUNDAMENTALS].find_one(FundamentalItem.filter_by_symbol(sym))
            if doc:
                item = FundamentalItem.from_doc(doc)
                from backend.utils.datetime_helpers import to_timestamp_int
                updated_at = to_timestamp_int(item.updated_at)
                if time.time() - updated_at < 604800:
                    # Kiểm tra tính hợp lệ của dữ liệu (tránh cache 0.0 bị lưu trước đây)
                    d = item.data
                    has_valid_metrics = (
                        d.get('pe', 0) > 0 or d.get('pb', 0) > 0 or d.get('eps', 0) > 0 or d.get('roe', 0) != 0
                    )
                    if has_valid_metrics and d.get('reportPeriod'):
                        _MEM_FUNDAMENTALS_CACHE[sym] = (d, updated_at)
                        return d
        except Exception as e_mongo:
            print(f'Lỗi đọc MongoDB fundamentals {sym}:', e_mongo)

    return None


def save_cached_fundamental(symbol, data):
    """Lưu hồ sơ cơ bản vào cache bộ nhớ và MongoDB Atlas."""
    sym = symbol.upper()
    now = int(time.time())
    _MEM_FUNDAMENTALS_CACHE[sym] = (data, now)

    # Lưu vào MongoDB Atlas Cloud
    mongo = _get_mongo()
    if mongo is not None:
        try:
            from backend.constants.db import COLL_FUNDAMENTALS
            from backend.models.db_models import FundamentalItem
            item = FundamentalItem(symbol=sym, data=dict(data), updated_at=now)
            mongo[COLL_FUNDAMENTALS].update_one(
                FundamentalItem.filter_by_symbol(sym),
                {'$set': item.to_doc()},
                upsert=True
            )
        except Exception as e_mongo:
            print(f'Lỗi ghi MongoDB fundamentals {sym}:', e_mongo)
