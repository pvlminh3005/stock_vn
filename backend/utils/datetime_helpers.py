"""
Stock RT - MongoDB Datetime Utilities
Cung cấp các hàm chuẩn hóa và chuyển đổi kiểu dữ liệu ngày/giờ dùng chung:
- to_mongo_datetime: Convert mọi input sang datetime UTC chuẩn để PyMongo ghi thành BSON ISODate (UTC+0).
  Khi MongoDB Compass hiển thị, Compass sẽ tự động cộng múi giờ địa phương (+07:00 Việt Nam) và hiển thị chính xác giờ thực tế.
- parse_db_datetime: Parse an toàn từ Mongo document (hỗ trợ cả bản ghi cũ dạng integer timestamp và bản ghi mới dạng ISODate).
  Tự động gán/chuyển đổi sang múi giờ Việt Nam (VN_TZ, GMT+7) để các tầng xử lý nghiệp vụ luôn đúng giờ thực.
- to_timestamp_int: Convert datetime sang UNIX timestamp integer phục vụ serialization trả về API JSON client.
- to_vn_datetime_str: Format hiển thị chuẩn giờ Việt Nam GMT+7: 'YYYY-MM-DD HH:MM:SS'.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

VN_TZ = timezone(timedelta(hours=7))


def to_mongo_datetime(val: Any, default_now: bool = True) -> Optional[datetime]:
    """
    Chuyển đổi giá trị đầu vào thành Python datetime timezone-aware theo UTC (+00:00).
    PyMongo sẽ ghi trực tiếp vào MongoDB dưới dạng BSON ISODate('...Z').
    Hỗ trợ: datetime (naive hoặc aware), int/float timestamp, ISO string, None.
    """
    if val is None:
        return datetime.now(timezone.utc) if default_now else None

    if isinstance(val, datetime):
        if val.tzinfo is None:
            # Naive datetime trong ứng dụng chứng khoán VN được hiểu là giờ địa phương VN
            return val.replace(tzinfo=VN_TZ).astimezone(timezone.utc)
        return val.astimezone(timezone.utc)

    if isinstance(val, (int, float)):
        if val <= 0:
            return datetime.now(timezone.utc) if default_now else None
        # Xử lý timestamp theo mili-giây (>= 100 tỉ)
        sec = val / 1000.0 if val >= 1e11 else float(val)
        try:
            return datetime.fromtimestamp(sec, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return datetime.now(timezone.utc) if default_now else None

    if isinstance(val, str):
        cleaned = val.strip()
        if not cleaned:
            return datetime.now(timezone.utc) if default_now else None

        # 1. Thử ISO 8601 (hỗ trợ Z, +07:00, +00:00, microseconds)
        iso_cand = cleaned.replace('Z', '+00:00')
        try:
            dt = datetime.fromisoformat(iso_cand)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=VN_TZ)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass

        # 2. Thử các định dạng ngày giờ thông dụng (mặc định hiểu là giờ địa phương VN)
        for fmt in ('%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S'):
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.replace(tzinfo=VN_TZ).astimezone(timezone.utc)
            except Exception:
                pass

        for fmt in ('%Y-%m-%d', '%Y/%m/%d'):
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.replace(tzinfo=VN_TZ).astimezone(timezone.utc)
            except Exception:
                pass

        # 3. Thử nếu là chuỗi số timestamp
        try:
            num = float(cleaned)
            sec = num / 1000.0 if num >= 1e11 else num
            return datetime.fromtimestamp(sec, tz=timezone.utc)
        except Exception:
            pass

    return datetime.now(timezone.utc) if default_now else None


def parse_db_datetime(val: Any, default_now: bool = False) -> Optional[datetime]:
    """
    Khôi phục đối tượng datetime khi đọc document từ MongoDB.
    MongoDB luôn lưu UTC, hàm này gắn timezone.utc và chuyển đổi sang VN_TZ (GMT+7)
    giúp toàn bộ logic bên trong app làm việc trực tiếp với giờ chuẩn Việt Nam.
    Tương thích ngược 100% với cả bản ghi cũ (integer timestamp) và bản ghi mới (ISODate).
    """
    if val is None:
        return datetime.now(VN_TZ) if default_now else None

    if isinstance(val, datetime):
        if val.tzinfo is None:
            # Document từ MongoDB trả về naive datetime tương ứng UTC
            val = val.replace(tzinfo=timezone.utc)
        return val.astimezone(VN_TZ)

    if isinstance(val, (int, float)):
        if val <= 0:
            return datetime.now(VN_TZ) if default_now else None
        sec = val / 1000.0 if val >= 1e11 else float(val)
        try:
            return datetime.fromtimestamp(sec, tz=timezone.utc).astimezone(VN_TZ)
        except (ValueError, OverflowError, OSError):
            return datetime.now(VN_TZ) if default_now else None

    dt_utc = to_mongo_datetime(val, default_now=default_now)
    if dt_utc:
        return dt_utc.astimezone(VN_TZ)
    return None


def to_timestamp_int(val: Any) -> int:
    """
    Chuyển đổi datetime, ISO string hoặc timestamp sang số nguyên giây UNIX timestamp.
    Dùng cho các trường API JSON trả về cho frontend/client để đảm bảo không bị vỡ giao diện.
    """
    if val is None:
        return 0

    if isinstance(val, (int, float)):
        if val <= 0:
            return 0
        return int(val / 1000.0) if val >= 1e11 else int(val)

    if isinstance(val, datetime):
        try:
            return int(val.timestamp())
        except (ValueError, OSError):
            return 0

    dt = parse_db_datetime(val, default_now=False)
    if dt:
        try:
            return int(dt.timestamp())
        except (ValueError, OSError):
            return 0

    return 0


def to_vn_datetime_str(val: Any) -> str:
    """
    Định dạng ngày giờ hiển thị theo chuẩn Việt Nam GMT+7: 'YYYY-MM-DD HH:MM:SS'.
    """
    if val is None:
        return ''

    if isinstance(val, datetime):
        dt = val
    else:
        dt = parse_db_datetime(val, default_now=False)

    if not dt:
        return ''

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=VN_TZ)
    else:
        dt = dt.astimezone(VN_TZ)

    return dt.strftime('%Y-%m-%d %H:%M:%S')


