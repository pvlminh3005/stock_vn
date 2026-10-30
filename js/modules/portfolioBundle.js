import { formatVND } from '../utils.js?v=4.0';
import { getPortfolioBundle, getPortfolioAlternatives, getPortfolioSectors } from '../api.js?v=4.0';

let currentCapital = 20000000;
let currentStyle = 'balanced';
let currentBundleData = null;
let activeSwapSlot = 0;
let activeTargetSector = 'Tất cả';
let cachedSectorsList = [];
let cachedAlternativesMap = {}; // Cache kết quả các ngành khi mở modal để chuyển tab tức thì 0ms
let onSelectStockCallback = null;

function safeSetText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = (text !== undefined && text !== null) ? text : '--';
}

export function initPortfolioBundle(selectStockCb) {
  onSelectStockCallback = selectStockCb;

  // 1. Chuyển đổi chế độ (Mode Switcher)
  const modeSingleBtn = document.getElementById('modeSingleStockBtn');
  const modeBundleBtn = document.getElementById('modePortfolioBundleBtn');

  if (modeSingleBtn && modeBundleBtn) {
    modeSingleBtn.addEventListener('click', () => switchAppMode('single'));
    modeBundleBtn.addEventListener('click', () => switchAppMode('bundle'));
  }

  // 2. Các nút chọn sẵn mức vốn (15tr, 20tr, 25tr, 50tr)
  document.querySelectorAll('.capital-preset-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.capital-preset-btn').forEach(b => {
        b.className = 'capital-preset-btn px-3 py-1.5 rounded-lg transition text-slate-300 hover:text-white';
      });
      btn.className = 'capital-preset-btn px-3 py-1.5 rounded-lg transition bg-blue-600 text-white shadow-sm font-bold active';
      
      const cap = Number(btn.getAttribute('data-capital'));
      if (cap && cap > 0) {
        currentCapital = cap;
        loadBundleData(currentCapital, currentStyle);
      }
    });
  });

  // 3. Nút áp dụng số vốn tự nhập
  const applyCustomBtn = document.getElementById('applyCustomCapitalBtn');
  const customInput = document.getElementById('customCapitalInput');
  if (applyCustomBtn && customInput) {
    applyCustomBtn.addEventListener('click', () => {
      const raw = customInput.value.replace(/\D/g, '');
      const cap = Number(raw);
      if (cap && cap >= 5000000) {
        currentCapital = cap;
        document.querySelectorAll('.capital-preset-btn').forEach(b => {
          b.className = 'capital-preset-btn px-3 py-1.5 rounded-lg transition text-slate-300 hover:text-white';
        });
        loadBundleData(currentCapital, currentStyle);
      } else {
        alert('Vui lòng nhập số vốn tối thiểu từ 5.000.000 đ');
      }
    });

    customInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        applyCustomBtn.click();
      }
    });
  }

  // 4. Các nút chọn khẩu vị đầu tư (Style)
  document.querySelectorAll('.bundle-style-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.bundle-style-btn').forEach(b => {
        b.className = 'bundle-style-btn px-3 py-1 rounded-lg text-slate-400 hover:text-white transition';
      });
      btn.className = 'bundle-style-btn px-3 py-1 rounded-lg text-white bg-blue-600/80 font-bold active';

      const style = btn.getAttribute('data-style') || 'balanced';
      currentStyle = style;
      loadBundleData(currentCapital, currentStyle);
    });
  });

  // 5. Nút đổi mã & đổi ngành ở 2 slot
  const swapSlot1 = document.getElementById('btnSwapSlot1');
  const swapSlot2 = document.getElementById('btnSwapSlot2');
  const slot1SecBtn = document.getElementById('btnSlot1Sector');
  const slot2SecBtn = document.getElementById('btnSlot2Sector');

  if (swapSlot1) swapSlot1.addEventListener('click', () => openSwapModal(0));
  if (swapSlot2) swapSlot2.addEventListener('click', () => openSwapModal(1));
  if (slot1SecBtn) slot1SecBtn.addEventListener('click', () => openSwapModal(0));
  if (slot2SecBtn) slot2SecBtn.addEventListener('click', () => openSwapModal(1));

  // 6. Đóng modal đổi mã
  const closeModalBtn = document.getElementById('closeSwapModalBtn');
  const modal = document.getElementById('swapStockModal');
  if (closeModalBtn && modal) {
    closeModalBtn.addEventListener('click', () => modal.classList.add('hidden'));
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.add('hidden');
    });
  }

  // 7. Tự nhập mã muốn đổi trong modal
  const applyCustomSwapBtn = document.getElementById('applyCustomSwapBtn');
  const customSwapInput = document.getElementById('customSwapInput');
  if (applyCustomSwapBtn && customSwapInput) {
    applyCustomSwapBtn.addEventListener('click', () => {
      const sym = customSwapInput.value.trim().toUpperCase();
      if (!sym) return;
      handleCustomStockSwap(sym);
    });
    customSwapInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') applyCustomSwapBtn.click();
    });
  }

  // 8. Nút xem chi tiết từng mã
  const detailSlot1 = document.getElementById('btnDetailSlot1');
  const detailSlot2 = document.getElementById('btnDetailSlot2');
  if (detailSlot1) {
    detailSlot1.addEventListener('click', () => {
      if (currentBundleData?.slots?.[0]?.symbol && onSelectStockCallback) {
        switchAppMode('single');
        onSelectStockCallback(currentBundleData.slots[0].symbol);
      }
    });
  }
  if (detailSlot2) {
    detailSlot2.addEventListener('click', () => {
      if (currentBundleData?.slots?.[1]?.symbol && onSelectStockCallback) {
        switchAppMode('single');
        onSelectStockCallback(currentBundleData.slots[1].symbol);
      }
    });
  }
}

