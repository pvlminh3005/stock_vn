/**
 * Stock RT - Frontend System & UI Configuration Constants
 * Tách biệt tập trung các hằng số chu kỳ quét, đếm ngược và mốc thời gian thị trường
 */

// Chu kỳ quét dữ liệu Screener & Top T+
export const COUNTDOWN_TOTAL_SECONDS = 180; // 3 phút
export const SCREENER_REFRESH_INTERVAL_MS = 180000; // 180.000 ms

// Mốc thời gian Khóa An Toàn 1: Xác nhận hấp thụ hàng T+ phiên chiều (13:45)
export const CONFIRMATION_TIME_HOUR = 13;
export const CONFIRMATION_TIME_MINUTE = 45;
export const CONFIRMATION_TIME_TOTAL_MINS = 13 * 60 + 45; // 825 phút
