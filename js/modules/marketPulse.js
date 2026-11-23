/**
 * Stock RT - Market Pulse Module
 * Quản lý và hiển thị thông số thị trường chung (VN-Index) realtime và đánh giá chế độ thị trường (Regime)
 */

import { getMarketOverview } from '../api.js?v=5.8';
import { formatCompactNumber, formatNumber, formatDateVN } from '../utils.js?v=6.0';

const COUNTDOWN_TOTAL_SECONDS = 60; // Chu kỳ fetch mặc định: 60 giây (1 phút)
let _countdownTimer = null;
let _remainingSeconds = COUNTDOWN_TOTAL_SECONDS;
let _cachedOverviewData = null;
let _isLoading = false;
let _isCooldown = false;

/**
 * Kiểm tra xem hiện tại có đang trong phiên giao dịch chứng khoán VN hay không (Giờ VN: UTC+7)
 * Sáng: 09:00 - 11:30 | Chiều: 13:00 - 15:00 (Thứ 2 đến Thứ 6)
 */
function getMarketSessionInfo() {
  const now = new Date();
  // Giờ theo múi giờ Việt Nam (UTC+7)
  const vnOffsetMs = 7 * 60 * 60 * 1000;
  const utcMs = now.getTime() + (now.getTimezoneOffset() * 60000);
  const vnDate = new Date(utcMs + vnOffsetMs);

  const day = vnDate.getDay(); // 0 = CN, 6 = T7
  const hour = vnDate.getHours();
  const minute = vnDate.getMinutes();
  const timeInMinutes = hour * 60 + minute;

  // Cuối tuần
  if (day === 0 || day === 6) {
    return { isOpen: false, statusText: 'Nghỉ cuối tuần', statusClass: 'text-slate-400 bg-slate-900 border-slate-700' };
  }

  // Khớp lệnh sáng: 09:00 (540) - 11:30 (690)
  if (timeInMinutes >= 540 && timeInMinutes <= 690) {
    return { isOpen: true, statusText: 'Đang giao dịch', statusClass: 'text-emerald-400 bg-emerald-950/60 border-emerald-800/40' };
  }

  // Nghỉ trưa: 11:31 - 12:59
  if (timeInMinutes > 690 && timeInMinutes < 780) {
    return { isOpen: false, statusText: 'Nghỉ trưa (11:30 - 13:00)', statusClass: 'text-amber-300 bg-amber-950/60 border-amber-800/40' };
  }

  // Khớp lệnh chiều: 13:00 (780) - 14:45 (885, kết thúc ATC)
  if (timeInMinutes >= 780 && timeInMinutes <= 885) {
    return { isOpen: true, statusText: 'Đang giao dịch (Phiên chiều)', statusClass: 'text-emerald-400 bg-emerald-950/60 border-emerald-800/40' };
  }

  // Giao dịch thỏa thuận sau ATC: 14:46 - 15:00
  if (timeInMinutes > 885 && timeInMinutes <= 900) {
    return { isOpen: false, statusText: 'Đã chốt ATC (Thỏa thuận)', statusClass: 'text-slate-300 bg-slate-900 border-slate-700' };
  }

  // Trước 09:00
  if (timeInMinutes < 540) {
    return { isOpen: false, statusText: 'Chờ mở cửa 09:00', statusClass: 'text-blue-300 bg-blue-950/60 border-blue-800/40' };
  }

  // Sau 15:00
  return { isOpen: false, statusText: 'Đã đóng cửa phiên', statusClass: 'text-slate-400 bg-slate-900 border-slate-700' };
}

/**
 * Cập nhật hiển thị đồng hồ đếm ngược từng giây
 */
function updateCountdownDisplay() {
  const el = document.getElementById('marketPulseCountdown');
  if (!el) return;
  const m = Math.floor(Math.max(0, _remainingSeconds) / 60);
  const s = Math.max(0, _remainingSeconds) % 60;
  el.innerText = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

/**
 * Bắt đầu đồng hồ đếm ngược 60 giây và tự động fetch khi hết giờ
 */
function startCountdown() {
  if (_countdownTimer) clearInterval(_countdownTimer);
  _remainingSeconds = COUNTDOWN_TOTAL_SECONDS;
  updateCountdownDisplay();

  _countdownTimer = setInterval(() => {
    _remainingSeconds--;
    if (_remainingSeconds <= 0) {
      _remainingSeconds = COUNTDOWN_TOTAL_SECONDS;
      loadMarketOverview(false); // Auto-fetch
    }
    updateCountdownDisplay();
  }, 1000);
}

/**
 * Helper an toàn cập nhật innerText của phần tử DOM
 */
function safeSetText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = (text !== undefined && text !== null && text !== '') ? text : '--';
}