export function switchAppMode(mode) {
  const modeSingleBtn = document.getElementById('modeSingleStockBtn');
  const modeBundleBtn = document.getElementById('modePortfolioBundleBtn');
  const singleDetail = document.getElementById('singleStockDetailContainer');
  const singleBody = document.getElementById('singleStockBodyContainer');
  const bundleSec = document.getElementById('portfolioBundleSection');

  if (mode === 'bundle') {
    if (modeSingleBtn) {
      modeSingleBtn.className = 'mode-nav-btn px-3.5 py-2 rounded-lg transition text-slate-400 hover:text-white flex items-center gap-1.5 cursor-pointer';
    }
    if (modeBundleBtn) {
      modeBundleBtn.className = 'mode-nav-btn px-3.5 py-2 rounded-lg transition bg-blue-600 text-white shadow-sm flex items-center gap-1.5 active cursor-pointer';
    }

    if (singleDetail) singleDetail.classList.add('hidden');
    if (singleBody) singleBody.classList.add('hidden');
    if (bundleSec) bundleSec.classList.remove('hidden');

    if (!currentBundleData) {
      loadBundleData(currentCapital, currentStyle);
    }
  } else {
    if (modeSingleBtn) {
      modeSingleBtn.className = 'mode-nav-btn px-3.5 py-2 rounded-lg transition bg-blue-600 text-white shadow-sm flex items-center gap-1.5 active cursor-pointer';
    }
    if (modeBundleBtn) {
      modeBundleBtn.className = 'mode-nav-btn px-3.5 py-2 rounded-lg transition text-slate-400 hover:text-white flex items-center gap-1.5 cursor-pointer';
    }

    if (singleDetail) singleDetail.classList.remove('hidden');
    if (singleBody) singleBody.classList.remove('hidden');
    if (bundleSec) bundleSec.classList.add('hidden');
  }
}

async function loadBundleData(capital, style) {
  try {
    const data = await getPortfolioBundle(capital, style);
    currentBundleData = data;
    renderBundleUI(data);
  } catch (err) {
    console.error('Lỗi tải dữ liệu gói danh mục:', err);
  }
}

