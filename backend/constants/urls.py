"""
Stock RT - Centralized External & Internal API Base URLs
Tập trung toàn bộ Root/Base URLs cho các dịch vụ bên ngoài và nội bộ.
Các function chỉ cần truyền sub-url hoặc parameters.
"""

import os
from urllib.parse import urlencode
from typing import Optional, Dict, Any

# 1. ENTRADE SERVICES (Bảng giá realtime, Nến chứng khoán & Chỉ số)
ENTRADE_BASE_URL = os.environ.get('ENTRADE_BASE_URL', 'https://services.entrade.com.vn').rstrip('/')
ENTRADE_CHART_API_BASE = f"{ENTRADE_BASE_URL}/chart-api/v2/ohlcs"


def build_entrade_chart_url(sub_path: str, params: Optional[Dict[str, Any]] = None) -> str:
    """
    Tạo URL Entrade OHLC từ sub-path.
    Ví dụ sub_path='stock' -> 'https://services.entrade.com.vn/chart-api/v2/ohlcs/stock?...'
    hoặc sub_path='index' -> 'https://services.entrade.com.vn/chart-api/v2/ohlcs/index?...'
    """
    clean_sub = sub_path.strip().lstrip('/')
    url = f"{ENTRADE_CHART_API_BASE}/{clean_sub}"
    if params:
        query_str = urlencode({k: v for k, v in params.items() if v is not None})
        if query_str:
            url = f"{url}?{query_str}"
    return url


# 2. TELEGRAM BOT API
TELEGRAM_API_BASE = os.environ.get('TELEGRAM_API_BASE', 'https://api.telegram.org').rstrip('/')


def build_telegram_url(bot_token: str, method: str = 'sendMessage') -> str:
    """Tạo URL gọi Telegram Bot API từ method sub-path."""
    clean_method = method.strip().lstrip('/')
    return f"{TELEGRAM_API_BASE}/bot{bot_token}/{clean_method}"


# 3. TIN TỨC & BÁO CHÍ TÀI CHÍNH
CAFEF_BASE_URL = 'https://cafef.vn'
CAFEF_S_BASE_URL = 'https://s.cafef.vn'
VNEXPRESS_BASE_URL = 'https://vnexpress.net'
BAOCHINHPHU_BASE_URL = 'https://baochinhphu.vn'
VIETSTOCK_FINANCE_BASE_URL = 'https://finance.vietstock.vn'


def build_cafef_search_url(ticker: str) -> str:
    """Tạo URL tìm kiếm tin tức CafeF theo mã."""
    return f"{CAFEF_BASE_URL}/tim-kiem.chn?keywords={ticker.strip().upper()}"


def build_cafef_events_url(ticker: str) -> str:
    """Tạo URL sự kiện doanh nghiệp trên CafeF."""
    return f"{CAFEF_S_BASE_URL}/tin-doanh-nghiep/{ticker.strip().upper()}/event.chn"


def build_vietstock_finance_url(ticker: str) -> str:
    """Tạo URL hồ sơ tài chính Vietstock theo mã."""
    return f"{VIETSTOCK_FINANCE_BASE_URL}/{ticker.strip().upper()}/tai-chinh.htm"


# 4. VIETCAP OPEN API & VIETCAP IQ (Rổ chỉ số & Báo cáo tài chính VCI)
VIETCAP_TRADING_BASE_URL = os.environ.get('VIETCAP_TRADING_BASE_URL', 'https://trading.vietcap.com.vn').rstrip('/')
VIETCAP_IQ_BASE_URL = os.environ.get('VIETCAP_IQ_BASE_URL', 'https://iq.vietcap.com.vn').rstrip('/')
VNDIRECT_FINFO_BASE_URL = os.environ.get('VNDIRECT_FINFO_BASE_URL', 'https://api-finfo.vndirect.com.vn').rstrip('/')


def build_vietcap_group_url(group: str) -> str:
    """Tạo URL lấy danh sách mã theo rổ chỉ số từ Vietcap Open API (VD: VN100, HNX30)."""
    return f"{VIETCAP_TRADING_BASE_URL}/api/price/symbols/getByGroup?group={group.strip().upper()}"


def build_vietcap_company_url(symbol: str) -> str:
    """Tạo URL lấy hồ sơ tổng quan doanh nghiệp từ Vietcap IQ."""
    return f"{VIETCAP_IQ_BASE_URL}/api/iq-insight-service/v1/company/{symbol.strip().upper()}"


def build_vietcap_statistics_url(symbol: str) -> str:
    """Tạo URL lấy lịch sử chỉ số tài chính theo quý từ Vietcap IQ."""
    return f"{VIETCAP_IQ_BASE_URL}/api/iq-insight-service/v1/company/{symbol.strip().upper()}/statistics-financial"


def build_vietcap_financial_statement_url(symbol: str, section: str) -> str:
    """Tạo URL lấy BCTC theo section (BALANCE_SHEET, CASH_FLOW, INCOME_STATEMENT) từ Vietcap IQ."""
    return (
        f"{VIETCAP_IQ_BASE_URL}/api/iq-insight-service/v1/company/"
        f"{symbol.strip().upper()}/financial-statement?section={section.strip().upper()}"
    )


def build_vndirect_events_url(ticker: str, size: int = 5) -> str:
    """Tạo URL lấy lịch sự kiện & cổ tức doanh nghiệp tiếng Việt từ VNDirect Finfo API."""
    return (
        f"{VNDIRECT_FINFO_BASE_URL}/v4/events?"
        f"{urlencode({'q': f'code:{ticker.strip().upper()}~locale:VN', 'sort': 'disclosureDate:desc', 'size': size})}"
    )

