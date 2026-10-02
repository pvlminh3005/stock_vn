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

/**
 * Tự động kiểm tra và căn chỉnh vị trí tooltip để chống tràn mép màn hình (viewport) và khung chứa
 */
export function initTooltipBoundaryProtection() {
  function handleTooltipPosition(trigger) {
    const box = trigger.querySelector('.tooltip-box');
    if (!box) return;

    // Reset style dịch chuyển inline để đo đạc chính xác
    box.style.translate = '';
    box.style.marginLeft = '';

    const rect = box.getBoundingClientRect();
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
    const container = trigger.closest('.max-w-6xl') || document.body;
    const containerRect = container.getBoundingClientRect();

    const padding = 12;
    // Ngưỡng mép phải và mép trái an toàn
    const maxAllowedRight = Math.min(viewportWidth - padding, containerRect.right - padding);
    const minAllowedLeft = Math.max(padding, containerRect.left + padding);

    if (rect.right > maxAllowedRight) {
      const overflow = rect.right - maxAllowedRight;
      if ('translate' in document.documentElement.style) {
        box.style.translate = `-${overflow + 6}px 0`;
      } else {
        box.style.marginLeft = `-${overflow + 6}px`;
      }
    } else if (rect.left < minAllowedLeft) {
      const underflow = minAllowedLeft - rect.left;
      if ('translate' in document.documentElement.style) {
        box.style.translate = `${underflow + 6}px 0`;
      } else {
        box.style.marginLeft = `${underflow + 6}px`;
      }
    }
  }

  function handleLeave(trigger) {
    const box = trigger.querySelector('.tooltip-box');
    if (box) {
      box.style.translate = '';
      box.style.marginLeft = '';
    }
  }

  // Sử dụng event delegation để tự động bảo vệ tất cả tooltip hiện tại & tạo mới
  document.addEventListener('mouseover', (e) => {
    const trigger = e.target.closest('.tooltip-trigger');
    if (trigger && !trigger._boundProtection) {
      trigger._boundProtection = true;
      trigger.addEventListener('mouseenter', () => handleTooltipPosition(trigger));
      trigger.addEventListener('mouseleave', () => handleLeave(trigger));
      trigger.addEventListener('focusin', () => handleTooltipPosition(trigger));
      trigger.addEventListener('focusout', () => handleLeave(trigger));
      handleTooltipPosition(trigger);
    }
  }, { passive: true });
}