function renderBundleUI(data) {
  if (!data || !data.slots || data.slots.length < 2) return;

  const cap = data.capital || currentCapital;
  const alloc = data.allocation || {};
  const reg = data.regime || {};
  const slot1 = data.slots[0];
  const slot2 = data.slots[1];

  // Regime badge
  safeSetText('bundleRegimeText', reg.label || 'NEUTRAL');
  safeSetText('bundleAllocRate', reg.allocationRate || 75);

  // Stats bar
  safeSetText('bundleDisplayCapital', formatVND(cap) + ' đ');
  safeSetText('bundleTotalInvested', formatVND(alloc.totalInvested || 0) + ' đ');
  safeSetText('bundleInvestedPct', alloc.totalInvestedPct || 0);
  safeSetText('bundleCashReserve', formatVND(alloc.cashReserve || 0) + ' đ');
  safeSetText('bundleCashPct', alloc.cashReservePct || 0);

  // Progress Bar
  const pct1 = slot1.costPercent || 35;
  const pct2 = slot2.costPercent || 35;
  const pctCash = alloc.cashReservePct || (100 - pct1 - pct2);

  const bar1 = document.getElementById('barSlot1');
  const bar2 = document.getElementById('barSlot2');
  const barCash = document.getElementById('barCash');
  if (bar1) bar1.style.width = `${pct1}%`;
  if (bar2) bar2.style.width = `${pct2}%`;
  if (barCash) barCash.style.width = `${pctCash}%`;

  safeSetText('legendSlot1', `${slot1.symbol} (${pct1}%)`);
  safeSetText('legendSlot2', `${slot2.symbol} (${pct2}%)`);

  // Render Slot 1 Card
  renderSlotCard(1, slot1);

  // Render Slot 2 Card
  renderSlotCard(2, slot2);
}

