"""
Stock RT - Quản lý Lưu trữ Cơ sở Dữ liệu (Pure MongoDB Atlas Cloud)
Hồ sơ phân tích cơ bản (fundamentals) và lịch sử VCI được lưu trữ 100% trên MongoDB Atlas.
Loại bỏ hoàn toàn SQLite local.
"""
import time

_MEM_FUNDAMENTALS_CACHE = {}


def _get_mongo():
    """Lấy kết nối MongoDB Atlas nếu có cấu hình."""
    try:
        from backend.db.portfolio_db import _mongo_db, _use_mongo
        if _use_mongo and _mongo_db is not None:
            return _mongo_db
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
            doc = mongo['fundamentals'].find_one({'symbol': sym})
            if doc:
                doc.pop('_id', None)
                updated_at = doc.get('updated_at', 0)
                if time.time() - updated_at < 604800:
                    # Kiểm tra tính hợp lệ của dữ liệu (tránh cache 0.0 bị lưu trước đây)
                    has_valid_metrics = (
                        doc.get('pe', 0) > 0 or doc.get('pb', 0) > 0 or doc.get('eps', 0) > 0 or doc.get('roe', 0) != 0
                    )
                    if has_valid_metrics and doc.get('reportPeriod'):
                        _MEM_FUNDAMENTALS_CACHE[sym] = (doc, updated_at)
                        return doc
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
            doc = dict(data)
            doc['symbol'] = sym
            doc['updated_at'] = now
            mongo['fundamentals'].update_one({'symbol': sym}, {'$set': doc}, upsert=True)
        except Exception as e_mongo:
            print(f'Lỗi ghi MongoDB fundamentals {sym}:', e_mongo)
