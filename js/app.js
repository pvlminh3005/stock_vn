import { formatVND, formatPriceVND, formatStockPrice, formatCompactNumber, initTooltipBoundaryProtection } from './utils.js?v=2.7';
import { getStockDetail, getChartData } from './api.js?v=2.6';
import { initChart, updateChartData } from './modules/chart.js?v=2.6';
import { renderFutureOutlook, renderNewsReferences, copyRiskReportMarkdown } from './modules/riskEngine.js?v=2.6';
import { loadTop10 } from './modules/topScanner.js?v=2.6';

// ==================== 1. TRẠNG THÁI TOÀN CỤC ====================
let currentTicker = 'FPT';
let currentResolution = '1D';

const POPULAR_STOCKS = [
  { ticker: 'FPT', name: 'Tập đoàn FPT', sector: 'Công nghệ thông tin' },
  { ticker: 'MWG', name: 'CTCP Đầu tư Thế Giới Di Động', sector: 'Bán lẻ' },
  { ticker: 'HPG', name: 'Tập đoàn Hòa Phát', sector: 'Thép & VLXD' },
  { ticker: 'TCB', name: 'Ngân hàng Kỹ thương Techcombank', sector: 'Ngân hàng' },
  { ticker: 'MBB', name: 'Ngân hàng Quân đội MB', sector: 'Ngân hàng' },
  { ticker: 'SSI', name: 'CTCP Chứng khoán SSI', sector: 'Chứng khoán' },
  { ticker: 'VCB', name: 'Ngân hàng Ngoại thương Vietcombank', sector: 'Ngân hàng' },
  { ticker: 'VNM', name: 'CTCP Sữa Việt Nam Vinamilk', sector: 'Thực phẩm' },
  { ticker: 'MSN', name: 'CTCP Tập đoàn Masan', sector: 'Tiêu dùng' },
  { ticker: 'DPG', name: 'CTCP Tập đoàn Đạt Phương', sector: 'Hạ tầng & BĐS' },
  { ticker: 'DGW', name: 'CTCP Thế Giới Số Digiworld', sector: 'Phân phối ICT' },
  { ticker: 'VCG', name: 'Tổng CTCP Xuất nhập khẩu VN Vinaconex', sector: 'Xây lắp' },
  { ticker: 'PVD', name: 'Tổng CT Khoan Dầu khí', sector: 'Dầu khí' },
  { ticker: 'POW', name: 'Tổng CT Điện lực Dầu khí', sector: 'Năng lượng' },
  { ticker: 'STB', name: 'Ngân hàng Sacombank', sector: 'Ngân hàng' }
];

const DOM = {
  overlay: document.getElementById("loadingOverlay"),
  overlayTicker: document.getElementById("loadingTicker"),
  alert: document.getElementById("alertBanner"),
  input: document.getElementById("tickerInput"),
  select: document.getElementById("tickerSelect"),
  btnSearch: document.getElementById("searchBtn"),
  searchSuggestions: document.getElementById("searchSuggestions"),
  tabBtns: [
    document.getElementById("tab1Btn"),
    document.getElementById("tab2Btn"),
    document.getElementById("tab3Btn")
  ],
  tabContents: [
    document.getElementById("tab1Content"),
    document.getElementById("tab2Content"),
    document.getElementById("tab3Content")
  ]
};

function safeSetText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = (text !== undefined && text !== null) ? text : "--";
}

function showLoading(ticker) {
  if (DOM.alert) DOM.alert.classList.add("hidden");
  if (DOM.overlayTicker) DOM.overlayTicker.innerText = `ĐANG PHÂN TÍCH: ${ticker.toUpperCase()}...`;
  if (DOM.overlay) DOM.overlay.classList.remove("hidden");
  const icon = document.getElementById("searchIcon");
  if (icon) icon.classList.add("animate-spin");
}

function hideLoading() {
  if (DOM.overlay) DOM.overlay.classList.add("hidden");
  const icon = document.getElementById("searchIcon");
  if (icon) icon.classList.remove("animate-spin");
}

