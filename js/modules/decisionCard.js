/**
 * Stock RT - Unified & Multi-Perspective Decision Hero Card Renderer
 * Render dữ liệu phân tách 2 chiều:
 * - Khung thời gian: Lướt Sóng T+ vs Trung & Dài Hạn
 * - Vị thế nhà đầu tư: Mua Mới (Chưa có hàng) vs Đang Nắm Giữ (Đã có hàng)
 */
import { formatVND, formatCompactNumber } from '../utils.js?v=4.0';

function safeSetText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = (text !== undefined && text !== null) ? text : '--';
}

function safeSetHtml(id, html) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = (html !== undefined && html !== null) ? html : '--';
}

let activeHorizon = 'tPlus';        // 'tPlus' | 'midTerm'
let activePosition = 'newEntry';     // 'newEntry' | 'holding'
let userCostPrice = null;            // Nhập giá vốn tùy chọn
let cachedDecisionData = null;
let cachedRawData = null;
let controlsInitialized = false;

const actionStyleMap = {
  BUY: {
    btn: 'bg-emerald-950 text-emerald-300 border-emerald-500 shadow-emerald-950/60 shadow-lg',
    icon: 'fa-solid fa-circle-check text-emerald-400',
  },
  ADD: {
    btn: 'bg-teal-950 text-teal-300 border-teal-500 shadow-teal-950/60 shadow-lg',
    icon: 'fa-solid fa-circle-plus text-teal-400',
  },
  WAIT: {
    btn: 'bg-amber-950 text-amber-300 border-amber-500 shadow-amber-950/60 shadow-lg',
    icon: 'fa-solid fa-hand text-amber-400',
  },
  AVOID: {
    btn: 'bg-slate-900 text-slate-300 border-slate-700 shadow-slate-950/60 shadow-lg',
    icon: 'fa-solid fa-ban text-slate-400',
  },
  HOLD: {
    btn: 'bg-blue-950 text-blue-300 border-blue-500 shadow-blue-950/60 shadow-lg',
    icon: 'fa-solid fa-shield-halved text-blue-400',
  },
  REDUCE: {
    btn: 'bg-orange-950 text-orange-300 border-orange-500 shadow-orange-950/60 shadow-lg',
    icon: 'fa-solid fa-arrow-down-short-wide text-orange-400',
  },
  SELL: {
    btn: 'bg-rose-950 text-rose-300 border-rose-500 shadow-rose-950/60 shadow-lg animate-pulse',
    icon: 'fa-solid fa-triangle-exclamation text-rose-400',
  },
};

function setupInteractiveControls() {
  if (controlsInitialized) return;

  const btnTplus = document.getElementById('heroTabTplus');
  const btnMidterm = document.getElementById('heroTabMidterm');
  const btnPosNew = document.getElementById('heroPosNew');
  const btnPosHolding = document.getElementById('heroPosHolding');
  const costInput = document.getElementById('heroEntryCostInput');

  if (btnTplus && btnMidterm) {
    btnTplus.addEventListener('click', () => {
      activeHorizon = 'tPlus';
      updateControlButtons();
      if (cachedDecisionData) renderMultiPerspectiveView(cachedDecisionData, cachedRawData);
    });

    btnMidterm.addEventListener('click', () => {
      activeHorizon = 'midTerm';
      updateControlButtons();
      if (cachedDecisionData) renderMultiPerspectiveView(cachedDecisionData, cachedRawData);
    });
  }

  if (btnPosNew && btnPosHolding) {
    btnPosNew.addEventListener('click', () => {
      activePosition = 'newEntry';
      updateControlButtons();
      if (cachedDecisionData) renderMultiPerspectiveView(cachedDecisionData, cachedRawData);
    });

    btnPosHolding.addEventListener('click', () => {
      activePosition = 'holding';
      updateControlButtons();
      if (cachedDecisionData) renderMultiPerspectiveView(cachedDecisionData, cachedRawData);
    });
  }

  if (costInput) {
    costInput.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value);
      userCostPrice = (!isNaN(val) && val > 0) ? val : null;
      updateCostPnL();
      if (cachedDecisionData) renderMultiPerspectiveView(cachedDecisionData, cachedRawData);
    });
  }

  controlsInitialized = true;
}

