// API lấy danh sách Top 10 lướt sóng T+ theo ngày
export async function getTop10Stocks() {
  const res = await fetch('/api/top-tplus');
  if (!res.ok) throw new Error(`Lỗi tải Top 10: ${res.status}`);
  return await res.json();
}

// API lấy kết quả Stock Screener định lượng chuẩn 5 tiêu chí lướt sóng
export async function getScreenerStocks() {
  const res = await fetch('/api/screener');
  if (!res.ok) throw new Error(`Lỗi tải dữ liệu Screener: ${res.status}`);
  return await res.json();
}

// API lấy chi tiết dữ liệu kỹ thuật, cơ bản & tin tức của 1 mã
export async function getStockDetail(ticker, resolution = '1D') {
  const symbol = ticker.trim().toUpperCase();
  const res = await fetch(`/api/stock?ticker=${symbol}&resolution=${resolution}`);
  if (!res.ok) throw new Error(`Lỗi phản hồi máy chủ: ${res.status}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data;
}

// API chỉ lấy dữ liệu nến khi người dùng chuyển khung thời gian biểu đồ
export async function getChartData(ticker, resolution = '1D') {
  const symbol = ticker.trim().toUpperCase();
  const res = await fetch(`/api/chart?ticker=${symbol}&resolution=${resolution}`);
  if (!res.ok) throw new Error(`Lỗi tải biểu đồ: ${res.status}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data;
}

// API lấy gói danh mục tối ưu theo số vốn
export async function getPortfolioBundle(capital = 20000000, style = 'balanced') {
  const res = await fetch(`/api/portfolio-bundle?capital=${encodeURIComponent(capital)}&style=${encodeURIComponent(style)}`);
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
  const res = await fetch(url);
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
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Lỗi tải danh mục ngành: ${res.status}`);
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data;
}