function renderSlotCard(slotNum, s) {
  safeSetText(`slot${slotNum}Role`, s.role || `Slot ${slotNum}`);
  safeSetText(`slot${slotNum}Sector`, s.sector || 'Doanh nghiệp');
  safeSetText(`slot${slotNum}Symbol`, s.symbol);
  safeSetText(`slot${slotNum}Exchange`, s.exchange || 'HOSE');
  safeSetText(`slot${slotNum}Name`, s.name || s.symbol);
  safeSetText(`slot${slotNum}Price`, formatVND(s.price) + ' đ');

  const chgEl = document.getElementById(`slot${slotNum}Change`);
  if (chgEl) {
    const isUp = (s.change || 0) >= 0;
    chgEl.innerText = `${isUp ? '+' : ''}${formatVND(s.change)} đ (${isUp ? '+' : ''}${s.percentChange}%)`;
    chgEl.className = `text-xs font-bold ${isUp ? 'text-emerald-400' : 'text-rose-400'}`;
  }

  const actionEl = document.getElementById(`slot${slotNum}ActionBadge`);
  if (actionEl) {
    actionEl.innerText = s.action || 'VÙNG GOM AN TOÀN';
    if (s.isExtended || s.actionColor === 'amber' || (s.action && s.action.includes('KHÔNG MUA ĐUỔI'))) {
      actionEl.className = 'text-[11px] font-bold px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800';
    } else if (s.actionColor === 'emerald' || (s.percentChange <= 1.5)) {
      actionEl.className = 'text-[11px] font-bold px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800';
    } else {
      actionEl.className = 'text-[11px] font-bold px-2 py-0.5 rounded bg-blue-950 text-blue-400 border border-blue-800';
    }
  }

  // Khung lời khuyên điểm mua / cảnh báo retest
  const adviceBox = document.getElementById(`slot${slotNum}AdviceBox`);
  const adviceText = document.getElementById(`slot${slotNum}AdviceText`);
  const adviceIcon = document.getElementById(`slot${slotNum}AdviceIcon`);
  if (adviceBox && adviceText) {
    if (s.advice) {
      adviceText.innerText = s.advice;
      adviceBox.classList.remove('hidden');
      if (s.isExtended || s.actionColor === 'amber' || (s.action && s.action.includes('KHÔNG MUA ĐUỔI'))) {
        adviceBox.className = 'mt-3 p-2.5 rounded-xl text-xs flex items-start gap-2 border bg-amber-950/40 text-amber-300 border-amber-800/60';
        if (adviceIcon) adviceIcon.className = 'fa-solid fa-triangle-exclamation mt-0.5 text-sm text-amber-400';
      } else {
        adviceBox.className = 'mt-3 p-2.5 rounded-xl text-xs flex items-start gap-2 border bg-emerald-950/30 text-emerald-300 border-emerald-800/50';
        if (adviceIcon) adviceIcon.className = 'fa-solid fa-circle-check mt-0.5 text-sm text-emerald-400';
      }
    } else {
      adviceBox.classList.add('hidden');
    }
  }

  safeSetText(`slot${slotNum}Quantity`, `${s.quantity} CP`);
  safeSetText(`slot${slotNum}TotalCost`, formatVND(s.totalCost) + ' đ');
  safeSetText(`slot${slotNum}CostPct`, `(${s.costPercent}% tổng vốn)`);
  safeSetText(`slot${slotNum}BuyZone`, s.buyZone || '--');
  safeSetText(`slot${slotNum}StopLoss`, formatVND(s.stopLoss) + ' đ');
  safeSetText(`slot${slotNum}Target1`, formatVND(s.target1) + ' đ');

  // Cập nhật nhãn % Cắt lỗ và Mục tiêu động theo dữ liệu kỹ thuật thực tế
  const slPct = s.stopLossPct !== undefined ? s.stopLossPct : (s.stopLoss && s.price ? Math.round(((s.stopLoss - s.price) / s.price) * 1000) / 10 : -5.0);
  const tgPct = s.target1Pct !== undefined ? s.target1Pct : (s.target1 && s.price ? Math.round(((s.target1 - s.price) / s.price) * 1000) / 10 : 7.0);
  safeSetText(`slot${slotNum}StopLossPct`, `(${slPct > 0 ? '+' : ''}${slPct}%)`);
  safeSetText(`slot${slotNum}Target1Pct`, `(${tgPct > 0 ? '+' : ''}${tgPct}%)`);

  safeSetText(`slot${slotNum}RR`, s.riskReward || '2.0');
}

async function openSwapModal(slotIndex) {
  activeSwapSlot = slotIndex;
  activeTargetSector = 'Tất cả';
  cachedAlternativesMap = {}; // Xóa cache cũ khi mở lượt đổi mới
  const modal = document.getElementById('swapStockModal');
  const listEl = document.getElementById('swapAlternativesList');
  const tabsEl = document.getElementById('swapSectorTabs');
  if (!modal || !listEl || !currentBundleData) return;

  modal.classList.remove('hidden');

  const currentStock = currentBundleData.slots[slotIndex];
  const otherStock = currentBundleData.slots[slotIndex === 0 ? 1 : 0];
  const slotBudget = (currentCapital * (currentBundleData.regime?.allocationRate || 75) / 100) / 2;

  safeSetText('swapModalBudget', formatVND(slotBudget) + ' đ');

  // 1. Tải danh mục ngành & Khả năng mua theo ngân sách
  if (tabsEl) {
    tabsEl.innerHTML = `
      <span class="text-xs text-slate-500 py-1 flex items-center gap-1.5">
        <i class="fa-solid fa-spinner animate-spin"></i> Đang phân tích ngành...
      </span>
    `;
  }

  listEl.innerHTML = `
    <div class="text-center py-8 text-slate-400 text-xs">
      <i class="fa-solid fa-spinner animate-spin text-lg mb-2"></i>
      <p>Đang tải danh sách cổ phiếu từ bảng giá SSI...</p>
    </div>
  `;

  try {
    const secData = await getPortfolioSectors(slotBudget, otherStock?.sector || '');
    cachedSectorsList = secData.sectors || [];
    renderSectorTabs(cachedSectorsList, slotBudget, otherStock?.sector || '');
  } catch (err) {
    console.error('Lỗi tải danh mục ngành:', err);
    if (tabsEl) tabsEl.innerHTML = `<span class="text-xs text-rose-400">Không thể tải danh mục ngành</span>`;
  }

  // 2. Tải danh sách cổ phiếu ban đầu
  await loadAlternativesForSlot(currentStock, otherStock, slotBudget, activeTargetSector);
}

