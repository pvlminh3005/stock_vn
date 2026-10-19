"""
Stock RT - Theme & Color Tokens
Tập trung định nghĩa mã màu hiển thị, badge, tín hiệu kỹ thuật và cảnh báo.
"""

# Badge Colors (Nguồn tin tức, sự kiện & BCTC)
BADGE_COLOR_FINANCE = 'blue'       # Báo cáo tài chính
BADGE_COLOR_COMPANY = 'amber'      # Tin tức doanh nghiệp
BADGE_COLOR_EVENT = 'cyan'         # Sự kiện HoSE/HNX & Cổ tức
BADGE_COLOR_MACRO = 'rose'         # Vĩ mô nhà nước (Cổng TTĐT Chính Phủ)
BADGE_COLOR_PRESS = 'purple'       # Báo chí thời sự (VnExpress)
BADGE_COLOR_MARKET = 'emerald'     # Bảng giá thị trường (SSI iBoard)

# Volume & Liquidity Signal Colors
VOL_COLOR_INFLOW = 'emerald'       # Dòng tiền vào mạnh (giá tăng + KL lớn)
VOL_COLOR_DISTRIBUTION = 'rose'    # Bán mạnh / Phân phối (giá giảm + KL lớn)
VOL_COLOR_WARNING = 'amber'        # Cảnh báo bất thường (giá đứng KL cao, hoặc tăng thiếu KL)
VOL_COLOR_ACTIVE = 'blue'          # Thanh khoản tích cực trên trung bình
VOL_COLOR_NEUTRAL = 'slate'        # Thanh khoản bình quân / thấp

# Overall Status Colors
STATUS_COLOR_PERFECT = 'emerald'   # Cổ phiếu hoàn hảo (FA + TA xuất sắc)
STATUS_COLOR_MOMENTUM = 'blue'     # Dòng tiền T+ mạnh (lướt sóng)
STATUS_COLOR_VALUE = 'indigo'      # Doanh nghiệp giá trị (tích sản trung hạn)
STATUS_COLOR_NEUTRAL = 'amber'     # Trạng thái trung tính (tích lũy)
STATUS_COLOR_RISK = 'rose'         # Cảnh báo rủi ro suy yếu

# Decision & Alert Types
DECISION_TYPE_SUCCESS = 'success'
DECISION_TYPE_WARNING = 'warning'
DECISION_TYPE_DANGER = 'danger'
DECISION_TYPE_INFO = 'info'
DECISION_TYPE_NEUTRAL = 'neutral'
