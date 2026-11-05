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

