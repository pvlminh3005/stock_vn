/**
 * Stock RT - User Portfolio Tracker Module
 * Quản lý giao diện sổ lệnh cá nhân, tính toán Lời/Lỗ realtime,
 * quản lý tổng NAV, bộ lọc đa năng và các thao tác giao dịch Mua/Bán.
 * Sử dụng Event Delegation để đảm bảo hoạt động 100% trong mọi điều kiện nạp DOM.
 */

import {
  getUserPortfolio,
  addUserTrade,
  deleteUserTrade,
  resetUserPortfolio,
  saveUserPortfolioSettings,
} from '../api.js?v=5.0';
import { switchAppMode } from './portfolioBundle.js?v=5.0';
import {
  formatNumber,
  formatVND,
  formatPriceVND,
  formatStockPrice,
  formatLiveVolumeInput,
  formatLivePriceInput,
  formatPriceInput,
  parsePriceInputToNumber,
} from '../utils.js?v=6.0';

let _portfolioData = {
  summary: {
    total_nav: 0,
    total_buy_cost: 0,
    current_market_val: 0,
    unrealized_pnl: 0,
    unrealized_pnl_pct: 0,
    realized_pnl: 0,
    total_pnl: 0,
    total_pnl_pct: 0,
    available_nav: 0,
    holdings_count: 0,
    closed_count: 0,
    total_trades_count: 0,
  },
  holdings: [],
  trades: [],
};

let _activeView = 'HOLDINGS'; // 'HOLDINGS' (Gom nhóm) | 'TRADES' (Nhật ký từng lệnh)
let _currentFilter = 'ALL';
let _searchTerm = '';
let _initialized = false;

// Hàm định dạng tiền VND kèm hậu tố đ chuẩn giao diện danh mục (500,000,000 đ)
function formatPortfolioVND(val) {
  if (val === undefined || val === null || isNaN(val)) return '0 đ';
  return `${formatVND(val)} đ`;
}

/**
 * Toggle trạng thái Loại Lệnh: Mua (Xanh) vs Bán (Đỏ)
 */
function setOrderType(type) {
  const tradeTypeBuyBtn = document.getElementById('tradeTypeBuyBtn');
  const tradeTypeSellBtn = document.getElementById('tradeTypeSellBtn');
  const tradeTypeHidden = document.getElementById('tradeTypeHidden');
  if (!tradeTypeHidden) return;

  if (type === 'BUY') {
    tradeTypeHidden.value = 'BUY';
    if (tradeTypeBuyBtn) {
      tradeTypeBuyBtn.className = 'flex-1 py-1 rounded-md text-xs font-bold transition cursor-pointer bg-emerald-600 text-white shadow-sm flex items-center justify-center gap-1 active';
    }
    if (tradeTypeSellBtn) {
      tradeTypeSellBtn.className = 'flex-1 py-1 rounded-md text-xs font-bold transition cursor-pointer text-slate-400 hover:text-white flex items-center justify-center gap-1';
    }
  } else {
    tradeTypeHidden.value = 'SELL';
    if (tradeTypeSellBtn) {
      tradeTypeSellBtn.className = 'flex-1 py-1 rounded-md text-xs font-bold transition cursor-pointer bg-rose-600 text-white shadow-sm flex items-center justify-center gap-1 active';
    }
    if (tradeTypeBuyBtn) {
      tradeTypeBuyBtn.className = 'flex-1 py-1 rounded-md text-xs font-bold transition cursor-pointer text-slate-400 hover:text-white flex items-center justify-center gap-1';
    }
  }
}

/**
 * Điền tự động thông tin từ một lệnh đã chọn lên form nhập
 * (Giữ ngày hiện tại, note để trống để tiện bổ sung lệnh Mua/Bán mới)
 */
