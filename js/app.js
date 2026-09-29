import { formatVND, formatCompactNumber } from './utils.js';
import { getTop10Stocks, getStockDetail, getChartData } from './api.js';

// ==================== 1. BIẾN TOÀN CỤC & BIỂU ĐỒ ====================
let chart = null;
let candleSeries = null;
let volumeSeries = null;
let ma20Series = null;
let ma50Series = null;
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
}

function hideLoading() {
  if (DOM.overlay) DOM.overlay.classList.add("hidden");
}

// ==================== 2. KHỞI TẠO BIỂU ĐỒ LIGHTWEIGHT CHARTS ====================
function initChart() {
  const container = document.getElementById("chartContainer");
  if (!container || !window.LightweightCharts) return;

  container.innerHTML = "";

  chart = window.LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: 360,
    layout: {
      background: { color: '#090d16' },
      textColor: '#94a3b8',
      fontSize: 11,
      fontFamily: 'ui-sans-serif, system-ui, sans-serif'
    },
    grid: {
      vertLines: { color: '#1e293b' },
      horzLines: { color: '#1e293b' }
    },
    crosshair: {
      mode: window.LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: '#475569', width: 1, style: 2 },
      horzLine: { color: '#475569', width: 1, style: 2 }
    },
    rightPriceScale: {
      borderColor: '#334155',
      scaleMargins: { top: 0.1, bottom: 0.25 }
    },
    timeScale: {
      borderColor: '#334155',
      timeVisible: true,
      secondsVisible: false
    }
  });

  // Series 1: Candlestick (Nến)
  candleSeries = chart.addCandlestickSeries({
    upColor: '#10b981',
    downColor: '#ef4444',
    borderUpColor: '#10b981',
    borderDownColor: '#ef4444',
    wickUpColor: '#10b981',
    wickDownColor: '#ef4444'
  });

  // Series 2: Volume Histogram (Cột khối lượng phía dưới)
  volumeSeries = chart.addHistogramSeries({
    color: '#3b82f6',
    priceFormat: { type: 'volume' },
    priceScaleId: '', // Overlay độc lập
    scaleMargins: { top: 0.8, bottom: 0 }
  });

  // Series 3 & 4: Đường MA20 & MA50
  ma20Series = chart.addLineSeries({
    color: '#3b82f6',
    lineWidth: 1.5,
    title: 'MA20'
  });

  ma50Series = chart.addLineSeries({
    color: '#f59e0b',
    lineWidth: 1.5,
    title: 'MA50'
  });

  // Sự kiện di chuột cập nhật Legend
  chart.subscribeCrosshairMove(param => {
    if (!param.time || !param.seriesData.get(candleSeries)) {
      return;
    }
    const cData = param.seriesData.get(candleSeries);
    const vData = param.seriesData.get(volumeSeries);
    if (cData) {
      safeSetText("legOpen", formatVND(cData.open));
      safeSetText("legHigh", formatVND(cData.high));
      safeSetText("legLow", formatVND(cData.low));
      safeSetText("legClose", formatVND(cData.close));
    }
    if (vData) {
      safeSetText("legVol", formatCompactNumber(vData.value));
    }
  });

  // Tự động resize khi màn hình thay đổi kích thước
  window.addEventListener('resize', () => {
    if (chart && container) {
      chart.applyOptions({ width: container.clientWidth });
    }
  });
}

function updateChartData(candles, resolution = '1D') {
  if (!chart || !candleSeries || !candles || candles.length === 0) return;

  const isIntraday = resolution === '1H' || resolution === '30' || resolution === '15' || resolution === '5';
  chart.applyOptions({
    timeScale: {
      timeVisible: isIntraday,
      secondsVisible: false
    }
  });

  const candleData = [];
  const volData = [];
  const ma20Data = [];
  const ma50Data = [];

  const closePrices = candles.map(c => c.close);

  for (let i = 0; i < candles.length; i++) {
    const item = candles[i];
    candleData.push({
      time: item.time,
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close
    });

    volData.push({
      time: item.time,
      value: item.volume,
      color: item.close >= item.open ? 'rgba(16, 185, 129, 0.45)' : 'rgba(239, 68, 68, 0.45)'
    });

    // Tính MA20
    if (i >= 19) {
      const slice20 = closePrices.slice(i - 19, i + 1);
      const avg20 = slice20.reduce((a, b) => a + b, 0) / 20;
      ma20Data.push({ time: item.time, value: avg20 });
    }

    // Tính MA50
    if (i >= 49) {
      const slice50 = closePrices.slice(i - 49, i + 1);
      const avg50 = slice50.reduce((a, b) => a + b, 0) / 50;
      ma50Data.push({ time: item.time, value: avg50 });
    }
  }

  candleSeries.setData(candleData);
  volumeSeries.setData(volData);
  ma20Series.setData(ma20Data);
  ma50Series.setData(ma50Data);

  chart.timeScale().fitContent();

  // Cập nhật legend ban đầu với cây nến gần nhất
  const lastC = candles[candles.length - 1];
  safeSetText("legOpen", formatVND(lastC.open));
  safeSetText("legHigh", formatVND(lastC.high));
  safeSetText("legLow", formatVND(lastC.low));
  safeSetText("legClose", formatVND(lastC.close));
  safeSetText("legVol", formatCompactNumber(lastC.volume));
}