function updateControlButtons() {
  const btnTplus = document.getElementById('heroTabTplus');
  const btnMidterm = document.getElementById('heroTabMidterm');
  const btnPosNew = document.getElementById('heroPosNew');
  const btnPosHolding = document.getElementById('heroPosHolding');
  const costBox = document.getElementById('heroHoldingCostBox');

  // Horizon buttons
  if (btnTplus && btnMidterm) {
    if (activeHorizon === 'tPlus') {
      btnTplus.className = 'px-2.5 py-1 rounded-md font-bold transition flex items-center gap-1 bg-blue-600 text-white shadow cursor-pointer';
      btnMidterm.className = 'px-2.5 py-1 rounded-md font-medium text-slate-400 hover:text-slate-200 transition flex items-center gap-1 cursor-pointer';
    } else {
      btnTplus.className = 'px-2.5 py-1 rounded-md font-medium text-slate-400 hover:text-slate-200 transition flex items-center gap-1 cursor-pointer';
      btnMidterm.className = 'px-2.5 py-1 rounded-md font-bold transition flex items-center gap-1 bg-cyan-600 text-white shadow cursor-pointer';
    }
  }

  // Position buttons
  if (btnPosNew && btnPosHolding) {
    if (activePosition === 'newEntry') {
      btnPosNew.className = 'px-2.5 py-1 rounded-md font-bold transition flex items-center gap-1.5 bg-emerald-600 text-white shadow cursor-pointer';
      btnPosHolding.className = 'px-2.5 py-1 rounded-md font-medium text-slate-400 hover:text-slate-200 transition flex items-center gap-1.5 cursor-pointer';
      if (costBox) costBox.classList.add('hidden');
    } else {
      btnPosNew.className = 'px-2.5 py-1 rounded-md font-medium text-slate-400 hover:text-slate-200 transition flex items-center gap-1.5 cursor-pointer';
      btnPosHolding.className = 'px-2.5 py-1 rounded-md font-bold transition flex items-center gap-1.5 bg-amber-600 text-white shadow cursor-pointer';
      if (costBox) costBox.classList.remove('hidden');
    }
  }

  updateCostPnL();
}

function updateCostPnL() {
  const pnlBadge = document.getElementById('heroCostPnLBadge');
  if (!pnlBadge) return;

  const currentPrice = (cachedRawData && cachedRawData.price) || 0;
  if (userCostPrice && currentPrice > 0) {
    const pnl = ((currentPrice - userCostPrice) / userCostPrice) * 100;
    const sign = pnl >= 0 ? '+' : '';
    pnlBadge.innerText = `${sign}${pnl.toFixed(1)}%`;
    pnlBadge.className = `text-xs font-bold px-2 py-0.5 rounded ${pnl >= 0 ? 'bg-emerald-950 text-emerald-300 border border-emerald-700' : 'bg-rose-950 text-rose-300 border border-rose-700'}`;
  } else {
    pnlBadge.innerText = '--%';
    pnlBadge.className = 'text-xs font-bold px-2 py-0.5 rounded bg-slate-800 text-slate-400';
  }
}

