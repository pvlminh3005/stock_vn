/**
 * Stock RT - API Base URLs & Endpoint Registry
 * Tập trung toàn bộ Root / Base URLs và các sub-path API của hệ thống.
 * Các hàm chỉ cần truyền sub-url hoặc sử dụng API_ENDPOINTS.
 */

// Root Base URL của hệ thống API backend
export const API_BASE_URL = '/api';

/**
 * Tạo URL đầy đủ từ sub-url hoặc sub-path.
 * @param {string} subUrl - Ví dụ: '/stock', 'stock', '/portfolio-bundle?capital=...'
 * @returns {string} URL hợp lệ, ví dụ: '/api/stock'
 */
export function buildApiUrl(subUrl) {
  if (!subUrl) return API_BASE_URL;

  // Nếu là URL tuyệt đối có schema (http:// hoặc https://) thì giữ nguyên
  if (subUrl.startsWith('http://') || subUrl.startsWith('https://')) {
    return subUrl;
  }

  const cleanSubUrl = subUrl.startsWith('/') ? subUrl : `/${subUrl}`;

  // Tránh bị nối lặp lại '/api/api/...' nếu caller đã truyền sẵn tiền tố
  if (cleanSubUrl.startsWith(API_BASE_URL + '/') || cleanSubUrl === API_BASE_URL) {
    return cleanSubUrl;
  }

  return `${API_BASE_URL}${cleanSubUrl}`;
}

// Bảng kê toàn bộ sub-endpoints chuẩn hóa của ứng dụng
export const API_ENDPOINTS = {
  TOP_TPLUS: '/top-tplus',
  SCREENER: '/screener',
  SCREENER_OPTIONS: '/screener-options',
  STOCK: '/stock',
  CHART: '/chart',
  SEARCH: '/search',
  MARKET_REGIME: '/market-regime',
  MARKET_SENTIMENT: '/market-sentiment',
  PORTFOLIO: '/portfolio',
  PORTFOLIO_BUNDLE: '/portfolio-bundle',
  PORTFOLIO_ALTERNATIVES: '/portfolio-alternatives',
  PORTFOLIO_SECTORS: '/portfolio-sectors',
  PORTFOLIO_TRADE: '/portfolio/trade',
  PORTFOLIO_TRADE_DELETE: '/portfolio/trade/delete',
  PORTFOLIO_RESET: '/portfolio/reset',
  PORTFOLIO_SETTINGS: '/portfolio/settings',
  AUTH_VERIFY: '/auth/verify',
  AUTH_LOGOUT: '/auth/logout',
};