function fillTradeForm(trade) {
  if (!trade) return;

  const symInput = document.getElementById('tradeSymbolInput');
  const volInput = document.getElementById('tradeVolumeInput');
  const priceInput = document.getElementById('tradePriceInput');
  const noteInput = document.getElementById('tradeNoteInput');
  const dateInput = document.getElementById('tradeDateInput');
  const form = document.getElementById('portfolioTradeForm');

  if (symInput) symInput.value = (trade.symbol || '').toUpperCase();
  if (volInput) volInput.value = formatNumber(trade.volume);
  if (priceInput) priceInput.value = formatPriceInput(trade.price);

  // Note để trống theo yêu cầu của user
  if (noteInput) noteInput.value = '';

  // Ngày thì vẫn giữ hiện tại lúc bấm nút edit
  if (dateInput) {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    dateInput.value = `${year}-${month}-${day}`;
  }

  // Loại Lệnh (BUY / SELL)
  setOrderType((trade.order_type || 'BUY').toUpperCase());

  // Cuộn mượt tới form và highlight nhẹ viền form
  if (form) {
    form.scrollIntoView({ behavior: 'smooth', block: 'center' });
    form.classList.add('ring-2', 'ring-emerald-500/80', 'transition-all');
    setTimeout(() => {
      form.classList.remove('ring-2', 'ring-emerald-500/80');
    }, 1500);
  }

  if (volInput) {
    volInput.focus();
    volInput.select();
  }
}

/**
 * Khởi tạo toàn bộ module Portfolio Tracker (Event Delegation)
 */
