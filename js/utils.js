// Định dạng hiển thị tiền VND (phân cách hàng nghìn)
export function formatVND(num) {
  if (num === null || num === undefined || isNaN(num)) return "--";
  return Math.round(num).toLocaleString('vi-VN');
}

// Định dạng giá VNĐ kèm ký hiệu đ cho biểu đồ và bảng giá
export function formatPriceVND(price) {
  if (price === null || price === undefined || isNaN(price)) return "--";
  return Math.round(Number(price)).toLocaleString('vi-VN') + " đ";
}

// Định dạng giá cổ phiếu chuẩn bảng điện tử (chia 1000, 2 chữ số thập phân, ví dụ: 62,70)
export function formatStockPrice(price) {
  if (price === null || price === undefined || isNaN(price)) return "--";
  const num = Number(price);
  const val = num >= 1000 ? num / 1000 : num;
  return val.toLocaleString('vi-VN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

// Định dạng khối lượng hoặc vốn hóa gọn gàng (K, M, Tỷ)
export function formatCompactNumber(num) {
  if (num === null || num === undefined || isNaN(num)) return "--";
  const abs = Math.abs(num);
  if (abs >= 1e9) {
    return (num / 1e9).toFixed(1) + " tỷ";
  }
  if (abs >= 1e6) {
    return (num / 1e6).toFixed(2) + " tr";
  }
  if (abs >= 1e3) {
    return (num / 1e3).toFixed(1) + "k";
  }
  return formatVND(num);
}

// Tính chỉ số RSI 14 phiên
export function calculateRSI(closes, period = 14) {
  if (!closes || closes.length < 3) return 50.0;
  const p = Math.min(period, closes.length - 1);
  let gains = 0, losses = 0;

  for (let i = 1; i <= p; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff >= 0) gains += diff;
    else losses -= diff;
  }

  if (losses === 0) return 80.0;
  const rs = (gains / p) / (losses / p);
  return Math.round((100 - (100 / (1 + rs))) * 10) / 10;
}

// Tính đường trung bình động Simple Moving Average (SMA)
export function calculateSMA(series, period = 20) {
  if (!series || series.length === 0) return 0;
  const slice = series.slice(-period);
  return Math.round(slice.reduce((a, b) => a + b, 0) / slice.length);
}