function renderSectorTabs(sectors, slotBudget, otherSector) {
  const tabsEl = document.getElementById('swapSectorTabs');
  const conflictWarn = document.getElementById('swapSectorConflictWarning');
  if (!tabsEl) return;

  tabsEl.innerHTML = sectors.map(sec => {
    const isActive = (sec.name === activeTargetSector);
    const isAvail = sec.isAvailable;
    const isConflict = sec.isExcluded;

    if (!isAvail) {
      const minRequired = Math.ceil((sec.minLotCost || 0) / 1000000);
      return `
        <button type="button" disabled
          class="px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-950/40 text-slate-600 border border-slate-900 whitespace-nowrap cursor-not-allowed opacity-50 flex items-center gap-1 select-none"
          title="Cần ngân sách từ ~${minRequired} triệu để mua được 1 lô 100 cổ phiếu">
          <span>${sec.name}</span>
          <span class="text-[10px] text-slate-600 font-mono">(&gt;${minRequired}tr)</span>
        </button>
      `;
    }

    if (isActive) {
      return `
        <button type="button"
          class="sector-tab-btn px-3 py-1 rounded-lg text-xs font-bold bg-blue-600 text-white whitespace-nowrap shadow-sm cursor-pointer transition flex items-center gap-1.5 border border-blue-500 active"
          data-sector="${sec.name}">
          <span>${sec.name}</span>
          <span class="px-1.5 py-0.2 rounded-full text-[10px] bg-blue-800 text-blue-100 font-mono">${sec.eligibleCount}</span>
          ${isConflict ? '<span class="text-[11px] text-amber-300 ml-0.5" title="Trùng ngành với Slot còn lại">⚠️</span>' : ''}
        </button>
      `;
    }

    return `
      <button type="button"
        class="sector-tab-btn px-3 py-1 rounded-lg text-xs font-semibold bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white whitespace-nowrap border border-slate-800 hover:border-slate-700 cursor-pointer transition flex items-center gap-1.5"
        data-sector="${sec.name}">
        <span>${sec.name}</span>
        <span class="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-800 text-slate-400 font-mono">${sec.eligibleCount}</span>
        ${isConflict ? '<span class="text-[11px] text-amber-400 ml-0.5" title="Trùng ngành với Slot còn lại">⚠️</span>' : ''}
      </button>
    `;
  }).join('');

  // Hiển thị cảnh báo trùng ngành nếu tab đang chọn trùng với slot còn lại
  const currentSecObj = sectors.find(s => s.name === activeTargetSector);
  if (conflictWarn) {
    if (currentSecObj && currentSecObj.isExcluded) {
      conflictWarn.classList.remove('hidden');
    } else {
      conflictWarn.classList.add('hidden');
    }
  }

  // Gắn sự kiện click đổi tab ngành
  tabsEl.querySelectorAll('.sector-tab-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const secName = btn.getAttribute('data-sector');
      if (!secName || secName === activeTargetSector) return;
      activeTargetSector = secName;

      // Re-render tabs để cập nhật trạng thái active
      renderSectorTabs(cachedSectorsList, slotBudget, otherSector);

      // Load lại danh sách mã thuộc ngành được chọn
      const currentStock = currentBundleData.slots[activeSwapSlot];
      const otherStock = currentBundleData.slots[activeSwapSlot === 0 ? 1 : 0];
      await loadAlternativesForSlot(currentStock, otherStock, slotBudget, activeTargetSector);
    });
  });
}