export function initUserPortfolioModule(callbacks = {}) {
  if (_initialized) return;
  _initialized = true;

  // 1. Lắng nghe kích hoạt chế độ User Portfolio
  window.addEventListener('userPortfolioActivated', () => {
    initDatePickerDefault();
    loadPortfolioData(callbacks);
  });

  // Khi các component load xong (nếu chạy fallback)
  window.addEventListener('componentsLoaded', () => {
    initDatePickerDefault();
    loadPortfolioData(callbacks);
  });

  // 2. Event Delegation cho các Click Actions
  document.addEventListener('click', async (e) => {
    const target = e.target;
    if (!target) return;

    // A. Nút chuyển Tab Sổ Lệnh
    const modeBtn = target.closest('#modeUserPortfolioBtn');
    if (modeBtn) {
      switchAppMode('user-portfolio');
      return;
    }

    // A1. Nút chuyển View: Gom nhóm (Holdings) vs Nhật ký (Trades)
    const viewHoldingsBtn = target.closest('#portfolioViewHoldingsBtn');
    if (viewHoldingsBtn) {
      switchPortfolioView('HOLDINGS');
      return;
    }
    const viewTradesBtn = target.closest('#portfolioViewTradesBtn');
    if (viewTradesBtn) {
      switchPortfolioView('TRADES');
      return;
    }

    // B. Nút Toggle Loại Lệnh Mua / Bán
    const buyBtn = target.closest('#tradeTypeBuyBtn');
    if (buyBtn) {
      setOrderType('BUY');
      return;
    }
    const sellBtn = target.closest('#tradeTypeSellBtn');
    if (sellBtn) {
      setOrderType('SELL');
      return;
    }

    // C. Nút Lưu Tổng NAV
    const saveNavBtn = target.closest('#saveNavSettingBtn');
    if (saveNavBtn) {
      const navInput = document.getElementById('userPortfolioNavInput');
      if (!navInput) return;
      const cleanVal = navInput.value.replace(/\D/g, '');
      const numVal = parseFloat(cleanVal);
      if (isNaN(numVal) || numVal < 0) {
        return alert('Vui lòng nhập số tiền Tổng NAV hợp lệ');
      }
      try {
        saveNavBtn.disabled = true;
        saveNavBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-1"></i> Đang lưu...';
        await saveUserPortfolioSettings({ total_nav: numVal });
        // Clear ô input sau khi lưu thành công, đặt placeholder là giá trị đã lưu
        navInput.value = '';
        navInput.placeholder = formatVND(numVal);
        await loadPortfolioData(callbacks);
        saveNavBtn.innerHTML = '<i class="fa-solid fa-circle-check mr-1 text-emerald-300"></i> Đã Lưu!';
        setTimeout(() => {
          saveNavBtn.disabled = false;
          saveNavBtn.innerHTML = '<i class="fa-solid fa-check mr-1"></i> Lưu NAV';
        }, 1500);
      } catch (err) {
        alert('Lỗi: ' + (err.message || 'Không thể lưu Tổng NAV'));
        saveNavBtn.disabled = false;
        saveNavBtn.innerHTML = '<i class="fa-solid fa-check mr-1"></i> Lưu NAV';
      }
      return;
    }

    // D. Nút Filter Chips (Giữ cố định font-semibold & kích thước để chống nhích layout)
    const filterBtn = target.closest('.portfolio-filter-btn');
    if (filterBtn) {
      const inactiveClass = 'portfolio-filter-btn min-h-[36px] sm:min-h-0 px-2.5 py-1 rounded-lg border border-slate-800 bg-slate-950 text-slate-400 hover:text-white hover:border-slate-700 font-semibold cursor-pointer whitespace-nowrap transition-colors';
      const activeClass = 'portfolio-filter-btn min-h-[36px] sm:min-h-0 px-2.5 py-1 rounded-lg border border-emerald-500/50 bg-emerald-600 text-white font-semibold cursor-pointer active whitespace-nowrap shadow-sm transition-colors';

      document.querySelectorAll('.portfolio-filter-btn').forEach(b => {
        b.className = inactiveClass;
      });
      filterBtn.className = activeClass;
      _currentFilter = filterBtn.getAttribute('data-filter') || 'ALL';
      renderPortfolioTable(callbacks);
      return;
    }

    // E. Nút Refresh Làm Mới
    const refreshBtn = target.closest('#refreshPortfolioBtn');
    if (refreshBtn) {
      loadPortfolioData(callbacks);
      return;
    }

    // F. Nút Reset (Xóa Tổng)
    const resetBtn = target.closest('#resetPortfolioBtn');
    if (resetBtn) {
      const confirmReset = window.confirm(
        '⚠️ BẠN CÓ CHẮC CHẮN MUỐN XÓA TOÀN BỘ SỔ LỆNH?\n\nTất cả lịch sử Mua/Bán sẽ bị xóa trắng hoàn toàn. Hành động này không thể khôi phục.'
      );
      if (!confirmReset) return;
      try {
        resetBtn.disabled = true;
        resetBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang xóa...';
        await resetUserPortfolio();
        await loadPortfolioData(callbacks);
      } catch (err) {
        alert('Lỗi: ' + (err.message || 'Không thể reset danh mục'));
      } finally {
        resetBtn.disabled = false;
        resetBtn.innerHTML = '<i class="fa-solid fa-trash-can mr-1"></i> Xóa Tổng';
      }
      return;
    }

    // G. Nút Xóa từng giao dịch
    const deleteBtn = target.closest('.delete-trade-btn');
    if (deleteBtn) {
      const id = deleteBtn.getAttribute('data-id');
      if (!id) return;
      if (!window.confirm('Bạn có chắc chắn muốn xóa giao dịch này khỏi sổ lệnh?')) return;
      try {
        await deleteUserTrade(id);
        await loadPortfolioData(callbacks);
      } catch (err) {
        alert('Lỗi xóa giao dịch: ' + (err.message || 'Thao tác thất bại'));
      }
      return;
    }

    // G2. Nút Bút chì (Edit / Nạp thông tin lệnh lên form nhập)
    const editBtn = target.closest('.edit-trade-btn');
    if (editBtn) {
      const id = editBtn.getAttribute('data-id');
      const trades = _portfolioData.trades || [];
      const trade = trades.find(t => String(t.id) === String(id));
      if (trade) {
        fillTradeForm(trade);
      }
      return;
    }

    // H. Nút Xem chi tiết mã (chuyển sang phân tích Single Stock)
    const viewBtn = target.closest('.view-stock-btn');
    if (viewBtn) {
      const sym = viewBtn.getAttribute('data-symbol');
      if (!sym) return;
      switchAppMode('single');
      const tickerInput = document.getElementById('tickerInput');
      const searchBtn = document.getElementById('searchBtn');
      if (tickerInput) tickerInput.value = sym;
      if (searchBtn) searchBtn.click();
      return;
    }
  });

  // 3. Event Delegation cho Form Submit
  document.addEventListener('submit', async (e) => {
    const form = e.target;
    if (!form || form.id !== 'portfolioTradeForm') return;
    e.preventDefault();

    const symInput = document.getElementById('tradeSymbolInput');
    const volInput = document.getElementById('tradeVolumeInput');
    const priceInput = document.getElementById('tradePriceInput');
    const noteInput = document.getElementById('tradeNoteInput');
    const dateInput = document.getElementById('tradeDateInput');
    const typeInput = document.getElementById('tradeTypeHidden');
    const addBtn = document.getElementById('addTradeBtn');

    if (!symInput || !volInput || !priceInput) return;

    const symbol = symInput.value.trim().toUpperCase();
    const rawVol = volInput.value.replace(/\D/g, '');
    const volume = parseInt(rawVol, 10);
    const price = parsePriceInputToNumber(priceInput.value);
    const tradeDate = dateInput ? dateInput.value : '';
    const orderType = typeInput ? typeInput.value : 'BUY';
    const note = noteInput ? noteInput.value.trim() : '';

    if (!symbol) return alert('Vui lòng nhập mã cổ phiếu');
    if (!volume || volume <= 0) return alert('Vui lòng nhập khối lượng lớn hơn 0');
    if (!price || price <= 0) return alert('Vui lòng nhập giá lớn hơn 0');

    try {
      if (addBtn) {
        addBtn.disabled = true;
        addBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Đang lưu...';
      }
      await addUserTrade({
        symbol,
        volume,
        price,
        trade_date: tradeDate,
        order_type: orderType,
        note,
      });

      // Clear toàn bộ form sau khi lưu thành công
      form.reset();
      symInput.value = '';
      volInput.value = '';
      priceInput.value = '';
      if (noteInput) noteInput.value = '';
      if (dateInput) {
        dateInput.value = new Date().toISOString().split('T')[0];
      }
      setOrderType('BUY');
      symInput.focus();

      await loadPortfolioData(callbacks);

      if (addBtn) {
        addBtn.innerHTML = '<i class="fa-solid fa-circle-check text-emerald-300"></i> Đã Ghi Sổ!';
        setTimeout(() => {
          addBtn.disabled = false;
          addBtn.innerHTML = '<i class="fa-solid fa-plus"></i> <span>Ghi Sổ Lệnh</span>';
        }, 1200);
      }
    } catch (err) {
      alert('Lỗi: ' + (err.message || 'Không thể thêm giao dịch'));
      if (addBtn) {
        addBtn.disabled = false;
        addBtn.innerHTML = '<i class="fa-solid fa-plus"></i> <span>Ghi Sổ Lệnh</span>';
      }
    }
  });

  // 4. Tìm kiếm nhanh & Tự động format cho các ô input khi typing
  document.addEventListener('input', (e) => {
    if (e.target && e.target.id === 'portfolioSearchInput') {
      _searchTerm = e.target.value.trim().toUpperCase();
      renderPortfolioTable(callbacks);
    } else if (e.target && e.target.id === 'userPortfolioNavInput') {
      formatLiveVolumeInput(e.target);
    } else if (e.target && e.target.id === 'tradeVolumeInput') {
      formatLiveVolumeInput(e.target);
    } else if (e.target && e.target.id === 'tradePriceInput') {
      formatLivePriceInput(e.target);
    }
  });

  // Tự động chuẩn hóa Giá khớp dạng 14,85 khi rời ô input (focusout)
  document.addEventListener('focusout', (e) => {
    if (e.target && e.target.id === 'tradePriceInput') {
      if (e.target.value && e.target.value.trim()) {
        e.target.value = formatPriceInput(e.target.value);
      }
    }
  });

  // Hỗ trợ phím Enter khi nhập Tổng NAV
  document.addEventListener('keydown', (e) => {
    if (e.target && e.target.id === 'userPortfolioNavInput' && e.key === 'Enter') {
      e.preventDefault();
      const saveNavBtn = document.getElementById('saveNavSettingBtn');
      if (saveNavBtn) saveNavBtn.click();
    }
  });

  // Ban đầu nạp date picker và dữ liệu
  initDatePickerDefault();
  loadPortfolioData(callbacks);
}