/**
 * Render dữ liệu thị trường chung lên giao diện
 */
function renderMarketOverview(data) {
  if (!data) return;
  _cachedOverviewData = data;

  const vn = data.vnindex || {};
  const regime = data.regime || {};
  const sentiment = data.sentiment || {};
  const assess = data.assessment || {};

  // 1. Cập nhật Badge Trạng thái phiên
  const sessionInfo = getMarketSessionInfo();
  const badgeEl = document.getElementById('marketSessionStatusBadge');
  const badgeTextEl = document.getElementById('marketSessionStatusText');
  if (badgeTextEl) badgeTextEl.innerText = sessionInfo.statusText;
  if (badgeEl) {
    badgeEl.className = `inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded border ${sessionInfo.statusClass}`;
  }

  // 2. Cập nhật Điểm số & Biến động VN-Index
  const price = vn.price || 0.0;
  const change = vn.change || 0.0;
  const changePct = vn.changePercent || 0.0;

  safeSetText('marketVnindexPrice', formatNumber(price, 2));
  safeSetText('marketVnindexRef', formatNumber(vn.ref, 2));
  safeSetText('marketVnindexVolume', formatCompactNumber(vn.volume || 0));

  if (vn.estValueTrillion && vn.estValueTrillion > 0) {
    safeSetText('marketVnindexValue', `~${formatNumber(vn.estValueTrillion, 2)}K Tỷ`);
  } else {
    safeSetText('marketVnindexValue', 'Đang tính');
  }

  // Đổi màu điểm số & badge theo tăng / giảm / đứng
  const changeBadge = document.getElementById('marketVnindexChangeBadge');
  const changeIcon = document.getElementById('marketVnindexChangeIcon');
  const changeValEl = document.getElementById('marketVnindexChange');
  const changePctEl = document.getElementById('marketVnindexChangePct');

  if (changeValEl && changePctEl) {
    const sign = change > 0 ? '+' : '';
    changeValEl.innerText = `${sign}${formatNumber(change, 2)}`;
    changePctEl.innerText = `(${sign}${formatNumber(changePct, 2)}%)`;

    if (change > 0) {
      if (changeBadge) changeBadge.className = 'inline-flex items-center gap-1 font-mono font-bold text-xs sm:text-sm px-2.5 py-1 rounded-lg bg-emerald-950/80 text-emerald-400 border border-emerald-800/60 shadow-sm';
      if (changeIcon) changeIcon.innerHTML = '<i class="fa-solid fa-arrow-trend-up text-xs"></i>';
    } else if (change < 0) {
      if (changeBadge) changeBadge.className = 'inline-flex items-center gap-1 font-mono font-bold text-xs sm:text-sm px-2.5 py-1 rounded-lg bg-rose-950/80 text-rose-400 border border-rose-800/60 shadow-sm';
      if (changeIcon) changeIcon.innerHTML = '<i class="fa-solid fa-arrow-trend-down text-xs"></i>';
    } else {
      if (changeBadge) changeBadge.className = 'inline-flex items-center gap-1 font-mono font-bold text-xs sm:text-sm px-2.5 py-1 rounded-lg bg-amber-950/80 text-amber-300 border border-amber-800/60 shadow-sm';
      if (changeIcon) changeIcon.innerHTML = '<i class="fa-solid fa-minus text-xs"></i>';
    }
  }

  // Độ rộng số mã tăng / không đổi / giảm
  safeSetText('marketBreadthAdvances', vn.advances !== null ? formatNumber(vn.advances) : '--');
  safeSetText('marketBreadthNoChange', vn.noChange !== null ? formatNumber(vn.noChange) : '--');
  safeSetText('marketBreadthDeclines', vn.declines !== null ? formatNumber(vn.declines) : '--');
  safeSetText('marketDataSourceTag', vn.source || 'VPS REALTIME');

  // 3. Khối Tâm lý & Sức mạnh
  safeSetText('marketSentimentScore', `${sentiment.score || '--'}/100`);
  safeSetText('marketSentimentLabel', sentiment.label || 'Trung lập');

  const sentimentBadge = document.getElementById('marketSentimentLabelBadge');
  if (sentimentBadge) {
    const sc = sentiment.score || 50;
    if (sc <= 30) {
      sentimentBadge.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-950/80 text-rose-300 border border-rose-800/50';
    } else if (sc < 50) {
      sentimentBadge.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-950/80 text-amber-300 border border-amber-800/50';
    } else if (sc <= 70) {
      sentimentBadge.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-blue-950/80 text-blue-300 border border-blue-800/50';
    } else {
      sentimentBadge.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-800/50';
    }
  }

  // Độ rộng % mã trên MA20
  const breadthPct = regime.breadthPctAboveMa20;
  if (breadthPct !== null && breadthPct !== undefined) {
    safeSetText('marketBreadthPct', `${formatNumber(breadthPct, 1)}%`);
    const bar = document.getElementById('marketBreadthProgressBar');
    if (bar) {
      bar.style.width = `${Math.min(100, Math.max(0, breadthPct))}%`;
      if (breadthPct >= 50) {
        bar.className = 'bg-emerald-500 h-1.5 rounded-full transition-all duration-500';
      } else if (breadthPct >= 35) {
        bar.className = 'bg-amber-400 h-1.5 rounded-full transition-all duration-500';
      } else {
        bar.className = 'bg-rose-500 h-1.5 rounded-full transition-all duration-500';
      }
    }
  } else {
    safeSetText('marketBreadthPct', '--%');
  }

  safeSetText('marketRegimeScore', `${regime.score || 0}/${regime.maxScore || 5} Điều kiện`);
  safeSetText('marketRiskCoeff', `${regime.coefficient !== undefined ? (regime.coefficient * 100).toFixed(0) + '%' : '--'}`);

  // 4. Khối Đánh giá thị trường & Khuyến nghị
  const regimeBadge = document.getElementById('marketRegimeBadge');
  if (regimeBadge) {
    regimeBadge.innerText = regime.label || 'ĐANG ĐÁNH GIÁ';
    const color = regime.statusColor || 'rose';
    if (color === 'emerald') {
      regimeBadge.className = 'inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-700/60 shadow-sm';
    } else if (color === 'amber') {
      regimeBadge.className = 'inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-950/80 text-amber-300 border border-amber-700/60 shadow-sm';
    } else {
      regimeBadge.className = 'inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-950/80 text-rose-300 border border-rose-700/60 shadow-sm';
    }
  }

  safeSetText('marketDiagnosisText', assess.diagnosis || 'Đang cập nhật đánh giá.');
  safeSetText('marketActionText', assess.action || 'Theo dõi sát diễn biến thị trường.');

  // Thời gian cập nhật gần nhất
  const now = new Date();
  const timeStr = now.toLocaleTimeString('vi-VN', { hour12: false });
  safeSetText('marketPulseLastUpdated', `Cập nhật: ${timeStr}`);
}