// ==================== 2. ĐIỀU HƯỚNG TAB ====================
export function switchTab(index) {
  DOM.tabBtns.forEach((btn, i) => {
    if (!btn || !DOM.tabContents[i]) return;
    if (i === index) {
      btn.className = "tab-btn py-3 px-4 md:px-5 text-sm tab-active transition flex items-center gap-2 whitespace-nowrap text-blue-400 font-semibold border-b-2 border-blue-600";
      DOM.tabContents[i].classList.remove("hidden");
    } else {
      btn.className = "tab-btn py-3 px-4 md:px-5 text-sm text-slate-400 hover:text-slate-200 transition flex items-center gap-2 whitespace-nowrap";
      DOM.tabContents[i].classList.add("hidden");
    }
  });
}

// ==================== 3. RENDER DỮ LIỆU CỔ PHIẾU ====================
function renderQuickHeader(data) {
  const price = data.price;
  const change = data.priceChange;
  const changePct = data.percentChange;

  safeSetText("displayTicker", data.code);
  safeSetText("companyName", data.name);
  safeSetText("exchangeBadge", data.exchange);
  safeSetText("sectorBadge", `Ngành: ${data.fundamentals?.sector || 'Doanh nghiệp'}`);
  safeSetText("updateTime", `Phiên: ${data.date}`);
  safeSetText("currentPrice", formatVND(price) + " đ");

  const highPrice = data.highest || data.highPrice || data.ceiling || price;
  const lowPrice = data.lowest || data.lowPrice || data.floor || price;

  safeSetText("priceHigh", formatVND(highPrice));
  safeSetText("priceRef", formatVND(data.refPrice));
  safeSetText("priceLow", formatVND(lowPrice));

  const changeBadge = document.getElementById("priceChangeBadge");
  if (changeBadge) {
    changeBadge.innerText = (change >= 0 ? "+" : "") + formatVND(change) + " đ (" + (change >= 0 ? "+" : "") + changePct + "%)";
    changeBadge.className = `inline-block mt-1 text-xs font-bold px-2.5 py-0.5 rounded ${change > 0
      ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
      : (change < 0 ? 'bg-rose-950 text-rose-400 border border-rose-800' : 'bg-amber-950 text-amber-300 border border-amber-800')
      }`;
  }
}

function renderVerdictAndScores(data) {
  const tech = data.technicals || {};
  const fa = data.fundamentals || {};

  safeSetText("verdictText", tech.overallStatus || "Đã phân tích xong dữ liệu.");
  safeSetText("taScoreVal", tech.taScore !== undefined ? `${tech.taScore}/100` : "--");
  safeSetText("faScoreVal", fa.faScore ? `${fa.faScore}/100` : "Dữ liệu chưa ghi nhận");

  const banner = document.getElementById("verdictBanner");
  const icon = document.getElementById("verdictIcon");
  if (banner && icon) {
    if (tech.overallColor === "emerald") {
      banner.className = "mt-4 p-3.5 rounded-xl border border-emerald-800/80 bg-emerald-950/30 flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-lg shadow-emerald-950/50";
      icon.innerHTML = '<i class="fa-solid fa-circle-check text-emerald-400"></i>';
    } else if (tech.overallColor === "rose") {
      banner.className = "mt-4 p-3.5 rounded-xl border border-rose-800/80 bg-rose-950/30 flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-lg shadow-rose-950/50";
      icon.innerHTML = '<i class="fa-solid fa-triangle-exclamation text-rose-400"></i>';
    } else if (tech.overallColor === "blue" || tech.overallColor === "indigo") {
      banner.className = "mt-4 p-3.5 rounded-xl border border-blue-800/80 bg-blue-950/30 flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-lg shadow-blue-950/50";
      icon.innerHTML = '<i class="fa-solid fa-circle-check text-blue-400"></i>';
    } else {
      banner.className = "mt-4 p-3.5 rounded-xl border border-amber-800/80 bg-amber-950/30 flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-lg shadow-amber-950/50";
      icon.innerHTML = '<i class="fa-solid fa-circle-exclamation text-amber-400"></i>';
    }
  }
}

