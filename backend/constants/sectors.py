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

# Bảng tra cứu nhóm ngành cho các cổ phiếu thanh khoản hàng đầu TTCK Việt Nam
KNOWN_STOCK_SECTORS = {
    # Ngân hàng
    'VCB': 'Ngân hàng', 'BID': 'Ngân hàng', 'CTG': 'Ngân hàng', 'TCB': 'Ngân hàng',
    'MBB': 'Ngân hàng', 'ACB': 'Ngân hàng', 'VPB': 'Ngân hàng', 'HDB': 'Ngân hàng',
    'STB': 'Ngân hàng', 'SHB': 'Ngân hàng', 'TPB': 'Ngân hàng', 'LPB': 'Ngân hàng',
    'MSB': 'Ngân hàng', 'VIB': 'Ngân hàng', 'EIB': 'Ngân hàng', 'OCB': 'Ngân hàng',
    'SSB': 'Ngân hàng', 'NAB': 'Ngân hàng', 'BVB': 'Ngân hàng',
    # Chứng khoán / Dịch vụ tài chính
    'SSI': 'Chứng khoán', 'VND': 'Chứng khoán', 'VIX': 'Chứng khoán', 'HCM': 'Chứng khoán',
    'VCI': 'Chứng khoán', 'SHS': 'Chứng khoán', 'MBS': 'Chứng khoán', 'BSI': 'Chứng khoán',
    'FTS': 'Chứng khoán', 'CTS': 'Chứng khoán', 'ORS': 'Chứng khoán', 'AGR': 'Chứng khoán',
    # Thép & Tài nguyên cơ bản
    'HPG': 'Thép & VLXD', 'HSG': 'Thép & VLXD', 'NKG': 'Thép & VLXD', 'VGS': 'Thép & VLXD',
    'TLH': 'Thép & VLXD', 'SMC': 'Thép & VLXD',
    # Bất động sản dân dụng & KCN
    'VHM': 'Bất động sản', 'VIC': 'Bất động sản', 'VRE': 'Bất động sản', 'KDH': 'Bất động sản',
    'NLG': 'Bất động sản', 'PDR': 'Bất động sản', 'DIG': 'Bất động sản', 'DXG': 'Bất động sản',
    'KBC': 'BĐS Khu công nghiệp', 'IDC': 'BĐS Khu công nghiệp', 'SZC': 'BĐS Khu công nghiệp',
    'BCM': 'BĐS Khu công nghiệp', 'VGC': 'BĐS Khu công nghiệp', 'NVL': 'Bất động sản',
    'CEO': 'Bất động sản', 'TCH': 'Bất động sản', 'HQC': 'Bất động sản', 'DPG': 'Bất động sản & Hạ tầng',
    # Bán lẻ & Tiêu dùng
    'MWG': 'Bán lẻ tiêu dùng', 'MSN': 'Bán lẻ & Tiêu dùng', 'PNJ': 'Bán lẻ trang sức',
    'DGW': 'Phân phối ICT', 'FRT': 'Bán lẻ ICT & Dược', 'VNM': 'Thực phẩm & Đồ uống',
    'SAB': 'Thực phẩm & Đồ uống', 'KDC': 'Thực phẩm & Đồ uống', 'MCH': 'Hàng tiêu dùng',
    # Công nghệ thông tin
    'FPT': 'Công nghệ thông tin', 'CMG': 'Công nghệ thông tin', 'ELC': 'Công nghệ thông tin',
    # Dầu khí & Năng lượng
    'GAS': 'Dầu khí', 'PVD': 'Dầu khí', 'PVS': 'Dầu khí', 'BSR': 'Dầu khí & Lọc hóa dầu',
    'PLX': 'Dầu khí', 'POW': 'Năng lượng điện', 'PC1': 'Năng lượng & Xây lắp', 'REE': 'Năng lượng & Cơ điện',
    'GELEX': 'Thiết bị điện & Hạ tầng', 'GEX': 'Thiết bị điện & Hạ tầng',
    # Hóa chất & Phân bón
    'DGC': 'Hóa chất cơ bản', 'DCM': 'Phân bón & Hóa chất', 'DPM': 'Phân bón & Hóa chất', 'CSV': 'Hóa chất cơ bản',
    # Vận tải & Logistics
    'HAH': 'Cảng biển & Vận tải biển', 'GMD': 'Cảng biển & Logistics', 'VSC': 'Cảng biển & Container',
    'PVT': 'Vận tải dầu khí', 'VOS': 'Vận tải biển',
    # Xây dựng & Hạ tầng
    'VCG': 'Xây dựng & Hạ tầng', 'HHV': 'Hạ tầng giao thông', 'FCN': 'Nền móng & Công trình ngầm',
    'CII': 'Hạ tầng cầu đường', 'CTD': 'Xây dựng dân dụng', 'HBC': 'Xây dựng dân dụng',
    # Thủy sản & Nông nghiệp
    'VHC': 'Thủy sản', 'ANV': 'Thủy sản', 'DBC': 'Chăn nuôi & Nông nghiệp', 'BAF': 'Chăn nuôi heo',
    'PAN': 'Nông nghiệp & Thực phẩm', 'HAG': 'Nông nghiệp & Trái cây',
}

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