async function loadAlternativesForSlot(currentStock, otherStock, slotBudget, targetSector) {
  const listEl = document.getElementById('swapAlternativesList');
  if (!listEl) return;

  // Nếu ngành này đã được nạp trước đó trong cùng phiên mở modal -> render tức thì 0ms, không cần fetch lại
  if (cachedAlternativesMap[targetSector]) {
    renderAlternativesList(cachedAlternativesMap[targetSector], slotBudget);
    return;
  }

  listEl.innerHTML = `
    <div class="text-center py-8 text-slate-400 text-xs">
      <i class="fa-solid fa-spinner animate-spin text-lg mb-2"></i>
      <p>Đang tải danh sách cổ phiếu ${targetSector !== 'Tất cả' ? `ngành <strong>${targetSector}</strong>` : 'toàn sàn'}...</p>
    </div>
  `;

  try {
    const data = await getPortfolioAlternatives(
      currentStock.symbol,
      currentStock.sector,
      slotBudget,
      otherStock?.sector || '',
      targetSector
    );
    const alts = data.alternatives || [];
    cachedAlternativesMap[targetSector] = alts;
    renderAlternativesList(alts, slotBudget);
  } catch (err) {
    listEl.innerHTML = `
      <div class="p-4 text-center text-xs text-rose-400">
        Không thể tải danh sách thay thế. Vui lòng thử lại.
      </div>
    `;
  }
}

function renderAlternativesList(alts, budget) {
  const listEl = document.getElementById('swapAlternativesList');
  if (!listEl) return;

  if (alts.length === 0) {
    listEl.innerHTML = `
      <div class="p-6 text-center text-xs text-slate-400">
        Không tìm thấy mã nào khác trong ngành này phù hợp với ngân sách lô 100.
      </div>
    `;
    return;
  }

  listEl.innerHTML = alts.map(s => {
    const isUp = (s.percentChange || 0) >= 0;
    const isConflict = s.isConflictWithOtherSlot;
    return `
      <div class="p-3 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between gap-3 hover:border-slate-700 transition">
        <div class="space-y-0.5">
          <div class="flex items-center gap-2">
            <span class="font-bold text-white font-mono text-sm">${s.symbol}</span>
            <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">${s.exchange}</span>
            <span class="text-[10px] px-1.5 py-0.2 rounded bg-slate-900 text-slate-300 border border-slate-800">${s.sector}</span>
            ${s.isSameSector ? '<span class="text-[10px] px-1.5 py-0.2 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">Cùng ngành cũ</span>' : ''}
            ${isConflict ? '<span class="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30" title="Mã này thuộc ngành đang có ở Slot còn lại">⚠️ Trùng ngành Slot còn lại</span>' : ''}
          </div>
          <p class="text-[11px] text-slate-400 line-clamp-1">${s.name}</p>
          <div class="text-[11px] text-slate-300">
            Giá: <strong class="text-white font-mono">${formatVND(s.price)} đ</strong>
            <span class="ml-1.5 font-bold ${isUp ? 'text-emerald-400' : 'text-rose-400'}">${isUp ? '+' : ''}${s.percentChange}%</span>
            <span class="text-slate-500 ml-1.5">|</span>
            <span class="text-slate-400 ml-1.5">Mua tối đa: <strong class="text-blue-400 font-mono">${s.suggestedQty} CP</strong> (~${formatVND(s.totalCost)} đ)</span>
          </div>
        </div>
        <div>
          <button type="button" class="btn-select-alt px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-semibold transition active:scale-95 cursor-pointer whitespace-nowrap"
            data-symbol="${s.symbol}" data-price="${s.price}" data-name="${s.name}" data-sector="${s.sector}" data-exchange="${s.exchange}" data-change="${s.change}" data-percent="${s.percentChange}">
            Chọn mã này
          </button>
        </div>
      </div>
    `;
  }).join('');

  // Gắn sự kiện click chọn mã thay thế
  listEl.querySelectorAll('.btn-select-alt').forEach(btn => {
    btn.addEventListener('click', () => {
      const sym = btn.getAttribute('data-symbol');
      const price = Number(btn.getAttribute('data-price'));
      const name = btn.getAttribute('data-name');
      const sector = btn.getAttribute('data-sector');
      const exchange = btn.getAttribute('data-exchange');
      const change = Number(btn.getAttribute('data-change'));
      const percent = Number(btn.getAttribute('data-percent'));

      applyNewStockToSlot({
        symbol: sym,
        price,
        name,
        sector,
        exchange,
        change,
        percentChange: percent,
      });
    });
  });
}

