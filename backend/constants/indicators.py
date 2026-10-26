"""
Stock RT - Technical & Quantitative Indicator Constants
Phân tầng thông số chỉ báo kỹ thuật theo trường phái Clean Architecture:
- Phân tầng 1: Lướt sóng T+ (Ngắn hạn - Bắt nhịp nhanh, độ nhạy cao)
- Phân tầng 2: Đầu tư Trung & Dài hạn (Lọc nhiễu, bám trọn trend lớn)
"""

# =============================================================================
# 1. PHÂN TẦNG LƯỚT SÓNG T+ (NGẮN HẠN)
# =============================================================================
TPLUS_TIMEFRAME = '1D'
TPLUS_INTRADAY_TIMEFRAME = '1H'

# SuperTrend T+ (chuẩn Ribbon co thắt động AmiBroker: bắt nhịp nhanh, trailing stop bám sát đệm lãi)
TPLUS_SUPERTREND_PERIOD = 10
TPLUS_SUPERTREND_MULTIPLIER = 1.15

# Stochastic RSI T+ (14, 14, 3, 3) - Bắt điểm xoay đảo chiều T+2.5
STOCH_RSI_PERIOD = 14
STOCH_RSI_STOCH_PERIOD = 14
STOCH_RSI_SMOOTH_K = 3
STOCH_RSI_SMOOTH_D = 3
STOCH_RSI_OVERSOLD = 20.0
STOCH_RSI_OVERBOUGHT = 80.0

# Xu hướng & Dòng tiền T+
TPLUS_VOLUME_RATIO_MIN = 1.3  # Volume > 1.3 x MA20 Volume
TPLUS_BUY_RATIO_MIN = 50.0    # Tỷ lệ lệnh mua chủ động tối thiểu

# =============================================================================
# 2. PHÂN TẦNG ĐẦU TƯ TRUNG & DÀI HẠN (3 - 12+ THÁNG)
# =============================================================================
MIDTERM_PRIMARY_TIMEFRAME = '1W'
MIDTERM_SECONDARY_TIMEFRAME = '1D'

# SuperTrend Trung hạn (Chuẩn kinh điển Olivier Seban - lọc nhiễu, bám trọn trend lớn)
MIDTERM_SUPERTREND_PERIOD = 10
MIDTERM_SUPERTREND_MULTIPLIER = 3.0

# Động lượng Trung hạn: MACD (12, 26, 9)
MACD_FAST_PERIOD = 12
MACD_SLOW_PERIOD = 26
MACD_SIGNAL_PERIOD = 9

# Xu hướng Trung & Dài hạn: EMA 50 / EMA 200
EMA_MEDIUM_PERIOD = 50
EMA_LONG_PERIOD = 200
