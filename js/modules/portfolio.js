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

let _portfolioData = {
  summary: {
    total_nav: 0,
    total_buy_cost: 0,
    current_market_val: 0,
    unrealized_pnl: 0,
    unrealized_pnl_pct: 0,
    available_nav: 0,
    holdings_count: 0,
    closed_count: 0,
  },
  trades: [],
};

let _currentFilter = 'ALL';
let _searchTerm = '';
let _initialized = false;

function formatVND(val) {
  if (val === undefined || val === null || isNaN(val)) return '0 đ';
  return Math.round(val).toLocaleString('vi-VN') + ' đ';
}

function formatNumber(val) {
  if (val === undefined || val === null || isNaN(val)) return '0';
  return Number(val).toLocaleString('vi-VN');
}

/**
 * Định dạng số với dấu chấm phân cách hàng nghìn (Chuẩn dot: 500.000.000)
 */
function formatDot(val) {
  if (val === undefined || val === null || val === '') return '';
  const digits = String(val).replace(/\D/g, '');
  if (!digits) return '';
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
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
        navInput.placeholder = formatDot(numVal);
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

    // D. Nút Filter Chips
    const filterBtn = target.closest('.portfolio-filter-btn');
    if (filterBtn) {
      document.querySelectorAll('.portfolio-filter-btn').forEach(b => {
        b.className = 'portfolio-filter-btn px-2.5 py-1 rounded-lg border border-slate-800 bg-slate-950 text-slate-400 hover:text-white cursor-pointer';
      });
      filterBtn.className = 'portfolio-filter-btn px-2.5 py-1 rounded-lg border border-slate-700 bg-emerald-600 text-white font-bold cursor-pointer active';
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
    const volume = parseInt(volInput.value, 10);
    const price = parseFloat(priceInput.value);
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

  // 4. Tìm kiếm nhanh & Tự động format dấu chấm (.) cho Tổng NAV khi typing
  document.addEventListener('input', (e) => {
    if (e.target && e.target.id === 'portfolioSearchInput') {
      _searchTerm = e.target.value.trim().toUpperCase();
      renderPortfolioTable(callbacks);
    } else if (e.target && e.target.id === 'userPortfolioNavInput') {
      const rawVal = e.target.value.replace(/\D/g, '');
      e.target.value = formatDot(rawVal);
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

/**
 * Tải dữ liệu danh mục từ backend
 */
export async function loadPortfolioData(callbacks = {}) {
  try {
    const data = await getUserPortfolio();
    if (data && data.success) {
      _portfolioData = data;
      updateSummaryCards(data.summary);
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
  const statTotalPnl = document.getElementById('statTotalPnl');
  const statPnlIcon = document.getElementById('statPnlIcon');

  const totalNav = summary.total_nav || 0;
  const buyCost = summary.total_buy_cost || 0;
  const availNav = summary.available_nav || 0;
  const pnlVal = summary.unrealized_pnl || 0;
  const pnlPct = summary.unrealized_pnl_pct || 0;

  if (navInput && totalNav > 0) {
    navInput.placeholder = formatDot(totalNav);
  }

  if (statTotalNav) statTotalNav.textContent = formatVND(totalNav);
  if (statTotalInvested) statTotalInvested.textContent = formatVND(buyCost);

  if (statInvestedRatio) {
    const ratio = totalNav > 0 ? ((buyCost / totalNav) * 100).toFixed(1) : '0.0';
    statInvestedRatio.textContent = `Chiếm ${ratio}% NAV (${summary.holdings_count || 0} mã)`;
  }

  if (statAvailableNav) statAvailableNav.textContent = formatVND(availNav);
  if (statAvailableRatio) {
    const availRatio = totalNav > 0 ? ((availNav / totalNav) * 100).toFixed(1) : '0.0';
    statAvailableRatio.textContent = `Tiền mặt khả dụng (${availRatio}% NAV)`;
  }

  // P&L styling
  if (statTotalPnl) {
    const isProfit = pnlVal > 0;
    const isLoss = pnlVal < 0;
    const sign = isProfit ? '+' : '';

    statTotalPnl.className = `text-base sm:text-lg font-black font-mono ${
      isProfit ? 'text-emerald-400' : isLoss ? 'text-rose-400' : 'text-slate-300'
    }`;
    statTotalPnl.innerHTML = `${sign}${formatVND(pnlVal)} <span class="text-xs font-semibold ml-1">(${sign}${pnlPct.toFixed(2)}%)</span>`;

    if (statPnlIcon) {
      statPnlIcon.className = `fa-solid ${
        isProfit ? 'fa-arrow-trend-up text-emerald-400' : isLoss ? 'fa-arrow-trend-down text-rose-400' : 'fa-chart-line text-slate-500'
      }`;
    }
  }

  // Cập nhật số lượng trên các nút Filter
  const trades = _portfolioData.trades || [];
  const buyTrades = trades.filter(t => t.order_type === 'BUY');
  const sellTrades = trades.filter(t => t.order_type === 'SELL');
  const profitTrades = trades.filter(t => t.order_type === 'BUY' && t.pnl_val > 0);
  const lossTrades = trades.filter(t => t.order_type === 'BUY' && t.pnl_val < 0);

  const countAll = document.getElementById('filterCountAll');
  const countBuy = document.getElementById('filterCountBuy');
  const countSell = document.getElementById('filterCountSell');
  const countProfit = document.getElementById('filterCountProfit');
  const countLoss = document.getElementById('filterCountLoss');

  if (countAll) countAll.textContent = trades.length;
  if (countBuy) countBuy.textContent = buyTrades.length;
  if (countSell) countSell.textContent = sellTrades.length;
  if (countProfit) countProfit.textContent = profitTrades.length;
  if (countLoss) countLoss.textContent = lossTrades.length;
}

/**
 * Render bảng danh sách giao dịch theo filter hiện tại
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
        <td class="py-2.5 px-3 font-bold">
          <div class="flex items-center gap-1.5">
            <button type="button" class="view-stock-btn text-white hover:text-blue-400 transition cursor-pointer underline decoration-dotted" data-symbol="${t.symbol}">
              ${t.symbol}
            </button>
            <span class="text-[9px] px-1 py-0.2 rounded bg-slate-800 text-slate-400">${t.exchange || 'HOSE'}</span>
          </div>
        </td>
        <td class="py-2.5 px-3">
          ${
            isBuy
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
        <td class="py-2.5 px-3 text-right text-slate-300">${formatVND(t.order_type === 'BUY' ? t.current_amount : t.invested_amount)}</td>
        <td class="py-2.5 px-3 text-right font-bold ${pnlColor}">
          ${
            isBuy
              ? `<div>${pnlSign}${formatVND(t.pnl_val)}</div>
                 <div class="text-[10px]">(${pnlSign}${t.pnl_pct.toFixed(2)}%)</div>`
              : `<span class="text-slate-500 text-[11px] font-sans">Đã chốt bán</span>`
          }
        </td>
        <td class="py-2.5 px-3 text-slate-400 text-[11px] font-sans">${t.trade_date || '-'}</td>
        <td class="py-2.5 px-3 text-slate-400 text-[11px] font-sans max-w-[150px] truncate" title="${t.note || ''}">${t.note || '-'}</td>
        <td class="py-2.5 px-3 text-center">
          <button type="button" class="delete-trade-btn p-1 text-slate-500 hover:text-rose-400 transition cursor-pointer" data-id="${t.id}" title="Xóa lệnh này">
            <i class="fa-solid fa-trash-can text-xs"></i>
          </button>
        </td>
      </tr>
    `;
  });

  tbody.innerHTML = html;
}
