// API lấy danh sách Top 10 lướt sóng T+ theo ngày
export async function getTop10Stocks() {
  const res = await fetch('/api/top-tplus');
  if (!res.ok) throw new Error(`Lỗi tải Top 10: ${res.status}`);
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