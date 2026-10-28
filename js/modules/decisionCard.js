/**
 * Stock RT - Unified 2-Strategy Decision Hero Card Renderer
 * Triển khai trực tiếp cấu trúc wireframe phân tách rõ ràng:
 * 1. Tổng quan tín hiệu & Trạng thái hành động đối chiếu với thị giá thực tế
 * 2. Hai cột chiến lược song song:
 *    - Cột 1: Chiến lược lướt sóng (T+ / Ngắn hạn) (Khung 3 - 10 phiên)
 *      + Vị thế Mua mới (Vùng mua, Chốt lời, Cắt lỗ, Tỷ lệ R/R)
 *      + Vị thế Đang nắm giữ (Chặn lãi Trailing Stop, Chốt từng phần)
 *    - Cột 2: Chiến lược đầu tư (Trung & Dài hạn) (Khung 3 - 6+ tháng)
 *      + Vị thế Mua mới (Vùng gom, Target 1, Target 2, Ngưỡng quản trị)
 *      + Vị thế Đang nắm giữ (Mốc gia tăng, Mốc hạ tỷ trọng, Kỳ vọng chu kỳ)
 * 3. Luận điểm cốt lõi (3 dòng then chốt: Kỹ thuật, Cơ bản, Quản trị rủi ro)
 * 4. Đồng bộ trực tiếp các mốc giá lên Đồ thị TradingView (Target, Vùng mua, Cắt lỗ)
 */

import { formatVND } from '../utils.js?v=4.0';
import { setChartPriceLines } from './chart.js?v=4.3';

function safeSetText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = (text !== undefined && text !== null) ? text : '--';
}

function safeSetHtml(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = (html !== undefined && html !== null) ? html : '--';
}

let activeFilter = 'newEntry';      // Mặc định luôn là 'newEntry' (Chưa có hàng / Mua mới)
let userCostPrice = null;           // Nhập giá vốn tùy chọn
let cachedDecisionData = null;
let cachedRawData = null;
let controlsInitialized = false;

function setupPositionControls() {
  if (controlsInitialized) return;

  const btnAll = document.getElementById('filterPosAll');
  const btnNew = document.getElementById('filterPosNew');
  const btnHolding = document.getElementById('filterPosHolding');
  const costInput = document.getElementById('userCostInput');

  if (btnAll) {
    btnAll.addEventListener('click', () => {
      activeFilter = 'all';
      updateFilterUI();
    });
  }

  if (btnNew) {
    btnNew.addEventListener('click', () => {
      activeFilter = 'newEntry';
      updateFilterUI();
    });
  }

  if (btnHolding) {
    btnHolding.addEventListener('click', () => {
      activeFilter = 'holding';
      updateFilterUI();
    });
  }

  if (costInput) {
    costInput.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      userCostPrice = (!isNaN(val) && val > 0) ? val : null;
      updateCostPnL();
      syncChartPriceLines();
    });
  }

  controlsInitialized = true;
}

function updateFilterUI() {
  const btnAll = document.getElementById('filterPosAll');
  const btnNew = document.getElementById('filterPosNew');
  const btnHolding = document.getElementById('filterPosHolding');
  const costWidget = document.getElementById('costPriceWidget');

  const boxTPlusNew = document.getElementById('boxTPlusNew');
  const boxTPlusHold = document.getElementById('boxTPlusHold');
  const boxMidtermNew = document.getElementById('boxMidtermNew');
  const boxMidtermHold = document.getElementById('boxMidtermHold');

  const activeBtnClass = 'px-3 py-1.5 rounded-md font-bold transition flex items-center gap-1.5 bg-blue-600 text-white shadow cursor-pointer';
  const activeGreenClass = 'px-3 py-1.5 rounded-md font-bold transition flex items-center gap-1.5 bg-emerald-600 text-white shadow cursor-pointer';
  const activeAmberClass = 'px-3 py-1.5 rounded-md font-bold transition flex items-center gap-1.5 bg-amber-600 text-white shadow cursor-pointer';
  const inactiveBtnClass = 'px-3 py-1.5 rounded-md font-medium text-slate-400 hover:text-slate-200 transition flex items-center gap-1.5 cursor-pointer';

  if (btnAll && btnNew && btnHolding) {
    btnAll.className = activeFilter === 'all' ? activeBtnClass : inactiveBtnClass;
    btnNew.className = activeFilter === 'newEntry' ? activeGreenClass : inactiveBtnClass;
    btnHolding.className = activeFilter === 'holding' ? activeAmberClass : inactiveBtnClass;
  }

  if (costWidget) {
    if (activeFilter === 'holding') {
      costWidget.classList.remove('hidden');
    } else {
      costWidget.classList.add('hidden');
    }
  }

  // Highlight hoặc làm mờ theo vị thế
  if (boxTPlusNew && boxTPlusHold && boxMidtermNew && boxMidtermHold) {
    if (activeFilter === 'newEntry') {
      boxTPlusNew.classList.remove('opacity-40', 'border-slate-800');
      boxTPlusNew.classList.add('border-emerald-500/60', 'ring-1', 'ring-emerald-500/40');
      boxMidtermNew.classList.remove('opacity-40', 'border-slate-800');
      boxMidtermNew.classList.add('border-emerald-500/60', 'ring-1', 'ring-emerald-500/40');

      boxTPlusHold.classList.add('opacity-40');
      boxTPlusHold.classList.remove('ring-1', 'ring-amber-500/40', 'border-amber-500/60');
      boxMidtermHold.classList.add('opacity-40');
      boxMidtermHold.classList.remove('ring-1', 'ring-cyan-500/40', 'border-cyan-500/60');
    } else if (activeFilter === 'holding') {
      boxTPlusHold.classList.remove('opacity-40', 'border-slate-800');
      boxTPlusHold.classList.add('border-amber-500/60', 'ring-1', 'ring-amber-500/40');
      boxMidtermHold.classList.remove('opacity-40', 'border-slate-800');
      boxMidtermHold.classList.add('border-cyan-500/60', 'ring-1', 'ring-cyan-500/40');

      boxTPlusNew.classList.add('opacity-40');
      boxTPlusNew.classList.remove('ring-1', 'ring-emerald-500/40', 'border-emerald-500/60');
      boxMidtermNew.classList.add('opacity-40');
      boxMidtermNew.classList.remove('ring-1', 'ring-emerald-500/40', 'border-emerald-500/60');
    } else {
      // 'all'
      [boxTPlusNew, boxTPlusHold, boxMidtermNew, boxMidtermHold].forEach(box => {
        box.classList.remove('opacity-40', 'ring-1', 'ring-emerald-500/40', 'ring-amber-500/40', 'ring-cyan-500/40', 'border-emerald-500/60', 'border-amber-500/60', 'border-cyan-500/60');
        box.classList.add('border-slate-800');
      });
    }
  }

  updateCostPnL();
  syncChartPriceLines();
}

