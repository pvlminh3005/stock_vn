"""
Stock RT - Centralized Environment & Profile Loader
Hỗ trợ quản lý đa môi trường (development, production, testing).
Tự động tách biệt database MongoDB giữa các profile để bảo vệ an toàn cho Production.
"""

import os
import sys
import logging

logger = logging.getLogger('env_loader')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_LOADED = False
_CURRENT_ENV = 'development'
_LOADED_FILE = None


def _normalize_env_name(raw_name: str) -> str:
    """Chuẩn hóa tên môi trường về 3 chuẩn: development, production, testing."""
    name = (raw_name or '').strip().lower()
    if name in ('prod', 'production'):
        return 'production'
    if name in ('test', 'testing'):
        return 'testing'
    return 'development'


def _detect_requested_env() -> str:
    """
    Xác định môi trường từ:
    1. Tham số dòng lệnh: --env <env> hoặc --profile <env>
    2. Biến môi trường hệ thống: APP_ENV hoặc ENV_PROFILE
    3. Mặc định là 'development' khi chạy local.
    """
    for i, arg in enumerate(sys.argv):
        if arg in ('--env', '--profile') and i + 1 < len(sys.argv):
            return _normalize_env_name(sys.argv[i + 1])
        if arg.startswith('--env='):
            return _normalize_env_name(arg.split('=', 1)[1])
        if arg.startswith('--profile='):
            return _normalize_env_name(arg.split('=', 1)[1])

    env_var = os.environ.get('APP_ENV') or os.environ.get('ENV_PROFILE')
    if env_var:
        return _normalize_env_name(env_var)

    return 'development'


def _parse_env_file(filepath: str, overwrite: bool = False) -> set:
    """Đọc file .env dạng KEY=VALUE và nạp vào os.environ."""
    keys = set()
    if not os.path.isfile(filepath):
        return keys

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k:
                        if overwrite or k not in os.environ:
                            os.environ[k] = v
                        keys.add(k)
    except Exception as e:
        logger.warning("Không thể đọc file env %s: %s", filepath, e)
    return keys


def load_environment(force_reload: bool = False) -> str:
    """
    Nạp cấu hình môi trường chuẩn từ thư mục envs/:
    - development: nạp envs/.env.development (Cụm Cluster Dev)
    - production : nạp envs/.env.production (Cụm Cluster Prod)
    - testing    : nạp envs/.env.test (Cụm Cluster Dev)
    Phân tách môi trường dựa trên MONGODB_URI riêng biệt của từng cụm cluster.
    Tên database được thống nhất dùng stock_pro_db (hoặc lấy theo URI/MONGODB_DB_NAME).
    """
    global _LOADED, _CURRENT_ENV, _LOADED_FILE

    if _LOADED and not force_reload:
        return _CURRENT_ENV

    target_env = _detect_requested_env()
    os.environ['APP_ENV'] = target_env
    _CURRENT_ENV = target_env

    # 1. Chỉ định chính xác file env theo profile (chỉ dùng trong thư mục envs/)
    if target_env == 'production':
        target_rel_path = 'envs/.env.production'
    elif target_env == 'testing':
        target_rel_path = 'envs/.env.test'
    else:
        target_rel_path = 'envs/.env.development'

    full_path = os.path.join(BASE_DIR, target_rel_path)
    loaded_keys = set()
    if os.path.isfile(full_path):
        loaded_keys = _parse_env_file(full_path, overwrite=True)
        _LOADED_FILE = target_rel_path
    else:
        logger.warning("⚠️ Không tìm thấy file cấu hình môi trường: %s", target_rel_path)
        _LOADED_FILE = None

    # 2. Tự động xác định MONGODB_DB_NAME (mặc định thống nhất: stock_pro_db)
    current_db = os.environ.get('MONGODB_DB_NAME', '').strip().strip("'\"")
    if not current_db:
        # Thử lấy từ path của MONGODB_URI nếu có
        uri = os.environ.get('MONGODB_URI', '').strip()
        parsed_name = ''
        if '/' in uri:
            path_part = uri.rsplit('/', 1)[-1].split('?')[0].strip()
            if path_part and not path_part.startswith('?'):
                parsed_name = path_part
        from backend.constants.db import DEFAULT_DB_NAME
        os.environ['MONGODB_DB_NAME'] = parsed_name or DEFAULT_DB_NAME

    _LOADED = True
    return _CURRENT_ENV


def get_app_env() -> str:
    """Trả về môi trường hiện tại (development / production / testing)."""
    if not _LOADED:
        load_environment()
    return _CURRENT_ENV


def is_production() -> bool:
    return get_app_env() == 'production'


def is_development() -> bool:
    return get_app_env() == 'development'


def is_testing() -> bool:
    return get_app_env() == 'testing'


def get_mongodb_config() -> tuple:
    """Lấy tuple (MONGODB_URI, MONGODB_DB_NAME) theo profile hiện tại."""
    if not _LOADED:
        load_environment()

    uri = os.environ.get('MONGODB_URI', '').strip().strip("'\"")
    db_name = os.environ.get('MONGODB_DB_NAME', '').strip().strip("'\"")
    return uri, db_name


# Tự động nạp khi import
load_environment()

