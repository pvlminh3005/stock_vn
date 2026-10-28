import { formatVND } from '../utils.js?v=4.0';
import { getTop10Stocks } from '../api.js?v=4.0';
import {
  COUNTDOWN_TOTAL_SECONDS,
  CONFIRMATION_TIME_TOTAL_MINS
} from '../constants/config.js?v=4.0';

let onSelectStockCallback = null;
let activeTicker = '';
let refreshTimer = null;
let countdownTimer = null;
let remainingSeconds = COUNTDOWN_TOTAL_SECONDS;
let isFetching = false;
let cachedOpportunities = [];
let previousStatuses = {}; // Lưu trữ trạng thái trước đó để nhận diện chuyển biến MUA NGAY

function safeSetText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = (text !== undefined && text !== null) ? text : '--';
}

/**
 * Cập nhật hiển thị đồng hồ đếm ngược từng giây (MM:SS)
 */
function updateCountdownDisplay() {
  const el = document.getElementById('topTPlusCountdown');
  if (!el) return;
  const m = Math.floor(Math.max(0, remainingSeconds) / 60);
  const s = Math.max(0, remainingSeconds) % 60;
  el.innerText = `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

/**
 * Bắt đầu / Đặt lại bộ đếm ngược 180 giây
 */
function startCountdown() {
  if (countdownTimer) clearInterval(countdownTimer);
  remainingSeconds = COUNTDOWN_TOTAL_SECONDS;
  updateCountdownDisplay();

  countdownTimer = setInterval(() => {
    remainingSeconds--;
    if (remainingSeconds <= 0) {
      remainingSeconds = COUNTDOWN_TOTAL_SECONDS;
      loadTopTPlusOpportunities(true);
    }
    updateCountdownDisplay();
  }, 1000);
}

/**
 * Render danh sách tối đa 8 thẻ cơ hội T+
 */
function renderCards(opportunities) {
  const container = document.getElementById('topTPlusListContainer');
  if (!container) return;

  if (!opportunities || opportunities.length === 0) {
    container.innerHTML = `
      <div class="w-full py-4 text-center text-xs text-slate-500 bg-slate-950/40 rounded-xl border border-slate-800/60">
        <i class="fa-solid fa-circle-info text-blue-400 mr-1.5"></i>
        <span>Hiện chưa có mã đạt chuẩn R/R &ge; 1.3 &amp; Vol/MA20 hoặc thị trường đang ngoài giờ giao dịch.</span>
      </div>
    `;
    return;
  }

  // Tính toán thời gian còn lại đến mốc xác nhận 13:45
  const now = new Date();
  const isWeekday = now.getDay() >= 1 && now.getDay() <= 5;
  const curMins = now.getHours() * 60 + now.getMinutes();
  const isMorningSession = isWeekday && (curMins >= 9 * 60 && curMins < CONFIRMATION_TIME_TOTAL_MINS);
  const minsUntil1345 = Math.max(0, CONFIRMATION_TIME_TOTAL_MINS - curMins);
  let waitTimeHint = '';
  if (isMorningSession && minsUntil1345 > 0) {
    const h = Math.floor(minsUntil1345 / 60);
    const m = minsUntil1345 % 60;
    waitTimeHint = h > 0 ? `${h}h${m > 0 ? m + 'p' : ''}` : `${m}p`;
  }

  const html = opportunities.map(opp => {
    const isBreakout = (opp.tagType || opp.tier) === 'BREAKOUT_T0';
    const isSectorWave = !!opp.isSectorWave;
    const isActive = activeTicker && activeTicker.toUpperCase() === opp.symbol.toUpperCase();
    const actionStatus = opp.actionStatus || 'BUY_READY';

    // Nhận diện trạng thái vừa mới chuyển sang MUA NGAY trong phiên treo app
    const prevStatus = previousStatuses[opp.symbol];
    const justActivated = (actionStatus === 'BUY_READY') && (prevStatus && prevStatus !== 'BUY_READY');

    // Lưu trạng thái hiện tại
    previousStatuses[opp.symbol] = actionStatus;

    // Màu sắc theo biến động giá
    const changeVal = opp.changePct !== undefined ? opp.changePct : (opp.change_pct || 0);
    const changeColor = changeVal > 0 ? 'text-emerald-400' : changeVal < 0 ? 'text-rose-400' : 'text-amber-400';
    const changeSign = changeVal > 0 ? '+' : '';

    // Đèn Hành Động (Action Status Badge)
    let actionBadgeHtml = '';
    if (actionStatus === 'BUY_READY') {
      actionBadgeHtml = `
        <span class="text-[10px] font-black px-2 py-0.5 rounded-md bg-emerald-500/20 text-emerald-300 border border-emerald-500/60 flex items-center gap-1 shadow-[0_0_10px_rgba(16,185,129,0.35)]">
          <span class="relative flex h-1.5 w-1.5">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span class="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
          </span>
          <span>MUA NGAY</span>
        </span>`;
    } else if (actionStatus === 'WAITING_CONFIRMATION') {
      const hintTxt = waitTimeHint ? ` (${waitTimeHint})` : '';
      actionBadgeHtml = `
        <span class="text-[10px] font-bold px-2 py-0.5 rounded-md bg-amber-500/15 text-amber-300 border border-amber-500/50 flex items-center gap-1" title="Chờ kiểm định hấp thụ hàng T+ sau 13:45">
          <i class="fa-solid fa-clock text-[9px] text-amber-400"></i>
          <span>CHỜ 13:45${hintTxt}</span>
        </span>`;
    } else if (actionStatus === 'OVER_EXTENDED') {
      actionBadgeHtml = `
        <span class="text-[10px] font-bold px-2 py-0.5 rounded-md bg-rose-500/15 text-rose-300 border border-rose-500/50 flex items-center gap-1">
          <i class="fa-solid fa-ban text-[9px] text-rose-400"></i>
          <span>ĐÃ CHẠY XA</span>
        </span>`;
    } else {
      actionBadgeHtml = `
        <span class="text-[10px] font-bold px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 border border-slate-700 flex items-center gap-1">
          <i class="fa-solid fa-triangle-exclamation text-[9px] text-orange-400"></i>
          <span>TT RỦI RO</span>
        </span>`;
    }

    // Huy hiệu phân loại (Sóng ngành / Bùng nổ D1 / Pullback)
    let tierBadge = '';
    if (isSectorWave) {
      tierBadge = `
        <span class="text-[9px] font-bold px-1.5 py-0.5 rounded bg-blue-950/90 text-blue-300 border border-blue-600/50 flex items-center gap-1 shadow-sm" title="Sóng ngành đồng thuận cùng Leader ${opp.sectorLeader || ''}">
          <i class="fa-solid fa-water text-[8px] text-blue-400 animate-pulse"></i> Sóng ${opp.sector || 'Ngành'}
        </span>`;
    } else if (isBreakout) {
      tierBadge = `
        <span class="text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-950/90 text-emerald-300 border border-emerald-600/50 flex items-center gap-1 shadow-sm">
          <i class="fa-solid fa-bolt text-[8px] text-amber-400"></i> Bùng nổ D1
        </span>`;
    } else {
      tierBadge = `
        <span class="text-[9px] font-bold px-1.5 py-0.5 rounded bg-cyan-950/90 text-cyan-300 border border-cyan-600/50 flex items-center gap-1 shadow-sm">
          <i class="fa-solid fa-crosshairs text-[8px] text-cyan-400"></i> Pullback nền
        </span>`;
    }

    // Tỷ trọng khuyến nghị
    const allocBadge = isBreakout
      ? `<span class="text-[10px] font-semibold text-amber-300 bg-amber-950/60 border border-amber-700/40 px-1.5 py-0.5 rounded">100% Size</span>`
      : `<span class="text-[10px] font-semibold text-cyan-300 bg-cyan-950/60 border border-cyan-700/40 px-1.5 py-0.5 rounded">30-50% Thăm dò</span>`;

    // Khung border active hoặc mặc định
    let borderClass = 'border-slate-800 bg-slate-950/80 hover:border-blue-500/60 hover:bg-slate-800/70';
    if (isActive) {
      borderClass = 'border-amber-500 bg-slate-800/95 shadow-[0_0_14px_rgba(245,158,11,0.25)] ring-1 ring-amber-500/50';
    } else if (justActivated) {
      // Hiệu ứng lóe sáng viền xanh 3 lần khi vừa được mở khóa MUA NGAY
      borderClass = 'border-emerald-400 bg-emerald-950/40 ring-2 ring-emerald-400 shadow-[0_0_24px_rgba(16,185,129,0.55)] animate-[pulse_1.5s_ease-in-out_3]';
    } else if (actionStatus === 'BUY_READY') {
      borderClass = 'border-emerald-500/60 bg-slate-950/90 shadow-[0_0_14px_rgba(16,185,129,0.15)] hover:border-emerald-400';
    }

    const netRR = opp.netRR !== undefined ? opp.netRR : (opp.risk_reward || 0);
    const guideTxt = opp.actionGuide || opp.timingNote || opp.catalyst || 'Đạt chuẩn 5 tiêu chí VSR';
    const slVal = opp.slPct !== undefined ? opp.slPct : -3.5;
    const tpVal = opp.tp1Pct !== undefined ? opp.tp1Pct : 6.0;

    // Mức giá vào: Nếu là Pullback/Sóng ngành thì hiển thị rõ P_rev
    const revPrice = opp.reversalPrice || opp.support || opp.price;
    const entryLabel = isBreakout ? 'Vào:' : 'Đón lõng (P_rev):';
    const entryValue = isBreakout ? (opp.entryZone || `${formatVND(opp.price)} đ`) : `${formatVND(revPrice)} đ`;

    return `
      <div class="top-tplus-card min-w-[225px] max-w-[255px] flex-shrink-0 p-3 rounded-xl border ${borderClass} transition-all duration-200 cursor-pointer select-none group space-y-2"
           data-symbol="${opp.symbol}">
        <!-- Hàng 1: Mã CK + Đèn Hành Động -->
        <div class="flex items-center justify-between gap-1.5">
          <div class="flex items-center gap-1.5">
            <span class="text-sm font-black text-white group-hover:text-blue-400 transition-colors font-mono tracking-tight">
              ${opp.symbol}
            </span>
            ${tierBadge}
          </div>
          ${actionBadgeHtml}
        </div>

        <!-- Hàng 2: Giá hiện tại & % Biến động -->
        <div class="flex items-baseline justify-between">
          <span class="text-xs font-mono font-bold text-slate-200">
            ${formatVND(opp.price)} đ
          </span>
          <span class="text-[11px] font-mono font-black ${changeColor}">
            ${changeSign}${changeVal.toFixed(1)}%
          </span>
        </div>

        <!-- Hàng 3: 1-Click Action (Vùng mua / Đón lõng P_rev + SL/TP) -->
        <div class="p-1.5 rounded-lg bg-slate-900/90 border border-slate-800 text-[10px] font-mono space-y-0.5">
          <div class="flex items-center justify-between text-slate-400">
            <span class="text-slate-400 font-sans">${entryLabel}</span>
            <span class="${isBreakout ? 'text-slate-200' : 'text-amber-300'} font-bold">${entryValue}</span>
          </div>
          <div class="flex items-center justify-between pt-0.5 border-t border-slate-800/60">
            <span class="text-rose-400 font-bold">SL: ${slVal}%</span>
            <span class="text-emerald-400 font-bold">TP: +${tpVal}%</span>
            <span class="text-blue-400 font-bold">R/R: ${Number(netRR).toFixed(1)}</span>
          </div>
        </div>

        <!-- Hàng 4: Tỷ trọng khuyến nghị & Chỉ dẫn hành động -->
        <div class="text-[10px] text-slate-400 truncate group-hover:text-slate-200 transition-colors" title="${guideTxt}">
          <i class="fa-solid fa-bullseye text-[9px] text-amber-400 mr-1"></i>${guideTxt}
        </div>
      </div>
    `;
  }).join('');

  container.innerHTML = html;

  // Gắn sự kiện click cho từng thẻ cơ hội
  container.querySelectorAll('.top-tplus-card').forEach(card => {
    card.addEventListener('click', () => {
      const sym = card.getAttribute('data-symbol');
      if (sym && onSelectStockCallback) {
        setActiveTopTPlusTicker(sym);
        onSelectStockCallback(sym);
      }
    });
  });
}

/**
 * Hiển thị skeleton loading
 */
function renderSkeleton() {
  const container = document.getElementById('topTPlusListContainer');
  if (!container) return;

  container.innerHTML = Array(4).fill(0).map(() => `
    <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800 min-w-[220px] flex-shrink-0 animate-pulse space-y-2">
      <div class="flex justify-between items-center">
        <div class="h-4 bg-slate-800 rounded w-1/3"></div>
        <div class="h-4 bg-slate-800/60 rounded w-1/2"></div>
      </div>
      <div class="flex justify-between items-center">
        <div class="h-3 bg-slate-800/60 rounded w-2/5"></div>
        <div class="h-3 bg-slate-800/40 rounded w-1/4"></div>
      </div>
      <div class="h-3 bg-slate-800/40 rounded w-full"></div>
    </div>
  `).join('');
}

/**
 * Tải danh sách Top 8 cơ hội T+ từ API
 */
export async function loadTopTPlusOpportunities(isSilent = false) {
  if (isFetching) return;
  isFetching = true;

  const refreshIcon = document.getElementById('refreshTopTPlusIcon');
  if (refreshIcon) refreshIcon.classList.add('animate-spin');

  if (!isSilent && cachedOpportunities.length === 0) {
    renderSkeleton();
  }

  try {
    const res = await getTop10Stocks();
    const rawList = res ? (res.topOpportunities || res.data || res.stocks || res.top) : null;
    if (Array.isArray(rawList)) {
      cachedOpportunities = rawList;
      renderCards(cachedOpportunities);

      const updateTimeEl = document.getElementById('topTPlusUpdateTime');
      if (updateTimeEl) {
        if (res.updatedAt) {
          updateTimeEl.innerText = `Cập nhật: ${res.updatedAt}`;
        } else {
          const now = new Date();
          updateTimeEl.innerText = `Cập nhật: ${now.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
        }
      }
    } else {
      console.warn("Dữ liệu top-tplus không hợp lệ:", res);
      renderCards([]);
    }
  } catch (err) {
    console.error("Lỗi khi tải Top T+:", err);
    if (!isSilent) {
      const container = document.getElementById('topTPlusListContainer');
      if (container) {
        container.innerHTML = `
          <div class="w-full py-3 text-center text-xs text-rose-400 bg-rose-950/20 rounded-xl border border-rose-900/40 flex items-center justify-center gap-2">
            <i class="fa-solid fa-triangle-exclamation"></i>
            <span>Không thể kết nối máy chủ quét T+. Đang thử lại trong 3 phút...</span>
          </div>
        `;
      }
    }
  } finally {
    isFetching = false;
    if (refreshIcon) refreshIcon.classList.remove('animate-spin');
    // Đặt lại đồng hồ đếm ngược 180s sau mỗi lần fetch xong
    startCountdown();
  }
}

