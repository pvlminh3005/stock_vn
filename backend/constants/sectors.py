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
