async function safeFetch(url, options = {}) {
  const pin = (typeof localStorage !== 'undefined') ? localStorage.getItem('stock_rt_pin') : null;
  const headers = new Headers(options.headers || {});
  if (pin && !headers.has('X-Access-Pin')) {
    headers.set('X-Access-Pin', pin);
  }
  const mergedOptions = { ...options, headers };
  const res = await fetch(url, mergedOptions);
  if (res.status === 401) {
    if (typeof localStorage !== 'undefined') {
      localStorage.removeItem('stock_rt_pin');
    }
    window.dispatchEvent(new Event('unauthorizedAccess'));
    throw new Error('Yêu cầu mã PIN bảo vệ để truy cập hệ thống');
  }
  return res;
}

// API lấy danh sách Top 10 lướt sóng T+ theo ngày
export async function getTop10Stocks() {
  const res = await safeFetch('/api/top-tplus');
  if (!res.ok) throw new Error(`Lỗi tải Top 10: ${res.status}`);
  return await res.json();
}

// API lấy kết quả Stock Screener định lượng chuẩn 5 tiêu chí lướt sóng
export async function getScreenerStocks() {
  const res = await safeFetch('/api/screener');
  if (!res.ok) throw new Error(`Lỗi tải dữ liệu Screener: ${res.status}`);
  return await res.json();
}

// API lấy chi tiết dữ liệu kỹ thuật, cơ bản & tin tức của 1 mã
export async function getStockDetail(ticker, resolution = '1D') {
  const symbol = ticker.trim().toUpperCase();
  const res = await safeFetch(`/api/stock?ticker=${symbol}&resolution=${resolution}`);
  if (!res.ok) throw new Error(`Lỗi phản hồi máy chủ: ${res.status}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data;
}

// API chỉ lấy dữ liệu nến khi người dùng chuyển khung thời gian biểu đồ
export async function getChartData(ticker, resolution = '1D') {
  const symbol = ticker.trim().toUpperCase();
  const res = await safeFetch(`/api/chart?ticker=${symbol}&resolution=${resolution}`);
  if (!res.ok) throw new Error(`Lỗi tải biểu đồ: ${res.status}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data;
}

// API lấy gói danh mục tối ưu theo số vốn
export async function getPortfolioBundle(capital = 20000000, style = 'balanced') {
  const res = await safeFetch(`/api/portfolio-bundle?capital=${encodeURIComponent(capital)}&style=${encodeURIComponent(style)}`);
  if (!res.ok) throw new Error(`Lỗi lấy gói danh mục: ${res.status}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data;
}

// API lấy danh sách cổ phiếu thay thế cùng ngành hoặc theo ngành tùy chọn
export async function getPortfolioAlternatives(symbol, sector, budget, excludeSector = '', targetSector = '') {
  let url = `/api/portfolio-alternatives?symbol=${encodeURIComponent(symbol)}&sector=${encodeURIComponent(sector)}&budget=${encodeURIComponent(budget)}`;
  if (excludeSector) {
    url += `&exclude_sector=${encodeURIComponent(excludeSector)}`;
  }
  if (targetSector) {
    url += `&target_sector=${encodeURIComponent(targetSector)}`;
  }
  const res = await safeFetch(url);
  if (!res.ok) throw new Error(`Lỗi tải mã thay thế: ${res.status}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data;
}

// API lấy thống kê các nhóm ngành khả dụng theo ngân sách slot
export async function getPortfolioSectors(budget, excludeSector = '') {
  let url = `/api/portfolio-sectors?budget=${encodeURIComponent(budget)}`;
  if (excludeSector) {
    url += `&exclude_sector=${encodeURIComponent(excludeSector)}`;
  }
  const res = await safeFetch(url);
  if (!res.ok) throw new Error(`Lỗi tải danh mục ngành: ${res.status}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data;
}

// ==================== USER PORTFOLIO / SỔ LỆNH CÁ NHÂN ====================

// API lấy toàn bộ danh mục, P&L realtime và thống kê NAV
export async function getUserPortfolio() {
  const res = await safeFetch('/api/portfolio');
  if (!res.ok) throw new Error(`Lỗi tải sổ lệnh cá nhân: ${res.status}`);
  return await res.json();
}

// API thêm giao dịch mới
export async function addUserTrade(tradeData) {
  const res = await safeFetch('/api/portfolio/trade', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify(tradeData)
  });
  const data = await res.json();
  if (!res.ok || !data.success) throw new Error(data.error || 'Lỗi thêm giao dịch');
  return data;
}

// API xóa một giao dịch theo ID
export async function deleteUserTrade(tradeId) {
  const res = await safeFetch('/api/portfolio/trade/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify({ id: tradeId })
  });
  const data = await res.json();
  if (!res.ok || !data.success) throw new Error(data.error || 'Lỗi xóa giao dịch');
  return data;
}

// API reset / xóa trắng toàn bộ sổ lệnh
export async function resetUserPortfolio() {
  const res = await safeFetch('/api/portfolio/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' }
  });
  const data = await res.json();
  if (!res.ok || !data.success) throw new Error(data.error || 'Lỗi xóa toàn bộ danh mục');
  return data;
}

// API lưu cấu hình Tổng NAV
export async function saveUserPortfolioSettings(settings) {
  const res = await safeFetch('/api/portfolio/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json; charset=utf-8' },
    body: JSON.stringify(settings)
  });
  const data = await res.json();
  if (!res.ok || !data.success) throw new Error(data.error || 'Lỗi lưu cấu hình NAV');
  return data;
}