/**
 * Cập nhật trạng thái active card khi người dùng đổi mã ở bất kỳ đâu
 */
export function setActiveTopTPlusTicker(symbol) {
  activeTicker = symbol ? symbol.toUpperCase() : '';
  const container = document.getElementById('topTPlusListContainer');
  if (!container) return;

  container.querySelectorAll('.top-tplus-card').forEach(card => {
    const sym = card.getAttribute('data-symbol');
    const isActive = sym && sym.toUpperCase() === activeTicker;
    if (isActive) {
      card.classList.add('ring-2', 'ring-amber-500', 'border-amber-500', 'bg-slate-800/95');
    } else {
      card.classList.remove('ring-2', 'ring-amber-500', 'border-amber-500', 'bg-slate-800/95');
    }
  });
}

/**
 * Khởi tạo Top 8 T+ bar: tải dữ liệu ban đầu, gán click & hẹn giờ 3 phút
 */
export function initTopTPlusBar(selectStockCb) {
  onSelectStockCallback = selectStockCb;

  // Gắn sự kiện nút làm mới thủ công
  const btnRefresh = document.getElementById('btnRefreshTopTPlus');
  if (btnRefresh) {
    btnRefresh.addEventListener('click', (e) => {
      e.preventDefault();
      loadTopTPlusOpportunities(false);
    });
  }

  // Khởi động đồng hồ đếm ngược và tải lần đầu
  startCountdown();
  loadTopTPlusOpportunities(false);
}