// ==================== 3. TAB CONTROLLER ====================
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

// ==================== 4. RENDER CÁC THÀNH PHẦN GIAO DIỆN ====================
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

  // Giữ fallback cho ID cũ nếu có
  safeSetText("priceCeiling", formatVND(highPrice));
  safeSetText("priceFloor", formatVND(lowPrice));

  const changeBadge = document.getElementById("priceChangeBadge");
  if (changeBadge) {
    changeBadge.innerText = (change >= 0 ? "+" : "") + formatVND(change) + " đ (" + (change >= 0 ? "+" : "") + changePct + "%)";
    changeBadge.className = `inline-block mt-1 text-xs font-bold px-2.5 py-0.5 rounded ${
      change > 0
        ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
        : (change < 0 ? 'bg-rose-950 text-rose-400 border border-rose-800' : 'bg-amber-950 text-amber-300 border border-amber-800')
    }`;
  }
}

function renderVerdictAndScores(data) {
  const tech = data.technicals || {};
  const fa = data.fundamentals || {};

  safeSetText("verdictText", tech.overallStatus || "Đã phân tích xong dữ liệu.");
  safeSetText("taScoreVal", tech.taScore || "--");
  safeSetText("faScoreVal", fa.faScore || "--");

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
    volBadge.className = `font-mono font-bold text-xs px-2 py-0.5 rounded ${
      volRatio >= 1.4 ? 'bg-emerald-950 text-emerald-300 border border-emerald-700' : 'bg-slate-800 text-slate-300'
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
}

function renderActionCards(tech) {
  // A. Card T+
  const tPlus = tech.tPlus || {};
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
  const midTerm = tech.midTerm || {};
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
  const price = data.price;

  safeSetText("peValue", typeof fa.pe === 'number' ? fa.pe.toFixed(1) + "x" : "--");
  safeSetText("pbValue", typeof fa.pb === 'number' ? fa.pb.toFixed(1) + "x" : "--");
  safeSetText("roeValue", typeof fa.roe === 'number' ? fa.roe.toFixed(1) + "%" : "--");
  safeSetText("epsValue", fa.eps ? formatVND(fa.eps) : "--");
  safeSetText("profitGrowthValue", typeof fa.profitGrowth === 'number' ? `${fa.profitGrowth > 0 ? '+' : ''}${fa.profitGrowth}%` : "--");
  safeSetText("debtValue", typeof fa.debtToEquity === 'number' ? fa.debtToEquity.toFixed(2) + "x" : "--");

  safeSetText("companySummaryTxt", fa.summary || "Thông tin doanh nghiệp đang được cập nhật.");

  safeSetText("buyZone", `${formatVND(price * 0.94)} - ${formatVND(price * 0.98)}`);
  safeSetText("tpLong", `${formatVND(price * 1.18)} - ${formatVND(price * 1.25)}`);
  safeSetText("slLong", formatVND(price * 0.92));

  // Render news
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
}

function renderNewsReferences(newsList) {
  const container = document.getElementById("newsListContainer");
  if (!container) return;
  container.innerHTML = "";

  if (!newsList || newsList.length === 0) {
    container.innerHTML = `<div class="text-xs text-slate-500">Chưa có thông tin sự kiện mới.</div>`;
    return;
  }

  newsList.forEach(item => {
    const div = document.createElement("div");
    div.className = "p-3 bg-slate-950/80 border border-slate-800 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-2 hover:border-slate-700 transition";
    div.innerHTML = `
      <div class="space-y-1">
        <a href="${item.url}" target="_blank" rel="noopener noreferrer" class="text-xs md:text-sm font-semibold text-slate-200 hover:text-blue-400 transition flex items-center gap-1.5">
          <i class="fa-solid fa-arrow-up-right-from-square text-xs text-slate-500"></i> ${item.title}
        </a>
        <div class="text-[11px] text-slate-500">Nguồn: ${item.source} • Ngày: ${item.date}</div>
      </div>
      <a href="${item.url}" target="_blank" rel="noopener noreferrer" class="text-[11px] text-blue-400 hover:underline self-start sm:self-auto whitespace-nowrap font-medium">
        Xem báo cáo <i class="fa-solid fa-chevron-right text-[9px]"></i>
      </a>
    `;
    container.appendChild(div);
  });
}

// ==================== 5. CONTROLLER TẢI DỮ LIỆU CHÍNH ====================
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

export async function loadTop10() {
  try {
    const result = await getTop10Stocks();
    safeSetText("topUpdateDate", `Cập nhật: ${result.date}`);
    const tbody = document.getElementById("topTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    result.data.forEach((item, idx) => {
      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-800/60 transition cursor-pointer";
      tr.innerHTML = `
        <td class="py-3 px-3 font-mono font-bold text-white flex items-center gap-2">
          <span class="w-5 h-5 flex items-center justify-center rounded bg-slate-800 text-[10px] text-slate-400 font-bold">${idx + 1}</span>
          <span class="text-blue-400 font-black text-sm">${item.ticker}</span>
        </td>
        <td class="py-3 px-3 text-slate-300 font-medium text-xs max-w-[150px] truncate">${item.name || item.ticker}</td>
        <td class="py-3 px-3 font-mono font-semibold text-slate-100">${formatVND(item.price)} đ</td>
        <td class="py-3 px-3 font-mono font-bold ${item.pctChange >= 0 ? 'text-emerald-400' : 'text-rose-400'}">${item.change}</td>
        <td class="py-3 px-3">
          <span class="px-2 py-0.5 rounded text-[11px] font-mono font-bold ${item.volRatio >= 1.4 ? 'bg-emerald-950 text-emerald-300 border border-emerald-700' : 'bg-slate-800 text-slate-300'}">
            ${item.volSignal}
          </span>
        </td>
        <td class="py-3 px-3 font-mono text-slate-300">${item.rsi}</td>
        <td class="py-3 px-3 text-slate-400 text-xs font-mono">${item.trend}</td>
        <td class="py-3 px-3 font-mono text-emerald-400 font-medium">${item.entry}</td>
        <td class="py-3 px-3 font-mono text-blue-400 font-bold">${item.target}</td>
        <td class="py-3 px-3 text-center">
          <button data-ticker="${item.ticker}" class="view-detail-btn px-2.5 py-1 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-lg transition whitespace-nowrap shadow-md shadow-blue-600/20">
            Xem chi tiết
          </button>
        </td>
      `;
      tbody.appendChild(tr);
    });

    document.querySelectorAll(".view-detail-btn").forEach(button => {
      button.addEventListener("click", (e) => {
        const t = e.target.getAttribute("data-ticker");
        if (DOM.input) DOM.input.value = t;
        loadStock(t);
        switchTab(1);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      });
    });
  } catch (err) {
    console.error("Lỗi tải Top 10:", err);
  }
}

// ==================== 6. AUTOCOMPLETE & GỢI Ý ====================
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
        <div class="flex items-center gap-2">
          <span class="font-mono font-bold text-blue-400">${s.ticker}</span>
          <span class="text-slate-300 truncate max-w-[180px]">${s.name}</span>
        </div>
        <span class="text-[10px] text-slate-500 font-mono">${s.sector}</span>
      </div>
    `).join("");

    DOM.searchSuggestions.classList.remove("hidden");

    document.querySelectorAll(".suggestion-item").forEach(item => {
      item.addEventListener("click", () => {
        const t = item.getAttribute("data-ticker");
        DOM.input.value = t;
        DOM.searchSuggestions.classList.add("hidden");
        loadStock(t);
      });
    });
  });

  // Đóng dropdown khi click ra ngoài
  document.addEventListener("click", (e) => {
    if (!DOM.input.contains(e.target) && !DOM.searchSuggestions.contains(e.target)) {
      DOM.searchSuggestions.classList.add("hidden");
    }
  });
}