function updateCostPnL() {
  const pnlBadge = document.getElementById('userPnLBadge');
  if (!pnlBadge) return;

  const currentPrice = (cachedRawData && cachedRawData.price) || 0;
  if (userCostPrice && currentPrice > 0) {
    const pnl = ((currentPrice - userCostPrice) / userCostPrice) * 100;
    const sign = pnl >= 0 ? '+' : '';
    pnlBadge.innerText = `${sign}${pnl.toFixed(1)}%`;
    pnlBadge.className = `text-[11px] font-bold px-1.5 py-0.5 rounded ${pnl >= 0 ? 'bg-emerald-950 text-emerald-300 border border-emerald-700' : 'bg-rose-950 text-rose-300 border border-rose-700'}`;
  } else {
    pnlBadge.innerText = '--%';
    pnlBadge.className = 'text-[11px] font-bold px-1.5 py-0.5 rounded bg-slate-800 text-slate-400';
  }
}

export function renderUnifiedDecisionHero(decisionData, rawData) {
  if (!decisionData) return;
  cachedDecisionData = decisionData;
  cachedRawData = rawData;
  activeFilter = 'newEntry'; // Luôn mặc định là "Chưa có hàng (Mua mới)" khi nạp mã mới
  userCostPrice = null;      // Reset giá vốn người dùng khi sang mã mới
  const costInput = document.getElementById('userCostInput');
  if (costInput) costInput.value = '';

  setupPositionControls();
  updateFilterUI();

  const de = decisionData;
  const tplus = de.tPlus || {};
  const midterm = de.midTerm || {};
  const overall = de.overallSignal || {};
  const priceStatus = de.priceStatusTag || {};
  const thesis = de.coreThesis || {};
  const currentPrice = de.currentPrice || (rawData && rawData.price) || 0;

  // 1. Banner Tổng quan tín hiệu (Overall Signal Banner)
  const signalTextEl = document.getElementById('overallSignalText');
  if (signalTextEl) {
    signalTextEl.innerText = overall.badge || 'ĐANG CẬP NHẬT TÍN HIỆU TOÀN DIỆN...';
    if (overall.type === 'positive') {
      signalTextEl.className = 'text-sm sm:text-base font-black text-emerald-400 tracking-wide mt-0.5';
    } else if (overall.type === 'danger') {
      signalTextEl.className = 'text-sm sm:text-base font-black text-rose-400 tracking-wide mt-0.5';
    } else if (overall.type === 'caution') {
      signalTextEl.className = 'text-sm sm:text-base font-black text-amber-400 tracking-wide mt-0.5';
    } else {
      signalTextEl.className = 'text-sm sm:text-base font-black text-blue-400 tracking-wide mt-0.5';
    }
  }

  // 2. Tag Trạng thái theo Thị giá (Real-time Price Action Status Badge)
  const priceStatusBadgeEl = document.getElementById('headerPriceStatusBadge');
  if (priceStatusBadgeEl) {
    if (priceStatus.badge) {
      priceStatusBadgeEl.innerText = priceStatus.badge;
      if (priceStatus.color === 'emerald') {
        priceStatusBadgeEl.className = 'px-3 py-1.5 rounded-lg text-xs font-mono font-bold uppercase tracking-wider border shadow-md bg-emerald-950 text-emerald-300 border-emerald-600 animate-pulse';
      } else if (priceStatus.color === 'rose') {
        priceStatusBadgeEl.className = 'px-3 py-1.5 rounded-lg text-xs font-mono font-bold uppercase tracking-wider border shadow-md bg-rose-950 text-rose-300 border-rose-600 animate-pulse';
      } else if (priceStatus.color === 'amber') {
        priceStatusBadgeEl.className = 'px-3 py-1.5 rounded-lg text-xs font-mono font-bold uppercase tracking-wider border shadow-md bg-amber-950 text-amber-300 border-amber-600';
      } else {
        priceStatusBadgeEl.className = 'px-3 py-1.5 rounded-lg text-xs font-mono font-bold uppercase tracking-wider border shadow-md bg-blue-950 text-blue-300 border-blue-600';
      }
      priceStatusBadgeEl.title = priceStatus.advice || '';
    } else {
      priceStatusBadgeEl.innerText = 'Chờ nạp dữ liệu...';
      priceStatusBadgeEl.className = 'px-3 py-1.5 rounded-lg text-xs font-mono font-bold uppercase tracking-wider border shadow-md bg-slate-800 text-slate-300 border-slate-700';
    }
  }

  // 3. Badges: Regime & Data Confidence
  const regEl = document.getElementById('heroRegimeBadge');
  if (regEl) {
    const regName = (rawData && rawData.technicals && rawData.technicals.regime && rawData.technicals.regime.regime) || 'NEUTRAL';
    const regScore = (rawData && rawData.technicals && rawData.technicals.regime && rawData.technicals.regime.score) || 3;
    const regColors = {
      RISK_ON: 'bg-emerald-950 text-emerald-300 border-emerald-700',
      NEUTRAL: 'bg-blue-950 text-blue-300 border-blue-700',
      DEFENSIVE: 'bg-amber-950 text-amber-300 border-amber-700',
      NO_NEW_RISK: 'bg-rose-950 text-rose-300 border-rose-700',
    };
    regEl.className = `flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-lg border font-bold ${regColors[regName] || 'bg-slate-800 text-slate-300 border-slate-700'}`;
    safeSetText('heroRegimeText', `Regime: ${regName} (${regScore}/5)`);

    const regConditions = (rawData && rawData.technicals && rawData.technicals.regime && rawData.technicals.regime.conditions) || [];
    const regDetailEl = document.getElementById('heroRegimeTooltipDetail');
    if (regDetailEl && regConditions.length > 0) {
      regDetailEl.innerHTML = regConditions.map(c => `<div>${c.met ? '✓' : '✗'} ${c.name}: ${c.detail}</div>`).join('');
    }
  }

  const dcEl = document.getElementById('heroDcBadge');
  if (dcEl) {
    const dcScore = (rawData && rawData.riskEngine && typeof rawData.riskEngine.dcScore === 'number') ? rawData.riskEngine.dcScore : 100;
    const dcRating = (rawData && rawData.riskEngine && rawData.riskEngine.dcRating) || 'CAO';
    const dcColor = dcScore >= 80 ? 'bg-emerald-950 text-emerald-300 border-emerald-700' :
      (dcScore >= 65 ? 'bg-blue-950 text-blue-300 border-blue-700' : 'bg-amber-950 text-amber-300 border-amber-700');
    dcEl.className = `flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-lg border font-bold ${dcColor}`;
    safeSetText('heroDcText', `DC: ${dcScore}/100 (${dcRating})`);

    const dcDetailEl = document.getElementById('heroDcTooltipDetail');
    if (dcDetailEl) {
      const deductions = (rawData && rawData.riskEngine && rawData.riskEngine.dcDeductions) || [];
      if (deductions.length > 0) {
        dcDetailEl.innerHTML = deductions.map(d => `<div class="text-rose-400">• ${d}</div>`).join('');
      } else {
        dcDetailEl.innerText = '✓ Dữ liệu đầy đủ và cập nhật thời gian thực';
      }
    }
  }

  // 4. Hard Rules Banner (nếu có vi phạm)
  const hardBanner = document.getElementById('heroHardRulesBanner');
  const hardList = document.getElementById('heroHardRulesList');
  const hardRules = tplus.hardRules || midterm.hardRules || {};
  if (hardBanner && hardList) {
    if (hardRules.triggeredCount && hardRules.triggeredCount > 0) {
      hardBanner.classList.remove('hidden');
      hardList.innerHTML = (hardRules.rules || []).map(r => `<li>${r}</li>`).join('');
    } else {
      hardBanner.classList.add('hidden');
      hardList.innerHTML = '';
    }
  }

  // =========================================================================
  // 5. CỘT 1: CHIẾN LƯỢC LƯỚT SÓNG (T+ / NGẮN HẠN)
  // =========================================================================
  safeSetText('tplusScoreBadge', `Điểm: ${tplus.score || 0}/100`);

  // 1A. Mua mới T+
  const tpNew = tplus.newEntry || {};
  safeSetText('tplusNewStatusBadge', `[ ${tpNew.badge || 'QUAN SÁT T+'} ]`);
  const tpNewBadgeEl = document.getElementById('tplusNewStatusBadge');
  if (tpNewBadgeEl) {
    if (tpNew.action === 'BUY') {
      tpNewBadgeEl.className = 'text-xs font-black font-mono px-2.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-600 shadow';
    } else if (tpNew.action === 'WAIT') {
      tpNewBadgeEl.className = 'text-xs font-black font-mono px-2.5 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-600 shadow';
    } else {
      tpNewBadgeEl.className = 'text-xs font-black font-mono px-2.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-600 shadow';
    }
  }

  // Tính toán % Chốt lời & % Cắt lỗ T+
  let tpPctStr = tplus.takeProfitPctDisplay;
  if (!tpPctStr) {
    if (tplus.targetPct !== undefined) {
      tpPctStr = `+${tplus.targetPct}%`;
    } else if (tplus.target && currentPrice > 0) {
      const p = (((tplus.target - currentPrice) / currentPrice) * 100).toFixed(1);
      tpPctStr = (p >= 0 ? '+' : '') + p + '%';
    } else {
      tpPctStr = '';
    }
  }

  let slPctStr = tplus.stopLossPctDisplay;
  if (!slPctStr) {
    if (tplus.stopLossPct !== undefined || tplus.downsidePct !== undefined) {
      const d = tplus.stopLossPct !== undefined ? tplus.stopLossPct : tplus.downsidePct;
      slPctStr = `-${d}%`;
    } else if (tplus.stopLoss && currentPrice > 0) {
      const d = (((currentPrice - tplus.stopLoss) / currentPrice) * 100).toFixed(1);
      slPctStr = `-${d}%`;
    } else {
      slPctStr = '';
    }
  }

  const tplusBuyZoneStr = tplus.buyZone || `${formatVND(tplus.entryMin || 0)} - ${formatVND(tplus.entryMax || 0)} đ`;
  safeSetText('tplusBuyZoneVal', tplusBuyZoneStr);
  safeSetText('tplusBuyZoneTooltipVal', tplusBuyZoneStr);

  const tpEntryPctStr = tplus.takeProfitPctFromEntryDisplay || (tplus.upsideEntryR1Pct !== undefined ? `+${tplus.upsideEntryR1Pct}%` : '');

  // Hiển thị ô Chốt lời (TP) - Giá sạch không kèm % cùng dòng
  safeSetText('tplusTPPctBadge', tpPctStr || '+0%');
  const tpCleanPrice = tplus.takeProfit || (tplus.target ? `${formatVND(tplus.target)} đ` : '--');
  safeSetText('tplusTPVal', tpCleanPrice);
  safeSetText('tplusTPTooltipPrice', tpCleanPrice);
  safeSetText('tplusTPTooltipPct', tpPctStr || '+0%');
  safeSetText('tplusTPTooltipEntryPct', tpEntryPctStr || tpPctStr || '+0%');
  const tplusTPEl = document.getElementById('tplusTPVal');
  if (tplusTPEl) {
    tplusTPEl.title = `Mục tiêu chốt lời: ${tpCleanPrice} (Từ giá hiện tại: ${tpPctStr}${tpEntryPctStr ? ` | Từ nền mua: ${tpEntryPctStr}` : ''})`;
  }

  // Hiển thị ô Cắt lỗ (SL) - Giá sạch không kèm % cùng dòng
  safeSetText('tplusSLPctBadge', slPctStr || '-0%');
  const slCleanPrice = tplus.stopLoss ? `< ${formatVND(tplus.stopLoss)} đ` : (tplus.stopLossPriceDisplay || '--');
  safeSetText('tplusSLVal', slCleanPrice);
  safeSetText('tplusSLTooltipPrice', slCleanPrice);
  safeSetText('tplusSLTooltipPct', slPctStr || '-0%');
  const tplusSLEl = document.getElementById('tplusSLVal');
  if (tplusSLEl) tplusSLEl.title = `Mốc cắt lỗ phòng thủ: ${slCleanPrice} (${slPctStr})`;

  safeSetText('tplusRRVal', `1 : ${tplus.netRR || 1.0}`);
  safeSetText('tplusNewReasonText', tpNew.reason || 'Đang phân tích điểm giải ngân...');

  // 1B. Đang nắm giữ T+
  const tpHold = tplus.holding || {};
  safeSetText('tplusHoldStatusBadge', `[ ${tpHold.badge || 'TIẾP TỤC NẮM GIỮ'} ]`);
  const tpHoldBadgeEl = document.getElementById('tplusHoldStatusBadge');
  if (tpHoldBadgeEl) {
    if (tpHold.action === 'HOLD') {
      tpHoldBadgeEl.className = 'text-xs font-black font-mono px-2.5 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-600 shadow';
    } else if (tpHold.action === 'REDUCE') {
      tpHoldBadgeEl.className = 'text-xs font-black font-mono px-2.5 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-600 shadow';
    } else if (tpHold.action === 'SELL') {
      tpHoldBadgeEl.className = 'text-xs font-black font-mono px-2.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-600 shadow';
    } else {
      tpHoldBadgeEl.className = 'text-xs font-black font-mono px-2.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-600 shadow';
    }
  }

  safeSetText('tplusTrailingVal', `Nâng SL lên mốc ${tplus.trailingStopDisplay || (tplus.trailingStop ? `${formatVND(tplus.trailingStop)} đ` : '--')}`);
  safeSetText('tplusTrimVal', tplus.sellPartialDisplay || `Bán 50% quanh ${formatVND(tplus.target || 0)} đ`);
  safeSetText('tplusHoldReasonText', tpHold.reason || 'Đang phân tích phương án gồng lãi...');

  // Chỉ số con T+
  const ind = tplus.indicators || {};
  safeSetText('tplusIndVol', `Vol: x${ind.volRatio || 1.0} TB20`);
  safeSetText('tplusIndBuyRatio', `Mua CĐ: ${ind.buyRatio || 50}%`);
  safeSetText('tplusIndRSI', `RSI: ${ind.rsi || 50}`);
  const stochRsi = ind.stochRsi || {};
  safeSetText('tplusIndStochRSI', `StochRSI: ${stochRsi.display || (stochRsi.k ? `${stochRsi.k}/${stochRsi.d}` : '--')}`);
  safeSetText('tplusIndAlloc', `Giải ngân: ${tpNew.allocatedNowPct || 0}% NAV`);

  // =========================================================================
  // 6. CỘT 2: CHIẾN LƯỢC ĐẦU TƯ (TRUNG & DÀI HẠN)
  // =========================================================================
  safeSetText('midtermScoreBadge', `FA: ${midterm.score || 0}/100`);

  // 2A. Mua mới Trung hạn
  const midNew = midterm.newEntry || {};
  safeSetText('midtermNewStatusBadge', `[ ${midNew.badge || 'TÍCH SẢN TỪNG PHẦN'} ]`);
  const midNewBadgeEl = document.getElementById('midtermNewStatusBadge');
  if (midNewBadgeEl) {
    if (midNew.action === 'BUY') {
      midNewBadgeEl.className = 'text-xs font-black font-mono px-2.5 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-600 shadow';
    } else if (midNew.action === 'WAIT') {
      midNewBadgeEl.className = 'text-xs font-black font-mono px-2.5 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-600 shadow';
    } else {
      midNewBadgeEl.className = 'text-xs font-black font-mono px-2.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-600 shadow';
    }
  }

  // Tính toán % Target 1, Target 2 & Cắt lỗ Trung hạn
  const mTarget1Pct = midterm.target1PctDisplay || (midterm.marginOfSafetyPct !== undefined ? `+${midterm.marginOfSafetyPct}%` : (midterm.target && currentPrice > 0 ? `+${(((midterm.target - currentPrice) / currentPrice) * 100).toFixed(1)}%` : ''));
  const mTarget2Pct = midterm.target2PctDisplay || (midterm.target2Pct !== undefined ? `+${midterm.target2Pct}%` : (midterm.targetHigh && currentPrice > 0 ? `+${(((midterm.targetHigh - currentPrice) / currentPrice) * 100).toFixed(1)}%` : ''));
  const mStopPct = midterm.stopLossPctDisplay || (midterm.stopLossPct !== undefined ? `-${midterm.stopLossPct}%` : (midterm.stopLoss && currentPrice > 0 ? `-${(((currentPrice - midterm.stopLoss) / currentPrice) * 100).toFixed(1)}%` : ''));

  safeSetText('midtermT1PctBadge', mTarget1Pct || '+0%');
  safeSetText('midtermT2PctBadge', mTarget2Pct || '+0%');
  safeSetText('midtermSLPctBadge', mStopPct || '-0%');

  const mBuyZoneStr = midterm.buyZone || `${formatVND(midterm.entryMin || 0)} - ${formatVND(midterm.entryMax || 0)} đ`;
  safeSetText('midtermBuyZoneVal', mBuyZoneStr);
  safeSetText('midtermBuyZoneTooltipVal', mBuyZoneStr);

  // Target 1 - Giá sạch không kèm % cùng dòng
  const midT1Price = midterm.target ? `${formatVND(midterm.target)} đ` : (midterm.target1Display || '--');
  safeSetText('midtermTarget1Val', midT1Price);
  safeSetText('midtermT1TooltipPrice', midT1Price);
  safeSetText('midtermT1TooltipPct', mTarget1Pct || '+0%');
  const midT1El = document.getElementById('midtermTarget1Val');
  if (midT1El) midT1El.title = `Target 1: ${midT1Price} (${mTarget1Pct})`;

  // Target 2 - Giá sạch không kèm % cùng dòng
  const midT2Price = midterm.targetHigh ? `${formatVND(midterm.targetHigh)} đ` : (midterm.target2Display || '--');
  safeSetText('midtermTarget2Val', midT2Price);
  safeSetText('midtermT2TooltipPrice', midT2Price);
  safeSetText('midtermT2TooltipPct', mTarget2Pct || '+0%');
  const midT2El = document.getElementById('midtermTarget2Val');
  if (midT2El) midT2El.title = `Target 2: ${midT2Price} (${mTarget2Pct})`;

  // Ngưỡng QTRR - Giá sạch không kèm % cùng dòng
  const midSLPrice = midterm.stopLoss ? `< ${formatVND(midterm.stopLoss)} đ` : (midterm.riskThresholdDisplay || '--');
  safeSetText('midtermRiskStopVal', midSLPrice);
  safeSetText('midtermSLTooltipPrice', midSLPrice);
  safeSetText('midtermSLTooltipPct', mStopPct || '-0%');
  const midSLEl = document.getElementById('midtermRiskStopVal');
  if (midSLEl) midSLEl.title = `Ngưỡng QTRR: ${midSLPrice} (${mStopPct})`;

  safeSetText('midtermNewReasonText', midNew.reason || 'Đang phân tích định giá nội tại BCTC...');

  // 2B. Đang nắm giữ Trung hạn
  const midHold = midterm.holding || {};
  safeSetText('midtermHoldStatusBadge', `[ ${midHold.badge || 'NẮM GIỮ THEO XU HƯỚNG'} ]`);
  const midHoldBadgeEl = document.getElementById('midtermHoldStatusBadge');
  if (midHoldBadgeEl) {
    if (midHold.action === 'HOLD') {
      midHoldBadgeEl.className = 'text-xs font-black font-mono px-2.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-600 shadow';
    } else if (midHold.action === 'REDUCE') {
      midHoldBadgeEl.className = 'text-xs font-black font-mono px-2.5 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-600 shadow';
    } else {
      midHoldBadgeEl.className = 'text-xs font-black font-mono px-2.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-600 shadow';
    }
  }

  safeSetText('midtermAddVal', midterm.mocGiaTang || `Vượt cản ${formatVND(midterm.target || 0)} đ với vol lớn`);
  safeSetText('midtermTrimVal', midterm.mocHaTyTrong || `Đóng nến tuần dưới ${formatVND(midterm.stopLoss || 0)} đ`);
  safeSetText('midtermCycleVal', midterm.kyVongChuKy || '+25% - 30%');
  safeSetText('midtermHoldReasonText', midHold.reason || 'Đang phân tích chu kỳ tăng trưởng...');

  // Chỉ số con Trung hạn
  const mInd = midterm.indicators || {};
  safeSetText('midtermIndPE', `P/E: ${midterm.pe ? midterm.pe.toFixed(1) : '--'}x`);
  safeSetText('midtermIndPB', `P/B: ${midterm.pb ? midterm.pb.toFixed(2) : '--'}x`);
  safeSetText('midtermIndROE', `ROE: ${midterm.roe ? midterm.roe.toFixed(1) : '--'}%`);
  const macd = mInd.macd || {};
  safeSetText('midtermIndMACD', `MACD: ${macd.display || (macd.macd !== undefined ? macd.macd : '--')}`);
  safeSetText('midtermIndEMA200', `EMA200: ${mInd.ema200 ? `${formatVND(mInd.ema200)} đ` : '--'}`);
  const marginSign = (midterm.marginOfSafetyPct !== undefined && midterm.marginOfSafetyPct >= 0) ? '+' : '';
  safeSetText('midtermIndSafety', `Biên an toàn: ${marginSign}${midterm.marginOfSafetyPct !== undefined ? midterm.marginOfSafetyPct : 0}%`);

  // =========================================================================
  // 7. LUẬN ĐIỂM CỐT LÕI (3 DÒNG THEN CHỐT THEO ĐÚNG WIREFRAME)
  // =========================================================================
  safeSetText('coreThesisTechnical', thesis.technical || '1. Đồ thị kỹ thuật (120D): Đang cập nhật dữ liệu nến...');
  safeSetText('coreThesisFundamental', thesis.fundamental || '2. Động lực cơ bản: Đang cập nhật BCTC doanh nghiệp...');
  safeSetText('coreThesisRisk', thesis.risk || '3. Kịch bản quản trị: Đang thiết lập các mốc cắt lỗ & chốt lời...');

  // =========================================================================
  // 8. ĐỒNG BỘ TRỰC QUAN CÁC ĐƯỜNG MỐC GIÁ LÊN CHART TRADINGVIEW & LÀM NỔI BẬT CỘT
  // =========================================================================
  const isMidTermHorizon = decisionData?.activeHorizon === 'midTerm' || rawData?.decisionEngine?.activeHorizon === 'midTerm';
  const colTPlus = document.getElementById('colTPlus');
  const colMidterm = document.getElementById('colMidterm');

  if (colTPlus && colMidterm) {
    if (isMidTermHorizon) {
      colMidterm.classList.add('ring-2', 'ring-purple-500', 'border-purple-600/80', 'bg-purple-950/20');
      colMidterm.classList.remove('border-indigo-900/40', 'bg-slate-950/70', 'opacity-85');
      colTPlus.classList.remove('ring-2', 'ring-blue-500', 'border-blue-600/80', 'bg-blue-950/20');
      colTPlus.classList.add('border-blue-900/30', 'opacity-85');
    } else {
      colTPlus.classList.add('ring-2', 'ring-blue-500', 'border-blue-600/80', 'bg-blue-950/20');
      colTPlus.classList.remove('border-blue-900/30', 'opacity-85');
      colMidterm.classList.remove('ring-2', 'ring-purple-500', 'border-purple-600/80', 'bg-purple-950/20');
      colMidterm.classList.add('border-indigo-900/40', 'bg-slate-950/70', 'opacity-85');
    }
  }

  // Gọi đồng bộ đường giá trực tiếp lên Chart TradingView
  syncChartPriceLines();
}

