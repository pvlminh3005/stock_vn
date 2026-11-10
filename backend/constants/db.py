"""
Stock RT - Định nghĩa Tên Database & Collections trên MongoDB Atlas
File quản lý tập trung toàn bộ Database Name và Collection Names kèm mô tả ngắn gọn.
"""

# ==================== TÊN DATABASE MẶC ĐỊNH ====================
# Có thể ghi đè linh hoạt qua biến MONGODB_DB_NAME trong envs/.env.development hoặc envs/.env.production
DEFAULT_DB_NAME = 'stock_pro_db'


# ==================== TÊN CÁC COLLECTIONS & MÔ TẢ ====================

# 1. Quản lý Danh mục & Sổ lệnh cá nhân
COLL_PORTFOLIO_TRADES = 'portfolio_trades'        # Sổ lệnh mua/bán & vị thế cổ phiếu cá nhân
COLL_PORTFOLIO_SETTINGS = 'portfolio_settings'    # Cấu hình danh mục (Tổng NAV, phân bổ vốn)

# 2. Cảnh báo Telegram & Chống spam
COLL_ALERT_STATES = 'alert_states'                # Trạng thái cảnh báo gần nhất của từng mã (chống đảo chiều ảo)
COLL_TELEGRAM_ALERT_LOGS = 'telegram_alert_logs'  # Cache khóa key để chống gửi trùng lặp cảnh báo
COLL_TELEGRAM_SENT_LOGS = 'telegram_sent_logs'    # Lịch sử các tin nhắn cảnh báo bot Telegram đã phát đi

# 3. Dữ liệu Tham chiếu & Thị trường chung
COLL_COMPANIES = 'companies'                      # Danh mục hơn 1,600 công ty niêm yết (HOSE, HNX, UPCoM)
COLL_MARKET_SNAPSHOT = 'market_board_snapshot'    # Snapshot bảng giá realtime toàn thị trường (Entrade)
COLL_FUNDAMENTALS = 'fundamentals'                # Dữ liệu tài chính & chỉ số cơ bản (P/E, P/B, ROE, EPS,...)
COLL_VCI_HISTORY = 'vci_history'                  # Lịch sử phân tích & tín hiệu kỹ thuật VCI
COLL_SCREENER_SNAPSHOTS = 'screener_snapshots'    # Snapshot kết quả bộ lọc quét Top cơ hội T+


# ==================== TỔNG HỢP DICTIONARY TRA CỨU ====================
COLLECTIONS_METADATA = {
    COLL_PORTFOLIO_TRADES: "Sổ lệnh giao dịch mua/bán và trạng thái nắm giữ (Holding/Closed)",
    COLL_PORTFOLIO_SETTINGS: "Cấu hình danh mục đầu tư (Tổng NAV, quản trị tỷ trọng)",
    COLL_ALERT_STATES: "Trạng thái bộ lọc và cảnh báo kỹ thuật theo từng mã cổ phiếu",
    COLL_TELEGRAM_ALERT_LOGS: "Cache khóa cảnh báo Telegram (TTL 7 ngày) chống spam",
    COLL_TELEGRAM_SENT_LOGS: "Lịch sử chi tiết các tin nhắn Telegram đã gửi (TTL 30 ngày)",
    COLL_COMPANIES: "Thông tin danh mục doanh nghiệp, mã CK, sàn giao dịch và phân ngành",
    COLL_MARKET_SNAPSHOT: "Bản chụp dữ liệu bảng giá realtime toàn thị trường chứng khoán",
    COLL_FUNDAMENTALS: "Chỉ số tài chính cơ bản, định giá doanh nghiệp và rủi ro pha loãng",
    COLL_VCI_HISTORY: "Lịch sử dữ liệu kỹ thuật và dòng tiền VCI theo từng phiên",
    COLL_SCREENER_SNAPSHOTS: "Kết quả quét tự động Top cơ hội lướt sóng T+ trong phiên",
}