function renderVisualMeters(data) {
  const tech = data.technicals || {};

  // 1. Thước đo RSI
  const rsi = tech.rsi || 50;
  safeSetText("rsiMeterVal", `${rsi} (${rsi > 70 ? 'Quá mua' : (rsi < 35 ? 'Quá bán' : 'Cân bằng')})`);
  const pointer = document.getElementById("rsiPointer");
  if (pointer) {
    const clampedRSI = Math.max(3, Math.min(97, rsi));
    pointer.style.left = `${clampedRSI}%`;
  }

  // 2. Thước đo Dòng tiền & Volume
  const volRatio = tech.volRatio || 1.0;
  const volBadge = document.getElementById("volRatioBadge");
  if (volBadge) {
    volBadge.innerText = `x${volRatio}`;
    volBadge.className = `font-mono font-bold text-xs px-2 py-0.5 rounded ${volRatio >= 1.4 ? 'bg-emerald-950 text-emerald-300 border border-emerald-700' : 'bg-slate-800 text-slate-300'
      }`;
  }
  safeSetText("volSignalText", tech.volSignal || "Thanh khoản bình thường");
  safeSetText("latestVolVal", formatCompactNumber(data.totalVolume) + " cp");

  // 3. Thước đo Lực cầu Mua / Bán chủ động
  const buyRatio = tech.buyRatio !== undefined ? tech.buyRatio : 50;
  const sellRatio = (100 - buyRatio).toFixed(1);
  safeSetText("buyActiveRatioVal", `${buyRatio}% Mua`);

  const buyBar = document.getElementById("buyActiveBar");
  const sellBar = document.getElementById("sellActiveBar");
  if (buyBar && sellBar) {
    buyBar.style.width = `${buyRatio}%`;
    sellBar.style.width = `${sellRatio}%`;
  }
  safeSetText("buyVolTxt", formatCompactNumber(tech.buyActive || 0));
  safeSetText("sellVolTxt", formatCompactNumber(tech.sellActive || 0));

  // 4. Thước đo Sức mạnh giá RS O'Neil so với VN-Index
  const rsData = tech.rs || {};
  const rsScore = (rsData.rsScore !== undefined) ? rsData.rsScore : (rsData.rs_rating !== undefined ? rsData.rs_rating : 50);
  const rsTier = rsData.rsRating || rsData.rating_tier || "Trung bình";
  safeSetText("rsMeterVal", `${rsScore} (${rsTier})`);

  const rsPointer = document.getElementById("rsPointer");
  if (rsPointer) {
    const clampedRS = Math.max(3, Math.min(97, rsScore));
    rsPointer.style.left = `${clampedRS}%`;
  }

  const alpha1M = (rsData.stockAlpha1M !== undefined) ? rsData.stockAlpha1M : rsData.alpha_1m;
  const alpha3M = (rsData.stockAlpha3M !== undefined) ? rsData.stockAlpha3M : rsData.alpha_3m;
  const elAlpha1M = document.getElementById("rsAlpha1M");
  const elAlpha3M = document.getElementById("rsAlpha3M");
  if (elAlpha1M) {
    if (typeof alpha1M === 'number') {
      elAlpha1M.innerText = `${alpha1M >= 0 ? '+' : ''}${alpha1M}%`;
      elAlpha1M.className = `font-bold ${alpha1M >= 0 ? 'text-emerald-400' : 'text-rose-400'}`;
    } else {
      elAlpha1M.innerText = "--";
    }
  }
  if (elAlpha3M) {
    if (typeof alpha3M === 'number') {
      elAlpha3M.innerText = `${alpha3M >= 0 ? '+' : ''}${alpha3M}%`;
      elAlpha3M.className = `font-bold ${alpha3M >= 0 ? 'text-emerald-400' : 'text-rose-400'}`;
    } else {
      elAlpha3M.innerText = "--";
    }
  }
}