function renderMultiPerspectiveView(de, rawData) {
  const isTplus = activeHorizon === 'tPlus';
  const isHolding = activePosition === 'holding';

  const strat = isTplus ? (de.tPlus || de) : (de.midTerm || de);
  const perspective = isHolding ? (strat.holding || strat) : (strat.newEntry || strat);

  const qual = de.quality || {};
  const tim = de.timing || {};
  const targets = de.targetsAndStops || {};
  const scen = de.scenarios || {};
  const hardRules = strat.hardRules || de.hardRules || {};
  const coreQ = perspective.coreQuestions || strat.coreQuestions || de.coreQuestions || {};

  // 1. Hard Rules Alert Banner
  const hardBanner = document.getElementById('heroHardRulesBanner');
  const hardList = document.getElementById('heroHardRulesList');
  if (hardBanner && hardList) {
    if (hardRules.triggeredCount && hardRules.triggeredCount > 0) {
      hardBanner.classList.remove('hidden');
      hardList.innerHTML = (hardRules.rules || []).map(r => `<li>${r}</li>`).join('');
    } else {
      hardBanner.classList.add('hidden');
      hardList.innerHTML = '';
    }
  }

  // 2. Spotlight Action Big Badge
  const actionBadgeEl = document.getElementById('heroActionBigBadge');
  const actionIconEl = document.getElementById('heroActionIcon');
  const actionTextEl = document.getElementById('heroPrimaryActionText');

  const actionKey = perspective.action || 'WAIT';
  const actionStyle = actionStyleMap[actionKey] || actionStyleMap.WAIT;

  if (actionBadgeEl) {
    actionBadgeEl.className = `px-4 py-2 rounded-xl text-lg sm:text-xl font-black uppercase tracking-wider font-mono border shadow-lg flex items-center gap-2 ${actionStyle.btn}`;
  }
  if (actionIconEl) {
    actionIconEl.className = actionStyle.icon;
  }
  if (actionTextEl) {
    actionTextEl.innerText = actionKey;
  }

  safeSetText('heroActionSubtagBadge', perspective.badge || '--');

  // Reason text kèm PnL nếu có
  let reasonText = perspective.reason || '--';
  const currentPrice = (rawData && rawData.price) || 0;
  if (isHolding && userCostPrice && currentPrice > 0) {
    const pnl = ((currentPrice - userCostPrice) / userCostPrice) * 100;
    const pnlPrefix = `[Giá vốn: ${formatVND(userCostPrice)} đ → Đang ${pnl >= 0 ? 'lãi' : 'lỗ'} ${pnl >= 0 ? '+' : ''}${pnl.toFixed(1)}%] `;
    reasonText = pnlPrefix + reasonText;
  }
  safeSetText('heroActionReasonText', reasonText);

  // 3. Subtitles & Indicators
  if (isTplus) {
    if (!isHolding) {
      safeSetText('heroHorizonFocus', 'Khung: Lướt sóng T+ (2-7 phiên) • Vị thế: Mua mới');
      safeSetText('heroHorizonBadgeDetail', 'Ưu tiên điểm vào & tỷ lệ R/R');
      safeSetText('heroAllocatedLabel', 'Giải ngân tức thời phiên hôm nay:');
    } else {
      safeSetText('heroHorizonFocus', 'Khung: Lướt sóng T+ (2-7 phiên) • Vị thế: Đang nắm giữ');
      safeSetText('heroHorizonBadgeDetail', 'Ưu tiên gồng lãi & Trailing Stop');
      safeSetText('heroAllocatedLabel', 'Tỷ trọng vị thế hiện tại đề xuất:');
    }
    safeSetText('heroAllocatedNowText', `${perspective.allocatedNowPct || 0}% NAV`);

    const ind = strat.indicators || {};
    safeSetText('heroMetric1', `Mua CĐ: ${ind.buyRatio || 50}%`);
    safeSetText('heroMetric2', `Vol: x${ind.volRatio || 1.0} TB20`);
    const divTag = ind.hasBullishDivergence ? ' (Phân kỳ +)' : '';
    safeSetText('heroMetric3', `RSI: ${ind.rsi || 50}${divTag}`);
    safeSetText('heroMetric4', `Net R/R: 1:${strat.netRR || 1.0}`);
  } else {
    if (!isHolding) {
      safeSetText('heroHorizonFocus', 'Khung: Trung & Dài hạn (3-12+ tháng) • Vị thế: Tích sản mới');
      safeSetText('heroHorizonBadgeDetail', 'Ưu tiên định giá BCTC & Biên an toàn');
      safeSetText('heroAllocatedLabel', 'Tỷ trọng tích sản thăm dò:');
    } else {
      safeSetText('heroHorizonFocus', 'Khung: Trung & Dài hạn (3-12+ tháng) • Vị thế: Đang nắm giữ');
      safeSetText('heroHorizonBadgeDetail', 'Ưu tiên tăng trưởng dài hạn & Thoái vốn BCTC');
      safeSetText('heroAllocatedLabel', 'Tỷ trọng nắm giữ trung hạn:');
    }
    safeSetText('heroAllocatedNowText', `${perspective.allocatedNowPct || 0}% NAV`);

    safeSetText('heroMetric1', `P/E: ${strat.pe ? strat.pe.toFixed(1) : '--'}x`);
    safeSetText('heroMetric2', `P/B: ${strat.pb ? strat.pb.toFixed(2) : '--'}x`);
    safeSetText('heroMetric3', `ROE: ${strat.roe ? strat.roe.toFixed(1) : '--'}%`);
    const marginSign = (strat.marginOfSafetyPct !== undefined && strat.marginOfSafetyPct >= 0) ? '+' : '';
    safeSetText('heroMetric4', `Biên an toàn: ${marginSign}${strat.marginOfSafetyPct !== undefined ? strat.marginOfSafetyPct : 0}%`);
  }

  // 4. Hàng 4 Chỉ Số Thực Thi
  const posVal = perspective.allocatedNowPct !== undefined ? perspective.allocatedNowPct : 0;
  safeSetText('heroPosSizingVal', `${posVal}% NAV`);
  if (!isHolding) {
    safeSetText('heroPosSizingSub', `Thăm dò ${strat.pilotNavPct || 5}% • Tối đa ${strat.maxNavPct || 15}% NAV`);
  } else {
    safeSetText('heroPosSizingSub', isTplus ? 'Bảo toàn lợi nhuận theo Trailing Stop' : 'Đồng hành theo chu kỳ doanh nghiệp');
  }

  const netRR = isTplus ? (strat.netRR || 1.0) : (scen.netRR || 1.0);
  const rrEl = document.getElementById('heroNetRRVal');
  if (rrEl) {
    rrEl.innerText = `1 : ${netRR}`;
    rrEl.className = `text-base sm:text-lg font-black font-mono ${netRR >= 2.0 ? 'text-emerald-400' : (netRR >= 1.4 ? 'text-amber-400' : 'text-rose-400')}`;
  }
  safeSetText('heroNetRRSub', netRR >= 2.0 ? '✓ Đạt chuẩn biên lợi nhuận' : (netRR >= 1.4 ? 'Đạt chuẩn lướt sóng' : '⚠️ Kém / Rủi ro cao'));

  const evVal = scen.expectedValuePct !== undefined ? scen.expectedValuePct : 0.0;
  const evEl = document.getElementById('heroEVVal');
  if (evEl) {
    evEl.innerText = `${evVal >= 0 ? '+' : ''}${evVal}%`;
    evEl.className = `text-base sm:text-lg font-black font-mono ${evVal > 0 ? 'text-blue-400' : 'text-rose-400'}`;
  }
  const bCase = scen.bullCase || {};
  const baseCase = scen.baseCase || {};
  const bearCase = scen.bearCase || {};
  safeSetText('heroEVSub', `Bull ${bCase.probability || 0}% • Base ${baseCase.probability || 0}% • Bear ${bearCase.probability || 0}%`);

  // Stop loss / Trailing stop card
  if (isHolding) {
    safeSetText('heroStopLossVal', perspective.trailingStopDisplay || strat.trailingStopDisplay || '-- đ');
    safeSetText('heroHardInvalSub', `Mục tiêu chốt lời: ${perspective.targetDisplay || strat.targetDisplay || '--'}`);
  } else {
    safeSetText('heroStopLossVal', perspective.stopLossDisplay || strat.stopLossDisplay || '-- đ');
    safeSetText('heroHardInvalSub', `Mục tiêu R1: ${perspective.targetDisplay || strat.targetDisplay || '--'}`);
  }

  // 5. Entries Đa Tầng
  const entries = (strat.entries && strat.entries.length > 0) ? strat.entries : (de.entries || []);
  const entryA = entries[0] || {};
  const entryB = entries[1] || {};
  safeSetText('heroEntryAZone', entryA.zone || '-- đ');
  safeSetText('heroEntryAPct', `Tỷ trọng: ${entryA.allocationPct || 0}% NAV • ${entryA.tactic || ''}`);

  safeSetText('heroEntryBZone', entryB.zone || '-- đ');
  safeSetText('heroEntryBPct', `Tỷ trọng: ${entryB.allocationPct || 0}% NAV • ${entryB.tactic || ''}`);

  // 6. TP & Trailing Stop Matrix
  const tp1Obj = targets.tp1 || {};
  const tp2Obj = targets.tp2 || {};
  const tp3Obj = targets.tp3 || {};
  const trailObj = targets.trailingStop || {};

  safeSetText('heroTP1Val', tp1Obj.display || '--');
  safeSetText('heroTP2Val', tp2Obj.display || '--');
  safeSetText('heroTP3Val', tp3Obj.display || '--');
  safeSetText('heroTrailingStopVal', trailObj.display || '-- đ');

  // 7. Ba Câu Hỏi Cốt Tử (The 3 Core Questions)
  const whyListEl = document.getElementById('heroWhyList');
  if (whyListEl) {
    const whyItems = coreQ.why || [];
    if (whyItems.length > 0) {
      whyListEl.innerHTML = whyItems.map(w => `<li class="leading-relaxed">${w}</li>`).join('');
    } else {
      whyListEl.innerHTML = '<li>Đang phân tích các yếu tố cốt lõi...</li>';
    }
  }

  safeSetText('heroWhyNotText', coreQ.whyNotBuyNow || '--');
  safeSetText('heroWhatWillChangeText', coreQ.whatWillChangeSignal || '--');
}

