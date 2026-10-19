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

// Định dạng ngày hiển thị chuẩn Việt Nam (DD/MM/YYYY)
export function formatDateVN(rawDate) {
  if (!rawDate) return "--";
  const str = String(rawDate).trim();
  if (!str || str === "--") return "--";

  // 1. Chuẩn ISO: YYYY-MM-DD hoặc YYYY/MM/DD
  const isoMatch = str.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})/);
  if (isoMatch) {
    const y = isoMatch[1];
    const m = isoMatch[2].padStart(2, "0");
    const d = isoMatch[3].padStart(2, "0");
    return `${d}/${m}/${y}`;
  }

  // 2. Định dạng có AM/PM (M/D/YYYY kiểu US của ASP.NET RSS)
  if (/[ap]m/i.test(str)) {
    const mBcp = str.match(/(\d{1,2})\/(\d{1,2})\/(\d{4})/);
    if (mBcp) {
      const m = mBcp[1].padStart(2, "0");
      const d = mBcp[2].padStart(2, "0");
      const y = mBcp[3];
      return `${d}/${m}/${y}`;
    }
  }

  // 3. Chuỗi có tên tháng tiếng Anh (RFC 2822: Tue, 06 Oct 2026...)
  if (/[a-zA-Z]{3}/.test(str)) {
    const parsed = new Date(str);
    if (!isNaN(parsed.getTime())) {
      const d = String(parsed.getDate()).padStart(2, "0");
      const m = String(parsed.getMonth() + 1).padStart(2, "0");
      const y = parsed.getFullYear();
      return `${d}/${m}/${y}`;
    }
  }

  // 4. Chuẩn DD/MM/YYYY (có thể kèm giờ như 06/10/2026 17:07)
  const dmyMatch = str.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/);
  if (dmyMatch) {
    const d = dmyMatch[1].padStart(2, "0");
    const m = dmyMatch[2].padStart(2, "0");
    const y = dmyMatch[3];
    return `${d}/${m}/${y}`;
  }

  // 5. Thử fallback qua Date object
  const parsed = new Date(str);
  if (!isNaN(parsed.getTime())) {
    const d = String(parsed.getDate()).padStart(2, "0");
    const m = String(parsed.getMonth() + 1).padStart(2, "0");
    const y = parsed.getFullYear();
    return `${d}/${m}/${y}`;
  }

  return str;
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
/**
 * GLOBAL TOOLTIP PORTAL OVERLAY
 * Render nội dung tooltip trực tiếp vào cấp cao nhất của document.body.
 * Đảm bảo 100% overlay trên cùng, không bao giờ bị cắt xén (overflow / containment) hay che khuất.
 */
export function initTooltipBoundaryProtection() {
  let overlay = document.getElementById('globalTooltipOverlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'globalTooltipOverlay';
    document.body.appendChild(overlay);
  }

  let activeTrigger = null;

  function showTooltip(trigger) {
    const box = trigger.querySelector('.tooltip-box');
    if (!box) return;

    activeTrigger = trigger;
    overlay.innerHTML = box.innerHTML;

    // Reset hiển thị để đo đạc chính xác
    overlay.style.visibility = 'hidden';
    overlay.style.display = 'block';
    overlay.classList.remove('active');

    const triggerRect = trigger.getBoundingClientRect();
    const overlayWidth = overlay.offsetWidth || 310;
    const overlayHeight = overlay.offsetHeight || 130;
    const padding = 12;

    // 1. Căn ngang (căn giữa trigger, kẹp trong màn hình an toàn)
    let left = triggerRect.left + (triggerRect.width / 2) - (overlayWidth / 2);
    left = Math.max(padding, Math.min(window.innerWidth - overlayWidth - padding, left));

    // 2. Căn dọc (ưu tiên mở xuống dưới, lật lên trên nếu chạm đáy viewport)
    const spaceBelow = window.innerHeight - triggerRect.bottom;
    const spaceAbove = triggerRect.top;
    let top = triggerRect.bottom + 8;

    if (spaceBelow < overlayHeight + 16 && spaceAbove > overlayHeight + 16) {
      top = triggerRect.top - overlayHeight - 8;
    }

    overlay.style.left = `${Math.round(left)}px`;
    overlay.style.top = `${Math.round(top)}px`;
    overlay.style.visibility = 'visible';
    overlay.classList.add('active');
  }

  function hideTooltip(trigger) {
    if (activeTrigger === trigger || !trigger) {
      activeTrigger = null;
      overlay.classList.remove('active');
      overlay.style.visibility = 'hidden';
    }
  }

  // Sử dụng Event Delegation gắn trên document
  document.addEventListener('mouseenter', (e) => {
    const trigger = e.target.closest && e.target.closest('.tooltip-trigger');
    if (trigger) {
      showTooltip(trigger);
    }
  }, true);

  document.addEventListener('mouseleave', (e) => {
    const trigger = e.target.closest && e.target.closest('.tooltip-trigger');
    if (trigger) {
      hideTooltip(trigger);
    }
  }, true);

  document.addEventListener('focusin', (e) => {
    const trigger = e.target.closest && e.target.closest('.tooltip-trigger');
    if (trigger) {
      showTooltip(trigger);
    }
  }, true);

  document.addEventListener('focusout', (e) => {
    const trigger = e.target.closest && e.target.closest('.tooltip-trigger');
    if (trigger) {
      hideTooltip(trigger);
    }
  }, true);

  // Tự động ẩn khi người dùng cuộn trang
  window.addEventListener('scroll', () => {
    hideTooltip();
  }, { passive: true });
}