function renderActionCards(tech) {
  const techObj = tech || {};
  // A. Card T+
  const tPlus = techObj.tPlus || {};
  const cardT = document.getElementById("cardTPlus");
  const badgeT = document.getElementById("badgeTPlus");
  safeSetText("badgeTPlus", tPlus.decision);
  safeSetText("reasonTPlus", tPlus.reason);
  safeSetText("tEntryVal", tPlus.entry);
  safeSetText("tTargetVal", tPlus.target);
  safeSetText("tStopVal", tPlus.stop);
  safeSetText("tRRVal", `1 : ${tech.rrRatio || 2.0}`);

  if (cardT && badgeT) {
    if (tPlus.type === "success") {
      cardT.className = "p-4 rounded-xl border space-y-2.5 bg-emerald-950/25 border-emerald-800/80 shadow-lg shadow-emerald-950/30";
      badgeT.className = "text-xs font-black px-2.5 py-0.5 rounded border text-emerald-300 bg-emerald-950 border-emerald-700";
    } else if (tPlus.type === "danger") {
      cardT.className = "p-4 rounded-xl border space-y-2.5 bg-rose-950/25 border-rose-800/80";
      badgeT.className = "text-xs font-black px-2.5 py-0.5 rounded border text-rose-300 bg-rose-950 border-rose-700";
    } else {
      cardT.className = "p-4 rounded-xl border space-y-2.5 bg-amber-950/25 border-amber-800/80";
      badgeT.className = "text-xs font-black px-2.5 py-0.5 rounded border text-amber-300 bg-amber-950 border-amber-700";
    }
  }

  // B. Card Trung & Dài Hạn
  const midTerm = techObj.midTerm || {};
  const cardM = document.getElementById("cardMidTerm");
  const badgeM = document.getElementById("badgeMidTerm");
  safeSetText("badgeMidTerm", midTerm.decision);
  safeSetText("reasonMidTerm", midTerm.reason);
  safeSetText("mEntryVal", midTerm.entry);
  safeSetText("mTargetVal", midTerm.target);
  safeSetText("mStopVal", midTerm.stop);

  if (cardM && badgeM) {
    if (midTerm.type === "success") {
      cardM.className = "p-4 rounded-xl border space-y-2.5 bg-emerald-950/25 border-emerald-800/80 shadow-lg shadow-emerald-950/30";
      badgeM.className = "text-xs font-black px-2.5 py-0.5 rounded border text-emerald-300 bg-emerald-950 border-emerald-700";
    } else if (midTerm.type === "danger") {
      cardM.className = "p-4 rounded-xl border space-y-2.5 bg-rose-950/25 border-rose-800/80";
      badgeM.className = "text-xs font-black px-2.5 py-0.5 rounded border text-rose-300 bg-rose-950 border-rose-700";
    } else {
      cardM.className = "p-4 rounded-xl border space-y-2.5 bg-blue-950/25 border-blue-800/80";
      badgeM.className = "text-xs font-black px-2.5 py-0.5 rounded border text-blue-300 bg-blue-950 border-blue-700";
    }
  }
}

