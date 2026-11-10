/**
 * Stock RT - Frontend Indicator Constants
 * Tách biệt tập trung các hằng số tham số chỉ báo kỹ thuật để dễ dàng quản lý và tinh chỉnh
 */

// =============================================================================
// 1. SUPERTREND RIBBON CONSTANTS
// =============================================================================

// SuperTrend T+ (Ngắn hạn - Cân bằng tối ưu bảo vệ chu kỳ T+2.5, lọc nhịp xanh xịt)
export const TPLUS_SUPERTREND_PERIOD = 10;
export const TPLUS_SUPERTREND_MULTIPLIER = 1.8;

// SuperTrend Trung & Dài hạn (Theo dõi trend lớn trung hạn)
export const MIDTERM_SUPERTREND_PERIOD = 10;
export const MIDTERM_SUPERTREND_MULTIPLIER = 3.0;

// =============================================================================
// 2. ADX TREND STRENGTH CONSTANTS
// =============================================================================
export const ADX_PERIOD = 14;
export const ADX_SIDEWAY_THRESHOLD = 20.0; // Dưới 20 là vùng Sideway / Đi ngang