function initDatePickerDefault() {
  const tradeDateInput = document.getElementById('tradeDateInput');
  if (tradeDateInput && !tradeDateInput.value) {
    const todayStr = new Date().toISOString().split('T')[0];
    tradeDateInput.value = todayStr;
    tradeDateInput.max = todayStr;
  }
}

function switchPortfolioView(view) {
  _activeView = view;
  const holdingsBtn = document.getElementById('portfolioViewHoldingsBtn');
  const tradesBtn = document.getElementById('portfolioViewTradesBtn');
  const holdingsContainer = document.getElementById('portfolioHoldingsContainer');
  const tradesContainer = document.getElementById('portfolioTradesContainer');

  if (view === 'HOLDINGS') {
    if (holdingsBtn) {
      holdingsBtn.className = 'portfolio-view-tab-btn min-h-[38px] px-3.5 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 cursor-pointer bg-emerald-600 text-white shadow-md active whitespace-nowrap';
    }
    if (tradesBtn) {
      tradesBtn.className = 'portfolio-view-tab-btn min-h-[38px] px-3.5 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 cursor-pointer text-slate-400 hover:text-white whitespace-nowrap';
    }
    if (holdingsContainer) holdingsContainer.classList.remove('hidden');
    if (tradesContainer) tradesContainer.classList.add('hidden');
  } else {
    if (tradesBtn) {
      tradesBtn.className = 'portfolio-view-tab-btn min-h-[38px] px-3.5 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 cursor-pointer bg-emerald-600 text-white shadow-md active whitespace-nowrap';
    }
    if (holdingsBtn) {
      holdingsBtn.className = 'portfolio-view-tab-btn min-h-[38px] px-3.5 py-1.5 rounded-lg text-xs font-bold transition flex items-center gap-1.5 cursor-pointer text-slate-400 hover:text-white whitespace-nowrap';
    }
    if (tradesContainer) tradesContainer.classList.remove('hidden');
    if (holdingsContainer) holdingsContainer.classList.add('hidden');
  }
}