function renderFundamentalsTab(data) {
  const fa = data.fundamentals || {};
  const isAudited = fa.isAudited && (fa.pe > 0 || fa.pb > 0 || fa.roe !== 0 || fa.eps > 0);

  safeSetText("peValue", (typeof fa.pe === 'number' && fa.pe > 0) ? fa.pe.toFixed(1) + "x" : "Chưa có");
  safeSetText("pbValue", (typeof fa.pb === 'number' && fa.pb > 0) ? fa.pb.toFixed(1) + "x" : "Chưa có");
  safeSetText("roeValue", (typeof fa.roe === 'number' && fa.roe !== 0) ? fa.roe.toFixed(1) + "%" : "Chưa có");
  safeSetText("epsValue", (fa.eps && fa.eps > 0) ? formatVND(fa.eps) : "Chưa có");
  safeSetText("profitGrowthValue", (typeof fa.profitGrowth === 'number' && fa.profitGrowth !== 0) ? `${fa.profitGrowth > 0 ? '+' : ''}${fa.profitGrowth}%` : "Chưa có");
  safeSetText("debtValue", (typeof fa.debtToEquity === 'number' && fa.debtToEquity > 0) ? fa.debtToEquity.toFixed(2) + "x" : "Chưa có");

  // Card 7: OCF
  const ocfVal = fa.ocf;
  const elOcf = document.getElementById("ocfValue");
  const elOcfSub = document.getElementById("ocfSubTxt");
  if (elOcf) {
    if (typeof ocfVal === 'number' && ocfVal !== 0) {
      elOcf.innerText = `${ocfVal >= 0 ? '+' : ''}${ocfVal.toLocaleString('vi-VN', { maximumFractionDigits: 1 })} tỷ`;
      elOcf.className = `text-lg font-bold font-mono ${ocfVal >= 0 ? 'text-emerald-400' : 'text-rose-400'}`;
    } else {
      elOcf.innerText = "Dữ liệu chưa ghi nhận";
      elOcf.className = "text-sm font-bold font-mono text-slate-400";
    }
  }
  if (elOcfSub) {
    elOcfSub.innerText = fa.ocfStatus || (ocfVal > 0 ? "Dòng tiền kinh doanh thặng dư" : "Theo dõi dòng tiền");
    elOcfSub.className = `text-[10px] mt-0.5 truncate block ${ocfVal < 0 ? 'text-rose-400 font-bold' : 'text-slate-400'}`;
  }

  // Card 8: Biên Lợi Nhuận Gộp / Ròng hoặc NIM / LDR
  const isBank = (typeof fa.nim === 'number' && fa.nim > 0) || (typeof fa.ldr === 'number' && fa.ldr > 0);
  const elMarginLabel = document.getElementById("marginLabel");
  const elMarginVal = document.getElementById("marginValue");
  const elMarginSub = document.getElementById("marginSub");

  if (isBank) {
    if (elMarginLabel) elMarginLabel.innerText = "Biên Lãi Thuần (NIM) Ngân hàng";
    if (elMarginVal) {
      elMarginVal.innerText = `${fa.nim.toFixed(2)}%`;
      elMarginVal.className = "text-lg font-bold font-mono text-cyan-400";
    }
    if (elMarginSub) {
      elMarginSub.innerText = `LDR: ${fa.ldr ? fa.ldr.toFixed(1) + '%' : 'Chuẩn SBV'}`;
    }
  } else {
    if (elMarginLabel) elMarginLabel.innerText = "Biên LN Gộp (Gross Margin)";
    if (elMarginVal) {
      if (typeof fa.grossMargin === 'number' && fa.grossMargin > 0) {
        elMarginVal.innerText = `${fa.grossMargin.toFixed(1)}%`;
        elMarginVal.className = "text-lg font-bold font-mono text-amber-400";
      } else {
        elMarginVal.innerText = "Dữ liệu chưa ghi nhận";
        elMarginVal.className = "text-sm font-bold font-mono text-slate-400";
      }
    }
    if (elMarginSub) {
      if (typeof fa.netMargin === 'number' && fa.netMargin !== 0) {
        elMarginSub.innerText = `Biên ròng: ${fa.netMargin.toFixed(1)}% (Lãi vay: ${fa.interestCoverage ? fa.interestCoverage.toFixed(1) + 'x' : '--'})`;
      } else {
        elMarginSub.innerText = "Biên LN ròng sau thuế";
      }
    }
  }

  const auditBadge = document.getElementById("auditBadge");
  if (auditBadge) {
    if (isAudited) {
      auditBadge.className = "text-[11px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800";
      auditBadge.textContent = "✓ BCTC Kiểm Toán Thực Tế";
    } else {
      auditBadge.className = "text-[11px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700";
      auditBadge.textContent = "⏳ Dữ Liệu BCTC Đang Cập Nhật";
    }
  }

  safeSetText("companySummaryTxt", fa.summary || "Thông tin doanh nghiệp đang được cập nhật từ cổng công bố thông tin.");

  // Render Khung Định Lượng & Tin tức đa nguồn
  renderFutureOutlook(data.futureOutlook, data.riskEngine, data);
  renderNewsReferences(data.news);
}

