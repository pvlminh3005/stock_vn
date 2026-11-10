"""
Stock RT - MongoDB Document Models & Conversion Mappers
Định nghĩa các Class Model có kiểu dữ liệu tường minh cho từng collection trên MongoDB.
Cung cấp to_doc() để chuyển sang Mongo BSON/Dict và from_doc() để khôi phục Object.
Cung cấp các Field Constants (F_*) và Query Helper Methods để chấm dứt việc truyền raw string/map.
"""

from dataclasses import dataclass, field, asdict
import re
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from bson import ObjectId
from backend.utils.datetime_helpers import (
    to_mongo_datetime,
    parse_db_datetime,
    to_timestamp_int,
    VN_TZ,
)


@dataclass
class PortfolioTrade:
    """Model Sổ lệnh Mua/Bán và Trạng thái vị thế cổ phiếu."""
    # Field Constants
    F_ID = '_id'
    F_ID_STR = 'id'
    F_SYMBOL = 'symbol'
    F_ORDER_TYPE = 'order_type'
    F_VOLUME = 'volume'
    F_PRICE = 'price'
    F_TRADE_DATE = 'trade_date'
    F_NOTE = 'note'
    F_STATUS = 'status'
    F_CREATED_AT = 'created_at'
    F_EXPIRE_AT = 'expire_at'

    # Order Type Constants
    ORDER_BUY = 'BUY'
    ORDER_SELL = 'SELL'

    # Status Constants
    STATUS_HOLDING = 'HOLDING'
    STATUS_CLOSED = 'CLOSED'

    # Index Constants
    INDEX_EXPIRE_AT = [(F_EXPIRE_AT, 1)]
    INDEX_SYMBOL = [(F_SYMBOL, 1)]
    INDEX_ORDER_TYPE = [(F_ORDER_TYPE, 1)]

    # Sort Constants
    SORT_TRADE_DATE_DESC = (F_TRADE_DATE, -1)

    symbol: str
    order_type: str = 'BUY'               # 'BUY' | 'SELL'
    volume: int = 0
    price: float = 0.0
    trade_date: str = ''
    note: str = ''
    status: str = 'HOLDING'               # 'HOLDING' | 'CLOSED'
    created_at: Optional[Any] = None
    expire_at: Optional[Any] = None
    id: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        """Convert sang Document dict để ghi trực tiếp vào MongoDB (ISODate)."""
        now_dt = datetime.now(VN_TZ)
        return {
            self.F_SYMBOL: self.symbol.strip().upper(),
            self.F_ORDER_TYPE: self.order_type.strip().upper(),
            self.F_VOLUME: int(self.volume),
            self.F_PRICE: float(self.price),
            self.F_TRADE_DATE: self.trade_date or now_dt.strftime('%Y-%m-%d'),
            self.F_NOTE: self.note.strip(),
            self.F_STATUS: self.status.strip().upper(),
            self.F_CREATED_AT: to_mongo_datetime(self.created_at),
            self.F_EXPIRE_AT: to_mongo_datetime(self.expire_at, default_now=False),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert sang Python Dict chuẩn để trả về cho API JSON client."""
        return {
            'id': self.id or '',
            'symbol': self.symbol,
            'order_type': self.order_type,
            'volume': self.volume,
            'price': self.price,
            'trade_date': self.trade_date,
            'note': self.note,
            'status': self.status,
            'created_at': to_timestamp_int(self.created_at),
        }

    def identity_filter(self) -> Dict[str, Any]:
        """Tạo filter query nhận diện bản ghi giao dịch (dùng cho deduplication/sync)."""
        return {
            self.F_SYMBOL: self.symbol.strip().upper(),
            self.F_ORDER_TYPE: self.order_type.strip().upper(),
            self.F_VOLUME: int(self.volume),
            self.F_PRICE: float(self.price),
            self.F_TRADE_DATE: self.trade_date,
        }

    @classmethod
    def normalize_price(cls, val: Any) -> float:
        """Chuẩn hóa giá về đơn vị Đồng (VNĐ). Nếu người dùng nhập 27.5 thì tự nhân 1000 thành 27500."""
        try:
            p = float(val)
            if p <= 0:
                return 0.0
            if 0 < p < 1000:
                return round(p * 1000, 2)
            return round(p, 2)
        except (ValueError, TypeError):
            return 0.0

    @classmethod
    def from_request(cls, data: Dict[str, Any]) -> Tuple[Optional['PortfolioTrade'], Optional[str]]:
        """Validate và parse payload từ HTTP API Request sang PortfolioTrade model."""
        if data is None or not isinstance(data, dict):
            return None, 'Payload không hợp lệ'

        sym = str(data.get(cls.F_SYMBOL, '')).strip().upper()
        if not sym:
            return None, 'Vui lòng nhập mã chứng khoán'
        if len(sym) > 10:
            return None, 'Mã chứng khoán không hợp lệ (tối đa 10 ký tự)'

        try:
            vol = int(data.get(cls.F_VOLUME, 0))
            if vol <= 0:
                return None, 'Khối lượng phải lớn hơn 0'
        except (ValueError, TypeError):
            return None, 'Khối lượng không hợp lệ'

        price = cls.normalize_price(data.get(cls.F_PRICE, 0))
        if price <= 0:
            return None, 'Giá mua/bán phải lớn hơn 0'

        order_type = str(data.get(cls.F_ORDER_TYPE, cls.ORDER_BUY)).strip().upper()
        if order_type not in (cls.ORDER_BUY, cls.ORDER_SELL):
            order_type = cls.ORDER_BUY

        trade_date = str(data.get(cls.F_TRADE_DATE, '')).strip()
        if not trade_date:
            trade_date = datetime.now(VN_TZ).strftime('%Y-%m-%d')

        note = str(data.get(cls.F_NOTE, '')).strip()
        status = cls.STATUS_HOLDING if order_type == cls.ORDER_BUY else cls.STATUS_CLOSED

        trade = cls(
            symbol=sym,
            order_type=order_type,
            volume=vol,
            price=price,
            trade_date=trade_date,
            note=note,
            status=status,
            created_at=datetime.now(VN_TZ),
        )
        return trade, None

    @classmethod
    def filter_by_id(cls, trade_id: str) -> Dict[str, Any]:
        """Tạo filter query theo ID (hỗ trợ cả ObjectId và string id)."""
        try:
            return {cls.F_ID: ObjectId(trade_id)}
        except Exception:
            return {cls.F_ID_STR: str(trade_id)}

    @classmethod
    def filter_by_id_str(cls, trade_id: str) -> Dict[str, Any]:
        """Tạo filter query theo string id."""
        return {cls.F_ID_STR: str(trade_id)}

    @classmethod
    def filter_by_symbol(cls, symbol: str) -> Dict[str, Any]:
        return {cls.F_SYMBOL: symbol.strip().upper()}

    @classmethod
    def filter_by_order_type(cls, order_type: str = 'BUY') -> Dict[str, Any]:
        return {cls.F_ORDER_TYPE: order_type.strip().upper()}

    @classmethod
    def filter_active_holdings(cls) -> Dict[str, Any]:
        """Filter các giao dịch đang có lệnh MUA."""
        return {cls.F_ORDER_TYPE: cls.ORDER_BUY}

    @classmethod
    def filter_by_symbol_and_type(cls, symbol: str, order_type: str = 'BUY') -> Dict[str, Any]:
        return {
            cls.F_SYMBOL: symbol.strip().upper(),
            cls.F_ORDER_TYPE: order_type.strip().upper()
        }

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> 'PortfolioTrade':
        """Khôi phục instance từ MongoDB document hoặc dict đầu vào."""
        if not doc:
            return cls(symbol='')

        trade_id = str(doc.get('_id', doc.get('id', '')))
        created = parse_db_datetime(doc.get('created_at'), default_now=True)
        expire = parse_db_datetime(doc.get('expire_at'), default_now=False)

        return cls(
            id=trade_id,
            symbol=str(doc.get('symbol', '')).strip().upper(),
            order_type=str(doc.get('order_type', 'BUY')).strip().upper(),
            volume=int(doc.get('volume', 0)),
            price=float(doc.get('price', 0.0)),
            trade_date=str(doc.get('trade_date', '')).strip(),
            note=str(doc.get('note', '')).strip(),
            status=str(doc.get('status', 'HOLDING')).strip().upper(),
            created_at=created,
            expire_at=expire,
        )


@dataclass
class PortfolioSetting:
    """Model Cấu hình Danh mục (Tổng NAV, quản trị rủi ro)."""
    F_KEY = 'key'
    F_VALUE = 'value'
    F_UPDATED_AT = 'updated_at'

    KEY_TOTAL_NAV = 'total_nav'
    INDEX_KEY = [(F_KEY, 1)]

    key: str
    value: str
    updated_at: Optional[Any] = None

    def to_doc(self) -> Dict[str, Any]:
        return {
            self.F_KEY: self.key.strip(),
            self.F_VALUE: str(self.value).strip(),
            self.F_UPDATED_AT: to_mongo_datetime(self.updated_at),
        }

    @classmethod
    def from_request(cls, data: Dict[str, Any]) -> Tuple[Optional['PortfolioSetting'], Optional[str]]:
        """Validate và parse payload cấu hình từ request sang PortfolioSetting."""
        if not data or not isinstance(data, dict):
            return None, 'Payload không hợp lệ'

        if 'total_nav' in data:
            try:
                nav = float(data['total_nav'])
                if nav < 0:
                    return None, 'Tổng NAV không được âm'
                return cls(key=cls.KEY_TOTAL_NAV, value=str(nav)), None
            except (ValueError, TypeError):
                return None, 'Giá trị Tổng NAV không hợp lệ'

        key = str(data.get(cls.F_KEY, '')).strip()
        if not key:
            return None, 'Thiếu tham số cấu hình'
        val = str(data.get(cls.F_VALUE, '')).strip()
        return cls(key=key, value=val), None

    @classmethod
    def filter_by_key(cls, key: str = KEY_TOTAL_NAV) -> Dict[str, Any]:
        return {cls.F_KEY: key.strip()}

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> 'PortfolioSetting':
        if not doc:
            return cls(key='', value='')
        return cls(
            key=str(doc.get('key', '')).strip(),
            value=str(doc.get('value', '')).strip(),
            updated_at=parse_db_datetime(doc.get('updated_at')),
        )


@dataclass
class AlertState:
    """Model Trạng thái Cảnh báo kỹ thuật của từng mã (chống spam bot Telegram)."""
    F_SYMBOL = 'symbol'
    F_LAST_ALERT_TYPE = 'last_alert_type'
    F_LAST_ALERT_TIME = 'last_alert_time'
    F_FLIP_COUNT_TODAY = 'flip_count_today'
    F_LAST_RIBBON_COLOR = 'last_ribbon_color'
    F_PENDING_SUMMARY = 'pending_summary'
    F_UPDATED_AT = 'updated_at'

    INDEX_SYMBOL = [(F_SYMBOL, 1)]

    symbol: str
    last_alert_type: str = ''
    last_alert_time: int = 0
    flip_count_today: int = 0
    last_ribbon_color: str = ''
    pending_summary: str = ''
    updated_at: Optional[Any] = None

    def to_doc(self) -> Dict[str, Any]:
        return {
            self.F_SYMBOL: self.symbol.strip().upper(),
            self.F_LAST_ALERT_TYPE: self.last_alert_type,
            self.F_LAST_ALERT_TIME: int(self.last_alert_time),
            self.F_FLIP_COUNT_TODAY: int(self.flip_count_today),
            self.F_LAST_RIBBON_COLOR: self.last_ribbon_color,
            self.F_PENDING_SUMMARY: self.pending_summary,
            self.F_UPDATED_AT: to_mongo_datetime(self.updated_at),
        }

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res['updated_at'] = to_timestamp_int(self.updated_at)
        return res

    @classmethod
    def filter_by_symbol(cls, symbol: str) -> Dict[str, Any]:
        return {cls.F_SYMBOL: symbol.strip().upper()}

    @classmethod
    def from_doc(cls, doc: Dict[str, Any], symbol: str = '') -> 'AlertState':
        if not doc:
            return cls(symbol=symbol.strip().upper())
        return cls(
            symbol=str(doc.get('symbol', symbol)).strip().upper(),
            last_alert_type=str(doc.get('last_alert_type', '')),
            last_alert_time=int(doc.get('last_alert_time', 0)),
            flip_count_today=int(doc.get('flip_count_today', 0)),
            last_ribbon_color=str(doc.get('last_ribbon_color', '')),
            pending_summary=str(doc.get('pending_summary', '')),
            updated_at=parse_db_datetime(doc.get('updated_at')),
        )


@dataclass
class TelegramAlertLog:
    """Model Khóa Chống Trùng Cảnh Báo Telegram."""
    F_KEY = 'key'
    F_SENT_AT = 'sent_at'
    F_PREVIEW = 'preview'

    INDEX_KEY = [(F_KEY, 1)]
    INDEX_SENT_AT = [(F_SENT_AT, 1)]

    key: str
    sent_at: Optional[Any] = None
    preview: str = ''

    def to_doc(self) -> Dict[str, Any]:
        return {
            self.F_KEY: self.key,
            self.F_SENT_AT: to_mongo_datetime(self.sent_at),
            self.F_PREVIEW: self.preview[:100],
        }

    @classmethod
    def filter_by_key(cls, key: str) -> Dict[str, Any]:
        return {cls.F_KEY: key}

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> 'TelegramAlertLog':
        if not doc:
            return cls(key='')
        return cls(
            key=doc.get(cls.F_KEY, ''),
            sent_at=parse_db_datetime(doc.get(cls.F_SENT_AT)),
            preview=doc.get(cls.F_PREVIEW, ''),
        )


@dataclass
class TelegramSentLog:
    """Model Lịch sử Tin nhắn Cảnh báo Telegram đã phát đi."""
    F_ID = '_id'
    F_ALERT_TYPE = 'alert_type'
    F_SENT_AT = 'sent_at'
    F_EXPIRE_AT = 'expire_at'

    INDEX_SENT_AT_DESC = [(F_SENT_AT, -1)]
    INDEX_SENT_AT_ASC = [(F_SENT_AT, 1)]
    SORT_SENT_AT_DESC = (F_SENT_AT, -1)

    alert_type: str = ''
    title: str = ''
    sent_at: Optional[Any] = None
    sent_time_vn: str = ''
    market_regime: str = ''
    vnindex: str = ''
    stocks: List[Dict[str, Any]] = field(default_factory=list)
    message_id: Optional[Any] = None
    status: str = 'SENT'
    expire_at: Optional[Any] = None
    id: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        return {
            self.F_ALERT_TYPE: str(self.alert_type).upper(),
            'title': self.title,
            self.F_SENT_AT: to_mongo_datetime(self.sent_at),
            'sent_time_vn': self.sent_time_vn,
            'market_regime': self.market_regime,
            'vnindex': self.vnindex,
            'stocks': self.stocks,
            'message_id': self.message_id,
            'status': self.status,
            self.F_EXPIRE_AT: to_mongo_datetime(self.expire_at, default_now=False),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id or '',
            'alert_type': self.alert_type,
            'title': self.title,
            'sent_at': to_timestamp_int(self.sent_at),
            'sent_time_vn': self.sent_time_vn,
            'market_regime': self.market_regime,
            'vnindex': self.vnindex,
            'stocks': self.stocks,
            'message_id': self.message_id,
            'status': self.status,
        }

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> 'TelegramSentLog':
        if not doc:
            return cls()
        return cls(
            id=str(doc.get('_id', doc.get('id', ''))),
            alert_type=str(doc.get('alert_type', '')),
            title=str(doc.get('title', '')),
            sent_at=parse_db_datetime(doc.get('sent_at')),
            sent_time_vn=str(doc.get('sent_time_vn', '')),
            market_regime=str(doc.get('market_regime', '')),
            vnindex=str(doc.get('vnindex', '')),
            stocks=doc.get('stocks', []),
            message_id=doc.get('message_id'),
            status=str(doc.get('status', 'SENT')),
            expire_at=parse_db_datetime(doc.get('expire_at'), default_now=False),
        )


@dataclass
class CompanyItem:
    """Model Thông tin Doanh nghiệp Niêm yết (HOSE, HNX, UPCoM)."""
    F_TICKER = 'ticker'
    F_NAME = 'name'
    F_NAME_VI = 'nameVi'
    F_NAME_EN = 'nameEn'
    F_NAME_UNACCENT = 'nameUnaccent'
    F_EXCHANGE = 'exchange'
    F_STOCK_EXCHANGE = 'stockExchange'
    F_SECTOR = 'sector'
    F_INDUSTRY = 'industry'
    F_IMAGE_URL = 'imageUrl'
    F_BC_ECONOMIC_SECTOR_ID = 'bcEconomicSectorId'
    F_UPDATED_AT = 'updated_at'

    # Indexes
    INDEX_TICKER = [(F_TICKER, 1)]
    INDEX_NAME_VI = [(F_NAME_VI, 1)]
    INDEX_NAME_UNACCENT = [(F_NAME_UNACCENT, 1)]
    INDEX_SECTOR = [(F_SECTOR, 1)]

    # Projections
    PROJECTION_NO_ID = {'_id': 0}

    ticker: str
    name: str = ''
    name_vi: str = ''
    name_en: str = ''
    name_unaccent: str = ''
    exchange: str = ''
    sector: str = 'Thị trường chung'
    industry: str = ''
    image_url: str = ''
    bc_economic_sector_id: Optional[Any] = None
    updated_at: Optional[Any] = None

    def to_doc(self) -> Dict[str, Any]:
        return {
            self.F_TICKER: self.ticker.strip().upper(),
            self.F_NAME: self.name.strip(),
            self.F_NAME_VI: self.name_vi or self.name,
            self.F_NAME_EN: self.name_en,
            self.F_NAME_UNACCENT: self.name_unaccent.strip().lower(),
            self.F_STOCK_EXCHANGE: self.exchange.strip().upper(),
            self.F_EXCHANGE: self.exchange.strip().upper(),
            self.F_SECTOR: self.sector,
            self.F_INDUSTRY: self.industry,
            self.F_IMAGE_URL: self.image_url,
            self.F_BC_ECONOMIC_SECTOR_ID: self.bc_economic_sector_id,
            self.F_UPDATED_AT: to_mongo_datetime(self.updated_at),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            'ticker': self.ticker,
            'name': self.name,
            'nameVi': self.name_vi or self.name,
            'nameEn': self.name_en,
            'nameUnaccent': self.name_unaccent,
            'exchange': self.exchange,
            'stockExchange': self.exchange,
            'sector': self.sector,
            'industry': self.industry,
            'imageUrl': self.image_url,
            'updated_at': to_timestamp_int(self.updated_at),
        }

    @classmethod
    def filter_by_ticker(cls, ticker: str) -> Dict[str, Any]:
        return {cls.F_TICKER: ticker.strip().upper()}

    @classmethod
    def filter_by_ticker_prefix(cls, prefix: str, exclude_tickers: Optional[List[str]] = None) -> Dict[str, Any]:
        flt: Dict[str, Any] = {cls.F_TICKER: {'$regex': f'^{prefix.strip().upper()}', '$options': 'i'}}
        if exclude_tickers:
            flt[cls.F_TICKER]['$nin'] = exclude_tickers
        return flt

    @classmethod
    def filter_search_text(cls, raw_q: str, q_unaccent: str, exclude_tickers: Optional[List[str]] = None) -> Dict[str, Any]:
        flt: Dict[str, Any] = {
            '$or': [
                {cls.F_NAME_VI: {'$regex': re.escape(raw_q), '$options': 'i'}},
                {cls.F_NAME_UNACCENT: {'$regex': re.escape(q_unaccent), '$options': 'i'}},
                {cls.F_SECTOR: {'$regex': re.escape(raw_q), '$options': 'i'}},
            ]
        }
        if exclude_tickers:
            flt[cls.F_TICKER] = {'$nin': exclude_tickers}
        return flt

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> 'CompanyItem':
        if not doc:
            return cls(ticker='', name='')
        return cls(
            ticker=str(doc.get('ticker', '')).strip().upper(),
            name=str(doc.get('name', '')).strip(),
            name_vi=str(doc.get('nameVi', doc.get('name', ''))).strip(),
            name_en=str(doc.get('nameEn', '')).strip(),
            name_unaccent=str(doc.get('nameUnaccent', doc.get('name_unaccent', ''))).strip().lower(),
            exchange=str(doc.get('stockExchange', doc.get('exchange', ''))).strip().upper(),
            sector=str(doc.get('sector', 'Thị trường chung')),
            industry=str(doc.get('industry', '')),
            image_url=str(doc.get('imageUrl', '')),
            bc_economic_sector_id=doc.get('bcEconomicSectorId'),
            updated_at=parse_db_datetime(doc.get('updated_at')),
        )


@dataclass
class MarketBoardSnapshot:
    """Model Snapshot Bảng giá Realtime toàn thị trường."""
    F_KEY = 'key'
    F_DATA = 'data'
    F_TOTAL_STOCKS = 'total_stocks'
    F_UPDATED_AT = 'updated_at'

    KEY_LATEST_BOARD = 'latest_board'
    INDEX_KEY = [(F_KEY, 1)]

    key: str = 'latest_board'
    data: Dict[str, Any] = field(default_factory=dict)
    updated_at: Optional[Any] = None

    def to_doc(self) -> Dict[str, Any]:
        return {
            self.F_KEY: self.key,
            self.F_DATA: self.data,
            self.F_TOTAL_STOCKS: len(self.data),
            self.F_UPDATED_AT: to_mongo_datetime(self.updated_at),
        }

    @classmethod
    def filter_by_key(cls, key: str = 'latest_board') -> Dict[str, Any]:
        return {cls.F_KEY: key}

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> 'MarketBoardSnapshot':
        if not doc:
            return cls()
        return cls(
            key=doc.get('key', cls.KEY_LATEST_BOARD),
            data=doc.get('data', {}),
            updated_at=parse_db_datetime(doc.get('updated_at')),
        )


@dataclass
class ScreenerSnapshot:
    """Model Snapshot Kết quả bộ lọc quét Top cơ hội T+."""
    F_KEY = 'key'
    F_DATA = 'data'
    F_UPDATED_AT = 'updated_at'

    KEY_TOP_TPLUS = 'top_tplus'
    INDEX_KEY = [(F_KEY, 1)]

    key: str = 'top_tplus'
    data: Dict[str, Any] = field(default_factory=dict)
    updated_at: Optional[Any] = None

    def to_doc(self) -> Dict[str, Any]:
        return {
            self.F_KEY: self.key,
            self.F_DATA: self.data,
            self.F_UPDATED_AT: to_mongo_datetime(self.updated_at),
        }

    @classmethod
    def filter_by_key(cls, key: str = 'top_tplus') -> Dict[str, Any]:
        return {cls.F_KEY: key}

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> 'ScreenerSnapshot':
        if not doc:
            return cls()
        return cls(
            key=doc.get('key', cls.KEY_TOP_TPLUS),
            data=doc.get('data', {}),
            updated_at=parse_db_datetime(doc.get('updated_at')),
        )


@dataclass
class FundamentalItem:
    """Model Dữ liệu Phân tích Cơ bản và Định giá doanh nghiệp."""
    F_SYMBOL = 'symbol'
    F_UPDATED_AT = 'updated_at'

    INDEX_SYMBOL = [(F_SYMBOL, 1)]

    symbol: str
    data: Dict[str, Any] = field(default_factory=dict)
    updated_at: Optional[Any] = None

    def to_doc(self) -> Dict[str, Any]:
        doc = dict(self.data)
        doc[self.F_SYMBOL] = self.symbol.upper()
        doc[self.F_UPDATED_AT] = to_mongo_datetime(self.updated_at)
        return doc

    @classmethod
    def filter_by_symbol(cls, symbol: str) -> Dict[str, Any]:
        return {cls.F_SYMBOL: symbol.strip().upper()}

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> 'FundamentalItem':
        if not doc:
            return cls(symbol='')
        sym = doc.get(cls.F_SYMBOL, '')
        up = parse_db_datetime(doc.get(cls.F_UPDATED_AT))
        cleaned = dict(doc)
        cleaned.pop('_id', None)
        return cls(symbol=sym, data=cleaned, updated_at=up)


@dataclass
class VciHistoryItem:
    """Model Dữ liệu Lịch sử Phân tích Kỹ thuật & Dòng tiền VCI."""
    F_SYMBOL = 'symbol'
    F_PAYLOAD = 'payload'
    F_LATEST_PERIOD = 'latest_period'
    F_UPDATED_AT = 'updated_at'

    INDEX_SYMBOL = [(F_SYMBOL, 1)]

    symbol: str
    payload: Dict[str, Any] = field(default_factory=dict)
    latest_period: str = ''
    updated_at: Optional[Any] = None

    def to_doc(self) -> Dict[str, Any]:
        return {
            self.F_SYMBOL: self.symbol.strip().upper(),
            self.F_PAYLOAD: self.payload,
            self.F_LATEST_PERIOD: self.latest_period,
            self.F_UPDATED_AT: to_mongo_datetime(self.updated_at),
        }

    @classmethod
    def filter_by_symbol(cls, symbol: str) -> Dict[str, Any]:
        return {cls.F_SYMBOL: symbol.strip().upper()}

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> 'VciHistoryItem':
        if not doc:
            return cls(symbol='')
        return cls(
            symbol=doc.get(cls.F_SYMBOL, ''),
            payload=doc.get(cls.F_PAYLOAD, {}),
            latest_period=doc.get(cls.F_LATEST_PERIOD, ''),
            updated_at=parse_db_datetime(doc.get(cls.F_UPDATED_AT)),
        )