function handleCustomStockSwap(symbol) {
  // Tìm mã từ bảng giá SSI bằng API tìm kiếm hoặc gán trực tiếp
  fetch(`/api/search?q=${encodeURIComponent(symbol)}`)
    .then(res => res.json())
    .then(items => {
      const match = items.find(i => i.symbol.toUpperCase() === symbol.toUpperCase()) || items[0];
      if (match && match.price > 0) {
        applyNewStockToSlot({
          symbol: match.symbol,
          price: match.price,
          name: match.name,
          sector: 'Thị trường',
          exchange: match.exchange || 'HOSE',
          change: match.change || 0,
          percentChange: match.percentChange || 0,
        });
      } else {
        alert(`Không tìm thấy mã hoặc giá cổ phiếu ${symbol}`);
      }
    })
    .catch(() => alert(`Không thể tra cứu mã ${symbol}`));
}

async function applyNewStockToSlot(stockInfo) {
  if (!currentBundleData || !currentBundleData.slots) return;

  // Đóng modal ngay lập tức để trải nghiệm mượt mà
  const modal = document.getElementById('swapStockModal');
  if (modal) modal.classList.add('hidden');

  const slotBudget = (currentCapital * (currentBundleData.regime?.allocationRate || 75) / 100) / 2;
  const p = stockInfo.price;
  const lots = Math.max(1, Math.floor(slotBudget / (p * 100)));
  const qty = lots * 100;
  const totalCost = qty * p;
  const role = activeSwapSlot === 0 ? 'Trụ Cân Bằng / Nền Tảng' : 'Động Lực Tăng Trưởng / T+';

  let s1 = 0;
  let r1 = 0;
  let r2 = 0;
  let atr = p * 0.02;
  let distToS1 = 0;
  let isExtended = false;
  let buyZone = '';
  let action = (stockInfo.percentChange || 0) <= 1.5 ? 'VÙNG GOM AN TOÀN' : 'CANH RUNG LẮC MUA';
  let actionColor = (stockInfo.percentChange || 0) <= 1.5 ? 'emerald' : 'blue';
  let advice = 'Giải ngân theo vùng gom khuyến nghị.';

  // Truy vấn kỹ thuật thực tế từ API /api/stock để lấy Fractal Pivot S1/R1 và ATR
  try {
    const res = await fetch(`/api/stock?ticker=${encodeURIComponent(stockInfo.symbol)}`);
    if (res.ok) {
      const detail = await res.json();
      const tech = detail.technicals || {};
      s1 = Number(tech.support) || 0;
      r1 = Number(tech.resistance) || 0;
      r2 = Number(tech.resistance2) || 0;
      atr = Number(tech.atr14) || (p * 0.02);
      distToS1 = s1 > 0 ? Math.round(((p - s1) / s1) * 1000) / 10 : 0;
      isExtended = distToS1 > 4.0;

      if (isExtended) {
        const pbMin = Math.round(Math.max(s1, p - 0.5 * (p - s1)) / 100) * 100;
        const pbMax = Math.round(Math.max(s1, p - 0.25 * (p - s1)) / 100) * 100;
        buyZone = `${formatVND(pbMin)} - ${formatVND(pbMax)} đ (Vùng Pullback)`;
        action = '⏳ CHỜ RETEST / KHÔNG MUA ĐUỔI';
        actionColor = 'amber';
        advice = `Giá đã tăng cách nền ${distToS1}%, không mua đuổi đỉnh ngắn hạn. Đặt lệnh chờ tại vùng Pullback.`;
      } else {
        const entryMax = Math.round(Math.min(s1 + 0.4 * atr, p * 1.005) / 100) * 100;
        buyZone = `${formatVND(s1 || Math.round(p * 0.985 / 100) * 100)} - ${formatVND(entryMax || Math.round(p * 1.01 / 100) * 100)} đ`;
        action = 'VÙNG GOM AN TOÀN';
        actionColor = 'emerald';
        advice = `Giá đang nằm trong vùng nền tích lũy an toàn (cách nền ${distToS1}%).`;
      }
    }
  } catch (e) {
    console.warn('Không thể nạp kỹ thuật chuyên sâu cho mã đổi:', e);
  }

  // Nếu không nạp được S1/R1 từ API, ước tính linh hoạt theo biên độ sàn thực tế
  const exch = stockInfo.exchange || 'HOSE';
  const band = exch === 'HOSE' ? 0.07 : (exch === 'HNX' ? 0.10 : 0.15);

  const stopLoss = s1 > 0 ? Math.round(Math.min(s1 - 0.5 * atr, p - 1.5 * atr) / 100) * 100 : Math.round(p * (1 - band * 0.65) / 100) * 100;
  const target1 = r1 > 0 ? Math.round(r1 / 100) * 100 : Math.round(p * (1 + band * 0.95) / 100) * 100;
  const target2 = r2 > 0 ? Math.round(r2 / 100) * 100 : Math.round(p * (1 + band * 1.8) / 100) * 100;

  const stopLossPct = Math.round(((stopLoss - p) / p) * 1000) / 10;
  const target1Pct = Math.round(((target1 - p) / p) * 1000) / 10;
  const target2Pct = Math.round(((target2 - p) / p) * 1000) / 10;
  const downside = Math.max(1, p - stopLoss);
  const upside = Math.max(1, target1 - p);
  const riskReward = Math.round((upside / downside) * 10) / 10;

  if (!buyZone) {
    const bzMin = s1 > 0 ? s1 : Math.round((p - atr * 0.8) / 100) * 100;
    const bzMax = Math.round(Math.min(p * 1.005, bzMin + atr * 0.4) / 100) * 100;
    buyZone = `${formatVND(bzMin)} - ${formatVND(bzMax)} đ`;
  }

  const updatedSlot = {
    symbol: stockInfo.symbol,
    name: stockInfo.name,
    exchange: exch,
    sector: stockInfo.sector || 'Doanh nghiệp',
    price: p,
    change: stockInfo.change || 0,
    percentChange: stockInfo.percentChange || 0,
    role,
    quantity: qty,
    totalCost,
    costPercent: Math.round((totalCost / currentCapital) * 1000) / 10,
    buyZone,
    stopLoss,
    stopLossPct,
    target1,
    target1Pct,
    target2,
    target2Pct,
    riskReward,
    action,
    actionColor,
    advice,
    distToS1,
    isExtended,
  };

  currentBundleData.slots[activeSwapSlot] = updatedSlot;

  // Tính lại tổng phân bổ
  const slot1 = currentBundleData.slots[0];
  const slot2 = currentBundleData.slots[1];
  const totalInvested = slot1.totalCost + slot2.totalCost;
  const cashReserve = Math.max(0, currentCapital - totalInvested);

  currentBundleData.allocation = {
    totalInvested,
    totalInvestedPct: Math.round((totalInvested / currentCapital) * 1000) / 10,
    cashReserve,
    cashReservePct: Math.round((cashReserve / currentCapital) * 1000) / 10,
  };

  renderBundleUI(currentBundleData);
}