function renderTechnicalsTab(data) {
  const tech = data.technicals || {};
  safeSetText("ma20Val", formatVND(tech.ma20) + " đ");
  safeSetText("ma50Val", formatVND(tech.ma50) + " đ");
  safeSetText("supportVal", formatVND(tech.support) + " đ");
  safeSetText("resistanceVal", formatVND(tech.resistance) + " đ");

  const maTrendEl = document.getElementById("maTrend");
  if (maTrendEl) {
    const isAboveMA = data.price >= tech.ma20;
    maTrendEl.innerText = isAboveMA ? "✓ Giữ trên MA20" : "✗ Dưới MA20";
    maTrendEl.className = `text-xs font-bold mt-1 ${isAboveMA ? 'text-emerald-400' : 'text-amber-400'}`;
  }

  const tPlus = tech.tPlus || {};
  safeSetText("tEntry", tPlus.entry || "--");
  safeSetText("tTarget", tPlus.target || "--");
  safeSetText("tStop", tPlus.stop || "--");
  safeSetText("tPlusNotes", tPlus.reason || "--");

  // Multi-Timeframe Trend Confluence
  const mtf = tech.multiTimeframe || {};
  const d1Ma = mtf.daily_ma20 || tech.ma20;
  const w1Ma = mtf.wMa10 || mtf.weekly_ma10;
  safeSetText("multiTfDailyMA20", (d1Ma ? formatVND(d1Ma) : "--") + " đ");
  safeSetText("multiTfWeeklyMA10", (w1Ma ? formatVND(w1Ma) : "--") + " đ");

  const d1TrendTxt = mtf.trend_d1 || (mtf.d1Bullish !== undefined ? (mtf.d1Bullish ? "✓ Trên MA20 (Uptrend)" : "✗ Dưới MA20 (Downtrend)") : "--");
  const w1TrendTxt = mtf.trend_w1 || (mtf.w1Bullish !== undefined ? (mtf.w1Bullish ? "✓ Trên MA10 Tuần" : "✗ Dưới MA10 Tuần") : "--");
  safeSetText("multiTfDailyTrend", d1TrendTxt);
  safeSetText("multiTfWeeklyTrend", w1TrendTxt);
  safeSetText("multiTfConfluenceVal", mtf.confluence || "--");
  safeSetText("multiTfDesc", mtf.description || mtf.action_note || "--");

  const mtfBadge = document.getElementById("multiTfBadge");
  if (mtfBadge) {
    mtfBadge.innerText = mtf.confluence || "Chưa xác định";
    const confLower = (mtf.confluence || "").toLowerCase();
    if (confLower.includes("uptrend") || confLower.includes("đồng thuận tăng")) {
      mtfBadge.className = "text-xs font-bold px-2.5 py-1 rounded-md bg-emerald-950 text-emerald-300 border border-emerald-700 font-mono";
    } else if (confLower.includes("downtrend") || confLower.includes("đồng thuận giảm")) {
      mtfBadge.className = "text-xs font-bold px-2.5 py-1 rounded-md bg-rose-950 text-rose-300 border border-rose-700 font-mono";
    } else {
      mtfBadge.className = "text-xs font-bold px-2.5 py-1 rounded-md bg-amber-950 text-amber-300 border border-amber-700 font-mono";
    }
  }

  // Position Sizing Guide
  const pos = tech.positionSizing || {};
  const maxNav = pos.maxNavPct !== undefined ? pos.maxNavPct : pos.max_nav_pct;
  const pilotNav = pos.pilotNavPct !== undefined ? pos.pilotNavPct : pos.pilot_pct;
  const pyramidNav = pos.pyramidNavPct !== undefined ? pos.pyramidNavPct : pos.pyramid_pct;
  const riskPct = pos.downsideRiskPct !== undefined ? pos.downsideRiskPct : pos.stop_loss_pct;
  const guideTxt = pos.guide || pos.recommendation || "--";

  safeSetText("posMaxNav", maxNav !== undefined ? `${maxNav}% NAV` : "--");
  safeSetText("posPilotNav", pilotNav !== undefined ? `${pilotNav}% NAV` : "--");
  safeSetText("posPyramidNav", pyramidNav !== undefined ? `${pyramidNav}% NAV` : "--");
  safeSetText("posMaxRiskPct", riskPct !== undefined ? `-${riskPct}%` : "--");
  safeSetText("posRecommendation", guideTxt);
}

// ==================== 4. CONTROLLER TẢI DỮ LIỆU ====================
export async function loadStock(ticker) {
  if (!ticker) return;
  const sym = ticker.trim().toUpperCase();
  currentTicker = sym;
  showLoading(sym);

  try {
    const resSelect = document.getElementById("chartTimeframeSelect");
    if (resSelect) currentResolution = resSelect.value || '1D';

    const data = await getStockDetail(sym, currentResolution);
    renderQuickHeader(data);
    renderVerdictAndScores(data);
    renderVisualMeters(data);
    renderActionCards(data.technicals);
    renderFundamentalsTab(data);
    renderTechnicalsTab(data);
    updateChartData(data.candles, currentResolution);
  } catch (err) {
    console.error("Lỗi khi load mã:", err);
    if (DOM.alert) {
      DOM.alert.innerText = `Lỗi tải dữ liệu cho mã ${sym}: ${err.message}`;
      DOM.alert.classList.remove("hidden");
    }
  } finally {
    hideLoading();
  }
}