/**
 * Tải dữ liệu danh mục từ backend
 */
export async function loadPortfolioData(callbacks = {}) {
  try {
    const data = await getUserPortfolio();
    if (data && data.success) {
      _portfolioData = data;
      updateSummaryCards(data.summary);
      renderHoldingsTable(callbacks);
      renderPortfolioTable(callbacks);
    }
  } catch (err) {
    console.warn('Lỗi nạp dữ liệu sổ lệnh:', err);
  }
}

/**
 * Cập nhật các Box Thống Kê Tổng Quan
 */
function updateSummaryCards(summary) {
  if (!summary) return;

  const navInput = document.getElementById('userPortfolioNavInput');
  const statTotalNav = document.getElementById('statTotalNav');
  const statTotalInvested = document.getElementById('statTotalInvested');
  const statInvestedRatio = document.getElementById('statInvestedRatio');
  const statAvailableNav = document.getElementById('statAvailableNav');
  const statAvailableRatio = document.getElementById('statAvailableRatio');
  const statRealizedPnl = document.getElementById('statRealizedPnl');
  const statTotalPnl = document.getElementById('statTotalPnl');
  const statPnlIcon = document.getElementById('statPnlIcon');

  const totalNav = summary.total_nav || 0;
  const buyCost = summary.total_buy_cost || 0;
  const availNav = summary.available_nav || 0;
  const realizedPnl = summary.realized_pnl || 0;
  const totalPnl = summary.total_pnl || 0;
  const totalPnlPct = summary.total_pnl_pct || 0;

  if (navInput && totalNav > 0) {
    navInput.placeholder = formatVND(totalNav);
  }

  if (statTotalNav) statTotalNav.textContent = formatPortfolioVND(totalNav);
  if (statTotalInvested) statTotalInvested.textContent = formatPortfolioVND(buyCost);

  if (statInvestedRatio) {
    const ratio = totalNav > 0 ? ((buyCost / totalNav) * 100).toFixed(1) : '0.0';
    statInvestedRatio.textContent = `Chiếm ${ratio}% NAV (${summary.holdings_count || 0} mã)`;
  }

  if (statAvailableNav) statAvailableNav.textContent = formatPortfolioVND(availNav);
  if (statAvailableRatio) {
    const availRatio = totalNav > 0 ? ((availNav / totalNav) * 100).toFixed(1) : '0.0';
    statAvailableRatio.textContent = `Tiền mặt khả dụng (${availRatio}% NAV)`;
  }

  // Realized PnL Card
  if (statRealizedPnl) {
    const isRealizedProfit = realizedPnl > 0;
    const isRealizedLoss = realizedPnl < 0;
    const signR = isRealizedProfit ? '+' : '';
    statRealizedPnl.className = `text-base sm:text-lg font-black font-mono ${isRealizedProfit ? 'text-emerald-400' : isRealizedLoss ? 'text-rose-400' : 'text-slate-300'
      }`;
    statRealizedPnl.textContent = `${signR}${formatPortfolioVND(realizedPnl)}`;
  }

  // Total P&L styling
  if (statTotalPnl) {
    const isProfit = totalPnl > 0;
    const isLoss = totalPnl < 0;
    const sign = isProfit ? '+' : '';

    statTotalPnl.className = `text-base sm:text-lg font-black font-mono ${isProfit ? 'text-emerald-400' : isLoss ? 'text-rose-400' : 'text-slate-300'
      }`;
    statTotalPnl.innerHTML = `${sign}${formatPortfolioVND(totalPnl)} <span class="text-xs font-semibold ml-1">(${sign}${totalPnlPct.toFixed(2)}%)</span>`;

    if (statPnlIcon) {
      statPnlIcon.className = `fa-solid ${isProfit ? 'fa-arrow-trend-up text-emerald-400' : isLoss ? 'fa-arrow-trend-down text-rose-400' : 'fa-chart-line text-slate-500'
        }`;
    }
  }

  // Cập nhật số lượng trên các nút Filter & Badges Tab
  const holdings = _portfolioData.holdings || [];
  const trades = _portfolioData.trades || [];

  const holdingsTabBadge = document.getElementById('holdingsTabBadge');
  const tradesTabBadge = document.getElementById('tradesTabBadge');
  if (holdingsTabBadge) holdingsTabBadge.textContent = summary.holdings_count || holdings.filter(h => h.holding_volume > 0).length;
  if (tradesTabBadge) tradesTabBadge.textContent = trades.length;

  const countAll = document.getElementById('filterCountAll');
  const countBuy = document.getElementById('filterCountBuy');
  const countSell = document.getElementById('filterCountSell');
  const countProfit = document.getElementById('filterCountProfit');
  const countLoss = document.getElementById('filterCountLoss');

  if (countAll) countAll.textContent = holdings.length;
  if (countBuy) countBuy.textContent = holdings.filter(h => h.holding_volume > 0).length;
  if (countSell) countSell.textContent = holdings.filter(h => h.holding_volume === 0).length;
  if (countProfit) countProfit.textContent = holdings.filter(h => h.total_pnl > 0).length;
  if (countLoss) countLoss.textContent = holdings.filter(h => h.total_pnl < 0).length;
}

