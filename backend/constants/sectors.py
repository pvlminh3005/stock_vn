"""
Stock RT - Phân loại ngành nghề (Sectors Classification)
Chuẩn hóa tên ngành và định nghĩa các nhóm ngành đặc thù (Tài chính, Chu kỳ, P/B).
"""

SECTOR_MAP = {
    'Technology': 'Công nghệ thông tin',
    'Construction & Materials': 'Xây dựng & Vật liệu',
    'Financial Services': 'Dịch vụ Tài chính / Chứng khoán',
    'Banks': 'Ngân hàng',
    'Real Estate': 'Bất động sản',
    'Food & Beverage': 'Thực phẩm & Đồ uống',
    'Retail': 'Bán lẻ tiêu dùng',
    'Basic Resources': 'Thép & Tài nguyên cơ bản',
    'Oil & Gas': 'Dầu khí & Năng lượng',
    'Utilities': 'Điện & Tiện ích',
    'Industrial Goods & Services': 'Hàng hóa & Dịch vụ công nghiệp',
    'Chemicals': 'Hóa chất & Phân bón',
    'Automobiles & Parts': 'Ô tô & Phụ tùng',
    'Personal & Household Goods': 'Hàng tiêu dùng cá nhân & Gia dụng',
    'Health Care': 'Y tế & Dược phẩm',
    'Telecommunications': 'Viễn thông',
    'Travel & Leisure': 'Du lịch & Giải trí',
    'Media': 'Truyền thông',
    'Insurance': 'Bảo hiểm',
}

# Ngành tài chính: D/E cao, OCF và biên lãi gộp không mang ý nghĩa như doanh nghiệp sản xuất
FINANCIAL_SECTORS = {
    'Ngân hàng',
    'Chứng khoán',
    'Dịch vụ Tài chính / Chứng khoán',
    'Bảo hiểm',
}

# Ngành chu kỳ: EPS đỉnh/đáy chu kỳ làm P/E sai lệch -> định giá theo P/B, không nâng P/B khi ROE ở đỉnh chu kỳ
CYCLICAL_SECTORS = {
    'Thép & Tài nguyên cơ bản',
    'Hóa chất & Phân bón',
    'Dầu khí & Năng lượng',
}

# Ngành định giá chính theo P/B
PB_PRIMARY_SECTORS = FINANCIAL_SECTORS | CYCLICAL_SECTORS | {'Bất động sản'}

# Tứ trụ dòng tiền thanh khoản cao nhất TTCK Việt Nam (Bank - Chứng - Thép - BĐS)
CORE_PILLAR_SECTORS = {
    'Ngân hàng',
    'Chứng khoán',
    'Thép & VLXD',
    'Bất động sản',
    'BĐS Khu công nghiệp',
}


class DynamicStockSectors(dict):
    """
    Bảng tra cứu nhóm ngành động tự nạp từ MongoDB Atlas collection 'companies' / 'company_directory'
    hoặc RAM cache (1,626 mã niêm yết trên HOSE, HNX, UPCoM).
    Loại bỏ hoàn toàn việc gán cứng (hardcode) danh mục mã cổ phiếu cố định.
    Hỗ trợ đầy đủ các thao tác: KNOWN_STOCK_SECTORS[sym], .get(), in, .keys(), .items(), len().
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loaded = False
        self._loading = False

    def _ensure_loaded(self):
        """Lazy-load nạp 1,626 mã từ MongoDB/Cache khi được truy cập lần đầu."""
        if self._loaded or self._loading:
            return
        self._loading = True
        try:
            from backend.data_providers.company_directory_provider import get_all_stock_sectors_map
            mapping = get_all_stock_sectors_map()
            if mapping:
                self.clear()
                self.update(mapping)
                self._loaded = True
        except Exception:
            pass
        finally:
            self._loading = False

    def __getitem__(self, key):
        self._ensure_loaded()
        k = str(key).strip().upper()
        if k in self:
            return super().__getitem__(k)
        try:
            from backend.data_providers.company_directory_provider import get_dynamic_sector
            return get_dynamic_sector(k)
        except Exception:
            return 'Thị trường chung'

    def get(self, key, default=None):
        self._ensure_loaded()
        k = str(key).strip().upper()
        if k in self:
            return super().get(k)
        try:
            from backend.data_providers.company_directory_provider import get_dynamic_sector
            sec = get_dynamic_sector(k)
            if sec and sec != 'Thị trường chung':
                return sec
        except Exception:
            pass
        return default if default is not None else 'Thị trường chung'

    def __contains__(self, key):
        self._ensure_loaded()
        k = str(key).strip().upper()
        if super().__contains__(k):
            return True
        try:
            from backend.data_providers.company_directory_provider import is_valid_ticker
            return is_valid_ticker(k)
        except Exception:
            return False

    def keys(self):
        self._ensure_loaded()
        return super().keys()

    def items(self):
        self._ensure_loaded()
        return super().items()

    def values(self):
        self._ensure_loaded()
        return super().values()

    def __iter__(self):
        self._ensure_loaded()
        return super().__iter__()

    def __len__(self):
        self._ensure_loaded()
        return super().__len__()


# Bảng tra cứu nhóm ngành động toàn diện (Dynamic Dictionary từ MongoDB 1,626 mã)
KNOWN_STOCK_SECTORS = DynamicStockSectors()


# Nhóm ngành phân loại vai trò
CORE_SECTORS = {'Ngân hàng', 'Thép & VLXD', 'Bán lẻ tiêu dùng', 'Thực phẩm & Đồ uống', 'Công nghệ thông tin'}
MOMENTUM_SECTORS = {
    'Chứng khoán', 'Bất động sản', 'BĐS Khu công nghiệp', 'Dầu khí', 'Dầu khí & Lọc hóa dầu',
    'Phân bón & Hóa chất', 'Hóa chất cơ bản', 'Cảng biển & Logistics', 'Xây dựng & Hạ tầng',
    'Thiết bị điện & Hạ tầng', 'Năng lượng điện'
}

# Danh mục các nhóm ngành chuẩn hóa để người dùng tùy biến khẩu vị
MAJOR_SECTOR_GROUPS = [
    'Ngân hàng',
    'Chứng khoán',
    'Thép & VLXD',
    'Bất động sản',
    'BĐS Khu công nghiệp',
    'Bán lẻ & Tiêu dùng',
    'Công nghệ thông tin',
    'Dầu khí & Năng lượng',
    'Hóa chất & Phân bón',
    'Cảng biển & Logistics',
    'Xây dựng & Hạ tầng',
    'Thủy sản & Nông nghiệp',
]