/**
 * Đồng bộ đường giá khuyến nghị lên đồ thị TradingView theo đúng vị thế người dùng
 * - Chưa có hàng (Mua mới / Tất cả): Vùng mua, Target 1, Target 2, Cắt lỗ gốc (SL)
 * - Đang nắm giữ: Ẩn đường vùng mua; Đổi đường phòng thủ thành Hỗ trợ Chặn Lãi (Amber) bảo toàn lợi nhuận; Focus Target 2
 */
export function syncChartPriceLines() {
  if (!cachedDecisionData) return;
  try {
    const de = cachedDecisionData;
    const rawData = cachedRawData;
    const tplus = de.tPlus || {};
    const midterm = de.midTerm || {};
    const overall = de.overallSignal || {};
    const priceStatus = de.priceStatusTag || {};
    const currentPrice = de.currentPrice || (rawData && rawData.price) || 0;

    const isMidTermHorizon = de.activeHorizon === 'midTerm' || rawData?.decisionEngine?.activeHorizon === 'midTerm';
    const primarySrc = isMidTermHorizon ? midterm : tplus;

    const isProhibited = overall.type === 'danger' || 
      (primarySrc.hardRules && primarySrc.hardRules.triggeredCount > 0) || 
      (priceStatus && priceStatus.color === 'rose') ||
      (priceStatus && priceStatus.badge && priceStatus.badge.includes('CẤM MUA')) ||
      (primarySrc.newEntry && primarySrc.newEntry.action === 'WAIT' && 
       ['AVOID_RISK', 'TAIL_RISK', 'AVOID_ILLIQUID'].includes(primarySrc.newEntry.subtag));

    const isHoldingMode = activeFilter === 'holding';

    if (isMidTermHorizon) {
      const midT1Price = midterm.target || 0;
      const midT2Price = midterm.targetHigh || 0;
      const valBand = midterm.valuationBand || {};
      const midBuyZone = valBand.fairLow || (midT1Price > 0 ? midT1Price * 0.9 : 0);
      const midStop = midterm.stopLoss || 0;
      const marginOfSafety = midterm.marginOfSafetyPct !== undefined ? midterm.marginOfSafetyPct : 0;
      const marginSign = marginOfSafety >= 0 ? '+' : '';

      const isMidLock = isHoldingMode && ((userCostPrice && currentPrice > userCostPrice) || (midT1Price > 0 && currentPrice >= midT1Price * 0.98));

      setChartPriceLines({
        target: midT1Price,
        targetLabel: isProhibited 
          ? `Kháng cự hạ tỷ trọng: ${formatVND(midT1Price)}` 
          : `Target 1 (Định giá): ${formatVND(midT1Price)} (${marginSign}${marginOfSafety}%)`,
        target2: isProhibited ? null : midT2Price,
        target2Label: (!isProhibited && midT2Price) ? `Target 2 (Đỉnh CK): ${formatVND(midT2Price)}` : '',
        buyZone: (isHoldingMode || isProhibited) ? null : midBuyZone,
        buyZoneLabel: isProhibited 
          ? `Hỗ trợ tuần: ${formatVND(midBuyZone)} (Cấm bắt đáy)` 
          : `Vùng gom tích sản: ${formatVND(midBuyZone)}`,
        stopLoss: midStop,
        stopLossLabel: isProhibited 
          ? `Ngưỡng thoát vị thế: ${formatVND(midStop)}` 
          : (isMidLock ? `Hỗ trợ Chặn Lãi Tuần: ${formatVND(midStop)}` : `Ngưỡng QTRR Tuần: ${formatVND(midStop)}`),
        isProhibited: isProhibited,
        isLockProfit: isMidLock,
      });
    } else {
      const rawSL = tplus.stopLoss || 0;
      const trailingSL = tplus.trailingStop || 0;
      const isHitTarget1 = tplus.isHitTarget1 || (tplus.target1 && currentPrice >= tplus.target1 * 0.98);

      const target1Price = tplus.target1 || tplus.target || 0;
      const target2Price = tplus.target2 || 0;

      const tpPctStr = tplus.targetPct ? `+${tplus.targetPct}%` : '';
      const slPctStr = tplus.stopLossPct ? `-${tplus.stopLossPct}%` : '';

      if (isHoldingMode) {
        // =========================================================================
        // CHẾ ĐỘ: ĐANG NẮM GIỮ (HOLDING)
        // =========================================================================
        // 1. Ẩn hoàn toàn đường vùng mua (buyZone = null) để đồ thị thoáng đãng
        // 2. Mốc Hỗ trợ Chặn Lãi / Trailing Stop:
        const hasProfit = (userCostPrice && currentPrice > userCostPrice) || isHitTarget1 || (trailingSL > rawSL);
        const lockStopPrice = (trailingSL && trailingSL > rawSL) ? trailingSL : (tplus.support || rawSL);

        let holdingSLLabel = `Cắt lỗ: ${formatVND(rawSL)}`;
        let isLockProfit = false;

        if (isProhibited) {
          holdingSLLabel = `Ngưỡng thoát vị thế: ${formatVND(lockStopPrice || rawSL)}`;
        } else if (hasProfit) {
          isLockProfit = true;
          if (isHitTarget1) {
            holdingSLLabel = `Hòa vốn (BE) / Chặn lãi: ${formatVND(lockStopPrice)}`;
          } else {
            holdingSLLabel = `Hỗ trợ Chặn Lãi: ${formatVND(lockStopPrice)}`;
          }
        } else {
          holdingSLLabel = `Ngưỡng QTRR: ${formatVND(rawSL)}`;
        }

        // Target cho người nắm giữ:
        let primaryTarget = target1Price;
        let primaryTargetLabel = `Target 1 (T+): ${formatVND(target1Price)}`;
        let secTarget = target2Price;
        let secTargetLabel = target2Price ? `Target 2 (Trend): ${formatVND(target2Price)}` : '';

        if (isHitTarget1 && target2Price > 0) {
          primaryTarget = target2Price;
          primaryTargetLabel = `Target 2 (Gồng lãi): ${formatVND(target2Price)}`;
          secTarget = null;
          secTargetLabel = '';
        }

        setChartPriceLines({
          target: isProhibited ? target1Price : primaryTarget,
          targetLabel: isProhibited ? `Kháng cự hạ tỷ trọng: ${formatVND(target1Price)}` : primaryTargetLabel,
          target2: isProhibited ? null : secTarget,
          target2Label: secTargetLabel,
          buyZone: null, // Không vẽ đường vùng mua khi đang nắm giữ
          buyZoneLabel: '',
          stopLoss: lockStopPrice || rawSL,
          stopLossLabel: holdingSLLabel,
          isProhibited: isProhibited,
          isLockProfit: isLockProfit,
        });
      } else {
        // =========================================================================
        // CHẾ ĐỘ: CHƯA CÓ HÀNG (MUA MỚI - MẶC ĐỊNH) HOẶC TẤT CẢ
        // =========================================================================
        const buyPrice = tplus.entryMin || tplus.entryMax || tplus.support || 0;
        let buyLabel = `Vùng mua: ${formatVND(buyPrice)}`;
        if (isProhibited) {
          buyLabel = `Hỗ trợ S1: ${formatVND(buyPrice)} (Cấm bắt đáy)`;
        } else if (tplus.isExtendedFromBase && tplus.pullbackMin && tplus.pullbackMax) {
          buyLabel = `Mua Pullback: ${formatVND(tplus.pullbackMin)} - ${formatVND(tplus.pullbackMax)}`;
        }

        let defaultSLLabel = isProhibited 
          ? `Ngưỡng thoát vị thế: ${formatVND(rawSL)}` 
          : `Cắt lỗ (SL): ${formatVND(rawSL)}${slPctStr ? ` (${slPctStr})` : ''}`;

        setChartPriceLines({
          target: target1Price,
          targetLabel: isProhibited 
            ? `Kháng cự hạ tỷ trọng: ${formatVND(target1Price)}` 
            : `Target 1 (T+): ${formatVND(target1Price)}${tpPctStr ? ` (${tpPctStr})` : ''}`,
          target2: isProhibited ? null : target2Price,
          target2Label: (!isProhibited && target2Price) ? `Target 2 (Trend): ${formatVND(target2Price)}` : '',
          buyZone: buyPrice,
          buyZoneLabel: buyLabel,
          stopLoss: rawSL,
          stopLossLabel: defaultSLLabel,
          isProhibited: isProhibited,
          isLockProfit: false,
        });
      }
    }
  } catch (err) {
    console.warn("Lỗi vẽ đường giá trên TradingView Chart:", err);
  }
}