// ==================== 5. AUTOCOMPLETE & GỢI Ý ====================
function setupAutocomplete() {
  if (!DOM.input || !DOM.searchSuggestions) return;

  DOM.input.addEventListener("input", (e) => {
    const val = e.target.value.trim().toUpperCase();
    if (!val) {
      DOM.searchSuggestions.classList.add("hidden");
      return;
    }

    const matches = POPULAR_STOCKS.filter(s => s.ticker.includes(val) || s.name.toUpperCase().includes(val));
    if (matches.length === 0) {
      DOM.searchSuggestions.classList.add("hidden");
      return;
    }

    DOM.searchSuggestions.innerHTML = matches.map(s => `
      <div class="p-2.5 hover:bg-slate-800 cursor-pointer flex items-center justify-between transition suggestion-item" data-ticker="${s.ticker}">
        <div class="flex items-center gap-2 pointer-events-none">
          <span class="font-mono font-bold text-blue-400">${s.ticker}</span>
          <span class="text-slate-300 truncate max-w-[180px]">${s.name}</span>
        </div>
        <span class="text-[10px] text-slate-500 font-mono pointer-events-none">${s.sector}</span>
      </div>
    `).join("");

    DOM.searchSuggestions.classList.remove("hidden");
  });

  DOM.searchSuggestions.addEventListener("mousedown", (e) => {
    const item = e.target.closest(".suggestion-item");
    if (item) {
      e.preventDefault();
      const t = item.getAttribute("data-ticker");
      if (t) {
        if (DOM.input) DOM.input.value = t;
        DOM.searchSuggestions.classList.add("hidden");
        loadStock(t);
      }
    }
  });

  document.addEventListener("click", (e) => {
    if (!DOM.input.contains(e.target) && !DOM.searchSuggestions.contains(e.target)) {
      DOM.searchSuggestions.classList.add("hidden");
    }
  });
}

// ==================== 6. SỰ KIỆN GIAO DIỆN ====================
function initEvents() {
  DOM.tabBtns.forEach((btn, idx) => {
    btn?.addEventListener("click", () => switchTab(idx));
  });

  const doSearch = () => {
    const val = DOM.input?.value.trim().toUpperCase();
    if (val) {
      DOM.searchSuggestions?.classList.add("hidden");
      loadStock(val);
    }
  };

  DOM.btnSearch?.addEventListener("click", (e) => {
    e.preventDefault();
    doSearch();
  });

  DOM.input?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      doSearch();
    }
  });

  DOM.select?.addEventListener("change", (e) => {
    const val = e.target.value;
    if (val) {
      if (DOM.input) DOM.input.value = val;
      DOM.searchSuggestions?.classList.add("hidden");
      loadStock(val);
    }
  });

  document.querySelectorAll(".chip-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const t = btn.getAttribute("data-ticker");
      if (t) {
        if (DOM.input) DOM.input.value = t;
        DOM.searchSuggestions?.classList.add("hidden");
        loadStock(t);
      }
    });
  });

  const tfSelect = document.getElementById("chartTimeframeSelect");
  if (tfSelect) {
    tfSelect.addEventListener("change", async (e) => {
      currentResolution = e.target.value;
      try {
        const chartRes = await getChartData(currentTicker, currentResolution);
        if (chartRes && chartRes.candles) {
          updateChartData(chartRes.candles, currentResolution);
        }
      } catch (err) {
        console.error("Lỗi đổi khung thời gian biểu đồ:", err);
      }
    });
  }
}

// ==================== 7. KHỞI CHẠY ỨNG DỤNG ====================
function initApp() {
  initChart();
  setupAutocomplete();
  initEvents();
  initTooltipBoundaryProtection();
  loadTop10((t) => {
    if (DOM.input) DOM.input.value = t;
    loadStock(t);
    switchTab(0);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
  loadStock("FPT");
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}
