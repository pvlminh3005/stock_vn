/**
 * Stock RT - Common Utility Functions
 * Module chuẩn hóa định dạng số liệu, tiền tệ, khối lượng, tỷ lệ %, ngày tháng
 * và các bộ xử lý input trực tiếp cho toàn bộ ứng dụng.
 */

// 1. Định dạng số nguyên / khối lượng với dấu phẩy phân cách hàng nghìn (ví dụ: 1,000, 10,000)
export function formatNumber(num) {
  if (num === null || num === undefined || isNaN(num)) return "0";
  return Math.round(Number(num)).toLocaleString('en-US');
}

// 2. Định dạng hiển thị tiền VND (phân cách hàng nghìn bằng dấu phẩy, ví dụ: 500,000,000)
export function formatVND(num, withSuffix = false) {
  if (num === null || num === undefined || isNaN(num)) return withSuffix ? "-- đ" : "--";
  const formatted = Math.round(Number(num)).toLocaleString('en-US');
  return withSuffix ? `${formatted} đ` : formatted;
}

// 3. Định dạng giá VNĐ kèm ký hiệu đ (ví dụ: 27,500 đ)
export function formatPriceVND(price) {
  if (price === null || price === undefined || isNaN(price)) return "--";
  return Math.round(Number(price)).toLocaleString('en-US') + " đ";
}

// 4. Định dạng giá cổ phiếu chuẩn bảng điện tử (14,85; 157,50; ...)
// Có 2 chữ số thập phân, phân cách thập phân bằng dấu phẩy ','
export function formatStockPrice(price) {
  if (price === null || price === undefined || isNaN(price)) return "--";
  let num = Number(price);
  if (num >= 1000) {
    num = num / 1000;
  }
  return num.toFixed(2).replace('.', ',');
}

// 5. Định dạng khối lượng hoặc vốn hóa gọn gàng (K, M, Tỷ)
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
  return formatNumber(num);
}

// 6. Live Formatter cho các ô input số nguyên / khối lượng / vốn NAV (giữ nguyên vị trí con trỏ)
export function formatLiveVolumeInput(input) {
  if (!input) return;
  const oldVal = input.value;
  const oldPos = input.selectionStart || 0;
  const digitsBefore = oldVal.slice(0, oldPos).replace(/\D/g, '').length;
  const raw = oldVal.replace(/\D/g, '');
  if (!raw) {
    input.value = '';
    return;
  }
  const formatted = raw.replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  input.value = formatted;
  let newPos = 0;
  let digitCount = 0;
  for (let i = 0; i < formatted.length; i++) {
    if (/\d/.test(formatted[i])) {
      digitCount++;
    }
    if (digitCount === digitsBefore) {
      newPos = i + 1;
      break;
    }
  }
  if (typeof input.setSelectionRange === 'function') {
    input.setSelectionRange(newPos, newPos);
  }
}

// 7. Live Formatter cho các ô nhập Giá cổ phiếu (cho phép dấu phẩy thập phân duy nhất, tự chuyển phím '.' thành ',')
export function formatLivePriceInput(input) {
  if (!input) return;
  let val = input.value.replace('.', ',');
  val = val.replace(/[^0-9,]/g, '');
  const parts = val.split(',');
  if (parts.length > 2) {
    val = parts[0] + ',' + parts.slice(1).join('');
  }
  if (parts.length === 2 && parts[1].length > 2) {
    val = parts[0] + ',' + parts[1].slice(0, 2);
  }
  if (input.value !== val) {
    input.value = val;
  }
}

// 8. Chuẩn hóa giá cổ phiếu khi hoàn tất nhập (blur) hoặc format hiển thị (14,85; 157,50)
// Hỗ trợ cả 3 cách nhập:
// - Đã có dấu thập phân: 14,85 hoặc 14.85 -> 14,85
// - Nhập chia theo 100: 1485 hoặc 2750 -> chia 100 thành 14,85 hoặc 27,50
// - Nhập đầy đủ theo đồng: >= 10000 (14850, 27500) -> chia 1000 thành 14,85 hoặc 27,50
export function formatPriceInput(val) {
  if (val === undefined || val === null || val === '') return '';
  const str = String(val).trim().replace(/\s/g, '');
  const hasCommaOrDot = str.includes(',') || str.includes('.');
  let num = parseFloat(str.replace(',', '.'));
  if (isNaN(num) || num <= 0) return '';

  if (!hasCommaOrDot) {
    if (num >= 10000) {
      num = num / 1000;
    } else if (num >= 1000) {
      num = num / 100;
    }
  } else {
    if (num >= 1000) {
      num = num / 1000;
    }
  }
  return num.toFixed(2).replace('.', ',');
}

// 9. Chuyển đổi chuỗi giá người dùng nhập thành số thực cho API hoặc tính toán (ví dụ: 14.85 hoặc 14850)
export function parsePriceInputToNumber(val) {
  if (val === undefined || val === null || val === '') return 0;
  const str = String(val).trim().replace(/\s/g, '');
  const hasCommaOrDot = str.includes(',') || str.includes('.');
  let num = parseFloat(str.replace(',', '.'));
  if (isNaN(num) || num <= 0) return 0;

  if (!hasCommaOrDot) {
    if (num >= 10000) {
      num = num / 1000;
    } else if (num >= 1000) {
      num = num / 100;
    }
  } else {
    if (num >= 1000) {
      num = num / 1000;
    }
  }
  return num;
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