export function renderUnifiedDecisionHero(decisionData, rawData) {
  if (!decisionData) return;
  cachedDecisionData = decisionData;
  cachedRawData = rawData;

  setupInteractiveControls();
  updateControlButtons();

  const de = decisionData;
  const qual = de.quality || {};
  const tim = de.timing || {};

  // Badges: Regime & Data Confidence
  const regEl = document.getElementById('heroRegimeBadge');
  if (regEl) {
    const regName = tim.regime || (rawData && rawData.technicals && rawData.technicals.regime && rawData.technicals.regime.regime) || 'NEUTRAL';
    const regScore = (rawData && rawData.technicals && rawData.technicals.regime && rawData.technicals.regime.score) || 3;
    const regColors = {
      RISK_ON: 'bg-emerald-950 text-emerald-300 border-emerald-700',
      NEUTRAL: 'bg-blue-950 text-blue-300 border-blue-700',
      DEFENSIVE: 'bg-amber-950 text-amber-300 border-amber-700',
      NO_NEW_RISK: 'bg-rose-950 text-rose-300 border-rose-700',
    };
    regEl.className = `flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-lg border font-bold ${regColors[regName] || 'bg-slate-800 text-slate-300 border-slate-700'}`;
    safeSetText('heroRegimeText', `Regime: ${regName} (${regScore}/5)`);

    const regSummary = (rawData && rawData.technicals && rawData.technicals.regime && rawData.technicals.regime.summary) || '';
    const regConditions = (rawData && rawData.technicals && rawData.technicals.regime && rawData.technicals.regime.conditions) || [];
    const regDetailEl = document.getElementById('heroRegimeTooltipDetail');
    if (regDetailEl) {
      if (regConditions.length > 0) {
        regDetailEl.innerHTML = regConditions.map(c => `<div>${c.met ? '✓' : '✗'} ${c.name}: ${c.detail}</div>`).join('');
      } else if (regSummary) {
        regDetailEl.innerText = `• ${regSummary}`;
      }
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

  // Cột Phải: 2 Trụ Cột Độc Lập Quality vs Timing
  const qScoreEl = document.getElementById('heroQualityScore');
  const tScoreEl = document.getElementById('heroTimingScore');

  const getScoreColor = (score) => {
    if (score >= 75) return 'text-emerald-400';
    if (score >= 60) return 'text-blue-400';
    if (score >= 45) return 'text-amber-400';
    return 'text-rose-400';
  };

  if (qScoreEl) {
    qScoreEl.innerText = `${qual.score || 0}/100`;
    qScoreEl.className = `font-mono font-black ${getScoreColor(qual.score || 0)}`;
  }
  safeSetHtml('heroQualityDesc', `<span>${qual.label || '--'} • ROE ${qual.roe || 0}% • FA ${qual.faScore || 0}/100</span>`);

  if (tScoreEl) {
    tScoreEl.innerText = `${tim.score || 0}/100`;
    tScoreEl.className = `font-mono font-black ${getScoreColor(tim.score || 0)}`;
  }
  const ma20Txt = tim.ma20 ? `${formatVND(tim.ma20)} đ` : '--';
  const ema9Txt = tim.ema9 ? ` • EMA9: ${formatVND(tim.ema9)} đ` : '';
  safeSetHtml('heroTimingDesc', `<span>${tim.label || '--'} • RSI ${tim.rsi || 50} • MA20: ${ma20Txt}${ema9Txt}</span>`);

  // Render view đa chiều
  renderMultiPerspectiveView(de, rawData);
}