/**
 * Tải dữ liệu tổng quan thị trường từ API
 */
export async function loadMarketOverview(isManual = false) {
  if (_isLoading) return;
  _isLoading = true;

  const refreshIcon = document.getElementById('refreshMarketPulseIcon');
  const refreshText = document.getElementById('btnRefreshMarketPulseText');
  if (isManual && refreshIcon) refreshIcon.classList.add('animate-spin');
  if (isManual && refreshText) refreshText.innerText = 'Đang tải...';

  try {
    const data = await getMarketOverview();
    if (data && !data.error) {
      renderMarketOverview(data);
    }
  } catch (err) {
    console.warn('Lỗi cập nhật tổng quan thị trường:', err);
  } finally {
    _isLoading = false;
    if (refreshIcon) refreshIcon.classList.remove('animate-spin');
    if (refreshText) refreshText.innerText = 'Làm mới';
  }
}

/**
 * Render nội dung Modal chi tiết 5 tiêu chí Regime
 */
function renderRegimeModal() {
  if (!_cachedOverviewData) return;
  const regime = _cachedOverviewData.regime || {};
  const conditions = regime.conditions || [];

  safeSetText('modalRegimeScoreBadge', `${regime.score || 0}/5 Đạt (${regime.label || ''})`);
  safeSetText('modalRegimeAsOf', `Dữ liệu chốt phiên: ${formatDateVN(regime.asOf || '')}`);

  const container = document.getElementById('modalConditionsList');
  if (!container) return;

  if (!conditions || conditions.length === 0) {
    container.innerHTML = '<div class="text-slate-400 py-3 text-center">Chưa có dữ liệu tiêu chí chi tiết.</div>';
    return;
  }

  let html = '';
  conditions.forEach((c, idx) => {
    const isMet = c.met === true;
    const isUnknown = c.met === null || c.met === undefined;

    let iconHtml = '';
    let cardClass = '';

    if (isMet) {
      iconHtml = '<span class="w-6 h-6 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center flex-shrink-0 text-xs border border-emerald-500/30"><i class="fa-solid fa-check"></i></span>';
      cardClass = 'bg-emerald-950/20 border-emerald-900/40 text-emerald-300';
    } else if (isUnknown) {
      iconHtml = '<span class="w-6 h-6 rounded-full bg-slate-800 text-slate-400 flex items-center justify-center flex-shrink-0 text-xs border border-slate-700"><i class="fa-solid fa-question"></i></span>';
      cardClass = 'bg-slate-900/50 border-slate-800 text-slate-400';
    } else {
      iconHtml = '<span class="w-6 h-6 rounded-full bg-rose-500/20 text-rose-400 flex items-center justify-center flex-shrink-0 text-xs border border-rose-500/30"><i class="fa-solid fa-xmark"></i></span>';
      cardClass = 'bg-rose-950/20 border-rose-900/40 text-rose-300';
    }

    html += `
      <div class="p-3 rounded-xl border ${cardClass} flex items-start gap-2.5">
        ${iconHtml}
        <div class="flex-1 space-y-0.5">
          <div class="flex items-center justify-between gap-2">
            <span class="font-bold text-white text-xs">${idx + 1}. ${c.name}</span>
            <span class="text-[10px] font-mono uppercase px-1.5 py-0.2 rounded ${isMet ? 'bg-emerald-950 text-emerald-400 border border-emerald-800' : 'bg-rose-950 text-rose-400 border border-rose-800'}">
              ${isMet ? 'ĐẠT' : (isUnknown ? 'THIẾU DATA' : 'KHÔNG ĐẠT')}
            </span>
          </div>
          <p class="text-[11px] text-slate-300 font-mono">${c.detail || '--'}</p>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;
}

/**
 * Đăng ký sự kiện nút bấm và Modal
 */
function initEvents() {
  const btnRefresh = document.getElementById('btnRefreshMarketPulse');
  if (btnRefresh && !btnRefresh.dataset.bound) {
    btnRefresh.dataset.bound = 'true';
    btnRefresh.addEventListener('click', () => {
      if (_isCooldown) return;
      _isCooldown = true;
      _remainingSeconds = COUNTDOWN_TOTAL_SECONDS;
      updateCountdownDisplay();
      loadMarketOverview(true);

      setTimeout(() => {
        _isCooldown = false;
      }, 3000); // 3 giây chống spam click
    });
  }

  // Mở modal
  const btnOpenModal = document.getElementById('btnOpenRegimeModal');
  const modal = document.getElementById('modalRegimeDetails');
  if (btnOpenModal && modal && !btnOpenModal.dataset.bound) {
    btnOpenModal.dataset.bound = 'true';
    btnOpenModal.addEventListener('click', () => {
      renderRegimeModal();
      modal.classList.remove('hidden');
    });
  }

  // Đóng modal
  const btnCloseX = document.getElementById('btnCloseRegimeModal');
  const btnCloseBtn = document.getElementById('btnCloseRegimeModalBtn');

  const closeModal = () => {
    if (modal) modal.classList.add('hidden');
  };

  if (btnCloseX && !btnCloseX.dataset.bound) {
    btnCloseX.dataset.bound = 'true';
    btnCloseX.addEventListener('click', closeModal);
  }
  if (btnCloseBtn && !btnCloseBtn.dataset.bound) {
    btnCloseBtn.dataset.bound = 'true';
    btnCloseBtn.addEventListener('click', closeModal);
  }
  if (modal && !modal.dataset.bound) {
    modal.dataset.bound = 'true';
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });
  }
}

/**
 * Khởi tạo module Market Pulse
 */
export function initMarketPulse() {
  initEvents();
  loadMarketOverview(false);
  startCountdown();
}