// ==================== 7. SỰ KIỆN & KHỞI CHẠY ====================
function initEvents() {
  DOM.tabBtns.forEach((btn, index) => {
    if (btn) btn.addEventListener("click", () => switchTab(index));
  });

  if (DOM.btnSearch) {
    DOM.btnSearch.addEventListener("click", () => {
      if (DOM.input && DOM.input.value) loadStock(DOM.input.value);
    });
  }

  if (DOM.input) {
    DOM.input.addEventListener("keypress", (e) => {
      if (e.key === "Enter" && DOM.input.value) {
        DOM.searchSuggestions?.classList.add("hidden");
        loadStock(DOM.input.value);
      }
    });
  }

  if (DOM.select) {
    DOM.select.addEventListener("change", (e) => {
      if (e.target.value) {
        if (DOM.input) DOM.input.value = e.target.value;
        loadStock(e.target.value);
      }
    });
  }

  // Quick Chips
  document.querySelectorAll(".chip-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const t = btn.getAttribute("data-ticker");
      if (DOM.input) DOM.input.value = t;
      loadStock(t);
    });
  });

  // Khung thời gian biểu đồ nến (Timeframe dropdown)
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

// Khởi chạy ứng dụng
initChart();
setupAutocomplete();
initEvents();
loadTop10();
// Tải trước mã mặc định FPT
loadStock("FPT");