/**
 * Render bảng danh mục vị thế gom nhóm (Holdings View)
 */
function renderHoldingsTable(callbacks = {}) {
  const tbody = document.getElementById('portfolioHoldingsTableBody');
  if (!tbody) return;

  const holdings = _portfolioData.holdings || [];

  let filtered = holdings.filter(h => {
    if (_searchTerm && !h.symbol.includes(_searchTerm)) return false;
    if (_currentFilter === 'BUY') return h.holding_volume > 0;
    if (_currentFilter === 'SELL') return h.holding_volume === 0;
    if (_currentFilter === 'PROFIT') return h.total_pnl > 0;
    if (_currentFilter === 'LOSS') return h.total_pnl < 0;
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="11" class="py-8 text-center text-slate-500 font-sans">
          <i class="fa-solid fa-inbox text-2xl mb-2 block text-slate-600"></i>
          Không có vị thế cổ phiếu nào khớp với bộ lọc hiện tại.
        </td>
      </tr>
    `;
    return;
  }

  let html = '';
  filtered.forEach(h => {
    const isHolding = h.holding_volume > 0;
    const isUnrealizedProfit = h.unrealized_pnl > 0;
    const isUnrealizedLoss = h.unrealized_pnl < 0;
    const signU = isUnrealizedProfit ? '+' : '';
    const colorU = isHolding ? (isUnrealizedProfit ? 'text-emerald-400' : isUnrealizedLoss ? 'text-rose-400' : 'text-slate-300') : 'text-slate-500';

    const isRealizedProfit = h.realized_pnl > 0;
    const isRealizedLoss = h.realized_pnl < 0;
    const signR = isRealizedProfit ? '+' : '';
    const colorR = isRealizedProfit ? 'text-emerald-400' : isRealizedLoss ? 'text-rose-400' : 'text-slate-500';

    const isTotalProfit = h.total_pnl > 0;
    const isTotalLoss = h.total_pnl < 0;
    const signT = isTotalProfit ? '+' : '';
    const colorT = isTotalProfit ? 'text-emerald-400' : isTotalLoss ? 'text-rose-400' : 'text-slate-300';

    const changeSign = h.change_pct > 0 ? '+' : '';
    const changeColor = h.change_pct > 0 ? 'text-emerald-400' : h.change_pct < 0 ? 'text-rose-400' : 'text-amber-300';

    html += `
      <tr class="hover:bg-slate-900/80 transition">
        <td class="py-2.5 px-3 font-bold sticky-col-first-cell bg-slate-950/90">
          <div class="flex items-center gap-1.5">
            <button type="button" class="view-stock-btn text-white hover:text-blue-400 transition cursor-pointer underline decoration-dotted font-mono text-sm" data-symbol="${h.symbol}">
              ${h.symbol}
            </button>
            <span class="text-[9px] px-1 py-0.2 rounded bg-slate-800 text-slate-400 font-mono">${h.exchange || 'HOSE'}</span>
          </div>
        </td>
        <td class="py-2.5 px-3">
          <span class="text-[11px] text-slate-300 truncate max-w-[130px] block font-sans">${h.sector || 'Thị trường chung'}</span>
        </td>
        <td class="py-2.5 px-3 text-right font-bold text-slate-100 font-mono">
          ${formatNumber(h.holding_volume)}
          ${!isHolding ? '<span class="text-[9px] text-slate-500 ml-1 block font-sans">Đã đóng</span>' : ''}
        </td>
        <td class="py-2.5 px-3 text-right font-mono text-amber-300 font-semibold">
          ${formatNumber(h.avg_price)} đ
        </td>
        <td class="py-2.5 px-3 text-right font-mono font-bold">
          <div class="text-white">${formatNumber(h.current_price)} đ</div>
          <div class="text-[10px] ${changeColor}">(${changeSign}${h.change_pct}%)</div>
        </td>
        <td class="py-2.5 px-3 text-right text-slate-200 font-mono">
          ${formatPortfolioVND(h.current_value)}
        </td>
        <td class="py-2.5 px-3 text-right font-bold font-mono ${colorU}">
          ${isHolding
        ? `<div>${signU}${formatPortfolioVND(h.unrealized_pnl)}</div>
                 <div class="text-[10px]">(${signU}${h.unrealized_pnl_pct.toFixed(2)}%)</div>`
        : `<span class="text-slate-600 text-[11px] font-sans">-</span>`
      }
        </td>
        <td class="py-2.5 px-3 text-right font-bold font-mono ${colorR}">
          ${h.realized_pnl !== 0 ? `${signR}${formatPortfolioVND(h.realized_pnl)}` : '<span class="text-slate-600 text-[11px] font-sans">0 đ</span>'}
        </td>
        <td class="py-2.5 px-3 text-right font-black font-mono ${colorT} bg-slate-900/30">
          <div>${signT}${formatPortfolioVND(h.total_pnl)}</div>
        </td>
        <td class="py-2.5 px-3 text-right font-mono text-slate-300">
          <span class="px-1.5 py-0.5 rounded bg-slate-800/80 text-[11px] font-semibold">${h.weight_pct}%</span>
        </td>
        <td class="py-2.5 px-3 text-center">
          <button type="button" class="view-stock-btn px-2 py-1 rounded bg-blue-600/20 hover:bg-blue-600/40 text-blue-400 text-[10px] font-bold transition cursor-pointer" data-symbol="${h.symbol}" title="Phân tích mã ${h.symbol}">
            <i class="fa-solid fa-chart-line mr-0.5"></i> Soi Kỹ Thuật
          </button>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}

/**
 * Render bảng danh sách giao dịch (Trades View)
 */
function renderPortfolioTable(callbacks = {}) {
  const tbody = document.getElementById('portfolioTableBody');
  if (!tbody) return;

  const trades = _portfolioData.trades || [];

  let filtered = trades.filter(t => {
    if (_searchTerm && !t.symbol.includes(_searchTerm)) return false;
    if (_currentFilter === 'BUY') return t.order_type === 'BUY';
    if (_currentFilter === 'SELL') return t.order_type === 'SELL';
    if (_currentFilter === 'PROFIT') return t.order_type === 'BUY' && t.pnl_val > 0;
    if (_currentFilter === 'LOSS') return t.order_type === 'BUY' && t.pnl_val < 0;
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="10" class="py-8 text-center text-slate-500 font-sans">
          <i class="fa-solid fa-inbox text-2xl mb-2 block text-slate-600"></i>
          Không có giao dịch nào khớp với bộ lọc hiện tại.
        </td>
      </tr>
    `;
    return;
  }

  let html = '';
  filtered.forEach(t => {
    const isBuy = t.order_type === 'BUY';
    const isProfit = t.pnl_val > 0;
    const isLoss = t.pnl_val < 0;
    const pnlSign = isProfit ? '+' : '';
    const pnlColor = isBuy ? (isProfit ? 'text-emerald-400' : isLoss ? 'text-rose-400' : 'text-slate-300') : 'text-slate-500';

    const changeSign = t.change_pct > 0 ? '+' : '';
    const changeColor = t.change_pct > 0 ? 'text-emerald-400' : t.change_pct < 0 ? 'text-rose-400' : 'text-amber-300';

    html += `
      <tr class="hover:bg-slate-900/80 transition">
        <td class="py-2.5 px-3 font-bold sticky-col-first-cell bg-slate-950/90">
          <div class="flex items-center gap-1.5">
            <button type="button" class="view-stock-btn text-white hover:text-blue-400 transition cursor-pointer underline decoration-dotted font-mono" data-symbol="${t.symbol}">
              ${t.symbol}
            </button>
            <span class="text-[9px] px-1 py-0.2 rounded bg-slate-800 text-slate-400 font-mono">${t.exchange || 'HOSE'}</span>
          </div>
        </td>
        <td class="py-2.5 px-3">
          ${isBuy
        ? `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                  <i class="fa-solid fa-arrow-down-long text-[8px]"></i> Mua
                </span>`
        : `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/30">
                  <i class="fa-solid fa-arrow-up-long text-[8px]"></i> Bán
                </span>`
      }
        </td>
        <td class="py-2.5 px-3 text-right font-bold text-slate-200">${formatNumber(t.volume)}</td>
        <td class="py-2.5 px-3 text-right text-slate-300">${formatNumber(t.price)} đ</td>
        <td class="py-2.5 px-3 text-right font-bold">
          <div class="text-white">${formatNumber(t.current_price)} đ</div>
          <div class="text-[10px] ${changeColor}">(${changeSign}${t.change_pct}%)</div>
        </td>
        <td class="py-2.5 px-3 text-right text-slate-300">${formatPortfolioVND(t.order_type === 'BUY' ? t.current_amount : t.invested_amount)}</td>
        <td class="py-2.5 px-3 text-right font-bold ${pnlColor}">
          ${isBuy
        ? `<div>${pnlSign}${formatPortfolioVND(t.pnl_val)}</div>
                 <div class="text-[10px]">(${pnlSign}${t.pnl_pct.toFixed(2)}%)</div>`
        : `<span class="text-slate-500 text-[11px] font-sans">Đã chốt bán</span>`
      }
        </td>
        <td class="py-2.5 px-3 text-slate-400 text-[11px] font-sans">${t.trade_date || '-'}</td>
        <td class="py-2.5 px-3 text-slate-400 text-[11px] font-sans max-w-[150px] truncate" title="${t.note || ''}">${t.note || '-'}</td>
        <td class="py-2.5 px-3 text-center">
          <div class="flex items-center justify-center gap-1.5">
            <button type="button" class="edit-trade-btn p-1 text-slate-400 hover:text-emerald-400 transition cursor-pointer" data-id="${t.id}" title="Nạp thông tin lệnh ${t.symbol} lên form">
              <i class="fa-solid fa-pen-to-square text-xs"></i>
            </button>
            <button type="button" class="delete-trade-btn p-1 text-slate-500 hover:text-rose-400 transition cursor-pointer" data-id="${t.id}" title="Xóa lệnh này">
              <i class="fa-solid fa-trash-can text-xs"></i>
            </button>
          </div>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}
