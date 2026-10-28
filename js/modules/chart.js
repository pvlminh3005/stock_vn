import { formatStockPrice, formatCompactNumber } from '../utils.js?v=4.0';
import {
  TPLUS_SUPERTREND_PERIOD,
  TPLUS_SUPERTREND_MULTIPLIER,
  ADX_PERIOD,
  ADX_SIDEWAY_THRESHOLD
} from '../constants/indicators.js?v=4.0';

let chart = null;
let candleSeries = null;
let volumeSeries = null;
let ma20Series = null;
let ma50Series = null;
let superTrendCloudPrimitive = null;

// Quản lý Price Lines & Observers tránh memory leak
let activePriceLines = [];
let cachedPriceLinesConfig = null;
let chartResizeObserver = null;
let isResizeListenerAttached = false;

// State for SuperTrend Ribbon Indicator (ATR Volatility Band & Directional Trend)
let isSuperTrendEnabled = true;
let cachedCandles = [];
let cachedResolution = '1D';
let isSuperTrendToggleAttached = false;

/**
 * Helper: Vẽ hình chữ nhật bo góc trên Canvas 2D
 */
function drawRoundedRect(ctx, x, y, width, height, radius) {
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.lineTo(x + width - radius, y);
  ctx.quadraticCurveTo(x + width, y, x + width, y + radius);
  ctx.lineTo(x + width, y + height - radius);
  ctx.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  ctx.lineTo(x + radius, y + height);
  ctx.quadraticCurveTo(x, y + height, x, y + height - radius);
  ctx.lineTo(x, y + radius);
  ctx.quadraticCurveTo(x, y, x + radius, y);
  ctx.closePath();
}

/**
 * SuperTrend Cloud Primitive (TradingView Lightweight Charts Series Primitive)
 * - Layer đáy (zOrder: 'bottom'): Vẽ "VÙNG XANH - VÙNG HỒNG" (Filled Cloud) với độ mờ tinh chỉnh (opacity 0.20)
 *   giúp thân nến xanh biển / đỏ hiển thị nổi bật, tương phản rõ nét.
 * - Layer đỉnh (zOrder: 'top'): Vẽ trực tiếp mũi tên đề xuất (Xanh lá / Đỏ) và nhãn MUA/BÁN
 *   bọc trong ô màu tương ứng với chữ trắng (#ffffff) chuẩn phong cách STB.
 */
class SuperTrendCloudPrimitive {
  constructor() {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
    this._cloudData = [];
    this._signals = [];
  }

  attached({ chart, series, requestUpdate }) {
    this._chart = chart;
    this._series = series;
    this._requestUpdate = requestUpdate;
  }

  detached() {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
  }

  setData(cloudData = [], signals = []) {
    this._cloudData = cloudData || [];
    this._signals = signals || [];
    if (this._requestUpdate) {
      this._requestUpdate();
    }
  }

  updateAllViews() {}

  paneViews() {
    return [
      {
        zOrder: () => 'bottom',
        renderer: () => ({
          draw: (target) => {
            const drawCloud = (ctx) => this._drawCloud(ctx);
            if (target && typeof target.useMediaCoordinateSpace === 'function') {
              target.useMediaCoordinateSpace(({ context: ctx }) => drawCloud(ctx));
            } else if (target && target.context) {
              drawCloud(target.context);
            }
          }
        })
      },
      {
        zOrder: () => 'top',
        renderer: () => ({
          draw: (target) => {
            const drawSignals = (ctx) => this._drawSignals(ctx);
            if (target && typeof target.useMediaCoordinateSpace === 'function') {
              target.useMediaCoordinateSpace(({ context: ctx }) => drawSignals(ctx));
            } else if (target && target.context) {
              drawSignals(target.context);
            }
          }
        })
      }
    ];
  }

  _drawCloud(ctx) {
    if (!this._chart || !this._series || !this._cloudData || this._cloudData.length === 0) return;

    const timeScale = this._chart.timeScale();
    const series = this._series;

    // Chuyển đổi dữ liệu chuỗi nến sang tọa độ pixel trên canvas
    const points = [];
    for (let i = 0; i < this._cloudData.length; i++) {
      const item = this._cloudData[i];
      const x = timeScale.timeToCoordinate(item.time);
      const yUpper = series.priceToCoordinate(item.upper);
      const yLower = series.priceToCoordinate(item.lower);
      if (x !== null && yUpper !== null && yLower !== null) {
        points.push({ x, yUpper, yLower, trend: item.trend });
      }
    }

    if (points.length < 2) return;

    // Nhóm thành các đoạn liên tục có cùng xu hướng (Vùng Xanh / Vùng Hồng)
    let currentSegment = [points[0]];
    for (let i = 1; i < points.length; i++) {
      const p = points[i];
      const prev = points[i - 1];

      if (p.trend === prev.trend) {
        currentSegment.push(p);
      } else {
        // Nối điểm giao thoa để dải mây đổi màu mượt mà không bị đứt đoạn
        currentSegment.push(p);
        this._renderSegment(ctx, currentSegment, prev.trend);
        currentSegment = [prev, p];
      }
    }
    if (currentSegment.length >= 2) {
      this._renderSegment(ctx, currentSegment, currentSegment[currentSegment.length - 1].trend);
    }
  }

  _renderSegment(ctx, seg, trend) {
    if (!seg || seg.length < 2) return;
    const isBull = trend === 1;

    ctx.save();

    // 1. Tô vùng mây (Cloud Polygon) - Giảm opacity xuống 0.20 để nến xanh biển / đỏ nổi bật
    ctx.beginPath();
    ctx.moveTo(seg[0].x, seg[0].yUpper);
    for (let i = 1; i < seg.length; i++) {
      ctx.lineTo(seg[i].x, seg[i].yUpper);
    }
    for (let i = seg.length - 1; i >= 0; i--) {
      ctx.lineTo(seg[i].x, seg[i].yLower);
    }
    ctx.closePath();

    // Vùng Xanh mướt dịu mắt hoặc Vùng Hồng êm ái
    ctx.fillStyle = isBull ? 'rgba(74, 222, 128, 0.20)' : 'rgba(244, 114, 182, 0.20)';
    ctx.fill();

    // 2. Viền ngoài trên & dưới mềm mại
    ctx.lineWidth = 1.2;
    ctx.strokeStyle = isBull ? 'rgba(34, 197, 94, 0.65)' : 'rgba(236, 72, 153, 0.65)';

    // Viền trên
    ctx.beginPath();
    ctx.moveTo(seg[0].x, seg[0].yUpper);
    for (let i = 1; i < seg.length; i++) {
      ctx.lineTo(seg[i].x, seg[i].yUpper);
    }
    ctx.stroke();

    // Viền dưới
    ctx.beginPath();
    ctx.moveTo(seg[0].x, seg[0].yLower);
    for (let i = 1; i < seg.length; i++) {
      ctx.lineTo(seg[i].x, seg[i].yLower);
    }
    ctx.stroke();

    ctx.restore();
  }

  _drawSignals(ctx) {
    if (!this._chart || !this._series || !this._signals || this._signals.length === 0) return;

    const timeScale = this._chart.timeScale();
    const series = this._series;

    ctx.save();
    ctx.font = 'bold 10px ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';

    for (let i = 0; i < this._signals.length; i++) {
      const s = this._signals[i];
      const x = timeScale.timeToCoordinate(s.time);
      if (x === null) continue;

      const isBuy = s.type === 'BUY';
      const labelText = s.text || (isBuy ? 'MUA' : 'BÁN');
      const textMetrics = ctx.measureText(labelText);
      const textW = textMetrics.width;

      const boxHeight = 18;
      const boxWidth = Math.max(textW + 12, 44);
      const boxX = x - boxWidth / 2;

      if (isBuy || s.type === 'WAIT_SIDEWAY') {
        const isSideway = s.type === 'WAIT_SIDEWAY';
        const priceVal = s.low !== undefined ? s.low : s.price;
        const yBase = series.priceToCoordinate(priceVal);
        if (yBase === null) continue;

        const arrowTipY = yBase + 4;
        const arrowBaseY = yBase + 11;
        const boxY = yBase + 13;

        // 1. Mũi tên tam giác
        ctx.beginPath();
        ctx.moveTo(x, arrowTipY);
        ctx.lineTo(x - 5, arrowBaseY);
        ctx.lineTo(x + 5, arrowBaseY);
        ctx.closePath();
        ctx.fillStyle = isSideway ? '#64748b' : '#16a34a';
        ctx.fill();
        ctx.strokeStyle = isSideway ? '#475569' : '#15803d';
        ctx.lineWidth = 1;
        ctx.stroke();

        // 2. Ô chữ nhật bo góc
        drawRoundedRect(ctx, boxX, boxY, boxWidth, boxHeight, 3);
        ctx.fillStyle = isSideway ? '#475569' : '#16a34a';
        ctx.shadowColor = 'rgba(0, 0, 0, 0.45)';
        ctx.shadowBlur = 4;
        ctx.shadowOffsetY = 1;
        ctx.fill();

        ctx.shadowColor = 'transparent';
        ctx.strokeStyle = isSideway ? '#94a3b8' : '#22c55e';
        ctx.lineWidth = 1;
        ctx.stroke();

        // 3. Text chữ màu trắng
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(labelText, x, boxY + boxHeight / 2);
      } else if (s.type === 'TAKE_PROFIT') {
        // Tín hiệu CHỐT LỜI CHỦ ĐỘNG (Take Profit): Mũi tên hổ phách / vàng cam trỏ xuống đỉnh nến, ô chữ nhật bo góc nền hổ phách chữ trắng
        const priceVal = s.high !== undefined ? s.high : s.price;
        const yBase = series.priceToCoordinate(priceVal);
        if (yBase === null) continue;

        const arrowTipY = yBase - 4;
        const arrowBaseY = yBase - 11;
        const boxY = yBase - 13 - boxHeight;

        // 1. Mũi tên tam giác màu vàng cam / hổ phách
        ctx.beginPath();
        ctx.moveTo(x, arrowTipY);
        ctx.lineTo(x - 5, arrowBaseY);
        ctx.lineTo(x + 5, arrowBaseY);
        ctx.closePath();
        ctx.fillStyle = '#d97706';
        ctx.fill();
        ctx.strokeStyle = '#b45309';
        ctx.lineWidth = 1;
        ctx.stroke();

        // 2. Ô chữ nhật bo góc màu hổ phách
        drawRoundedRect(ctx, boxX, boxY, boxWidth, boxHeight, 3);
        ctx.fillStyle = '#d97706';
        ctx.shadowColor = 'rgba(0, 0, 0, 0.45)';
        ctx.shadowBlur = 4;
        ctx.shadowOffsetY = 1;
        ctx.fill();

        ctx.shadowColor = 'transparent';
        ctx.strokeStyle = '#f59e0b';
        ctx.lineWidth = 1;
        ctx.stroke();

        // 3. Text chữ màu trắng
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(labelText, x, boxY + boxHeight / 2);
      } else {
        // Tín hiệu BÁN / CẮT LỖ: Mũi tên đỏ trỏ xuống đỉnh nến, ô chữ nhật bo góc nền đỏ chữ trắng
        const priceVal = s.high !== undefined ? s.high : s.price;
        const yBase = series.priceToCoordinate(priceVal);
        if (yBase === null) continue;

        const arrowTipY = yBase - 4;
        const arrowBaseY = yBase - 11;
        const boxY = yBase - 13 - boxHeight;

        // 1. Mũi tên tam giác màu đỏ
        ctx.beginPath();
        ctx.moveTo(x, arrowTipY);
        ctx.lineTo(x - 5, arrowBaseY);
        ctx.lineTo(x + 5, arrowBaseY);
        ctx.closePath();
        ctx.fillStyle = '#dc2626';
        ctx.fill();
        ctx.strokeStyle = '#b91c1c';
        ctx.lineWidth = 1;
        ctx.stroke();

        // 2. Ô chữ nhật bo góc màu đỏ
        drawRoundedRect(ctx, boxX, boxY, boxWidth, boxHeight, 3);
        ctx.fillStyle = '#dc2626';
        ctx.shadowColor = 'rgba(0, 0, 0, 0.45)';
        ctx.shadowBlur = 4;
        ctx.shadowOffsetY = 1;
        ctx.fill();

        ctx.shadowColor = 'transparent';
        ctx.strokeStyle = '#ef4444';
        ctx.lineWidth = 1;
        ctx.stroke();

        // 3. Text chữ màu trắng
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(labelText, x, boxY + boxHeight / 2);

        // 4. Nếu có mốc Kháng cự động khi gãy mây (như _ KC: 11.1 trong AmiBroker)
        if (s.kc) {
          ctx.font = 'bold 9px ui-sans-serif, system-ui, sans-serif';
          ctx.fillStyle = '#f87171';
          ctx.fillText(`_ KC: ${formatStockPrice(s.kc)}`, x, boxY - 5);
          ctx.font = 'bold 10px ui-sans-serif, system-ui, sans-serif';
        }
      }
    }

    ctx.restore();
  }
}

function safeSetText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = (text !== undefined && text !== null) ? text : "--";
}

export function clearChartPriceLines() {
  if (!candleSeries || activePriceLines.length === 0) return;
  for (const line of activePriceLines) {
    try {
      candleSeries.removePriceLine(line);
    } catch (e) {
      // Bỏ qua nếu dòng đã bị gỡ
    }
  }
  activePriceLines = [];
}

export function syncSummaryPriceCard(config = cachedPriceLinesConfig, currentPrice = null) {
  if (!config) return;
  const isMidTerm = cachedResolution === '1W' || cachedResolution === '1M';
  const isProhibited = !!config.isProhibited;

  if (!currentPrice && cachedCandles && cachedCandles.length > 0) {
    currentPrice = cachedCandles[cachedCandles.length - 1].close;
  }

  // 1. Target 1
  const targetLabelEl = document.getElementById("stbSummaryTargetLabel");
  const targetPctEl = document.getElementById("stbSummaryTargetPct");
  const targetEl = document.getElementById("stbSummaryTarget");
  if (targetLabelEl) {
    targetLabelEl.innerText = isProhibited 
      ? "KHÁNG CỰ (HẠ TỶ TRỌNG)" 
      : (isMidTerm ? "TARGET 1 (FA)" : "TARGET 1 (T+)");
  }
  const targetPrice = config.target;
  const targetPct = (targetPrice && currentPrice > 0)
    ? (((targetPrice - currentPrice) / currentPrice) * 100).toFixed(1)
    : null;
  safeSetText("stbSummaryTarget", targetPrice ? formatStockPrice(targetPrice) : "--");
  safeSetText("stbSummaryTargetPct", targetPct ? (targetPct >= 0 ? `+${targetPct}%` : `${targetPct}%`) : "");
  if (targetEl) {
    if (isProhibited) {
      targetEl.className = "font-bold text-amber-400 text-xs mt-0.5";
      if (targetPctEl) targetPctEl.className = "text-[10px] font-bold font-mono text-amber-400";
      targetEl.title = targetPrice
        ? `Kháng cự hạ tỷ trọng: ${formatStockPrice(targetPrice)} ${targetPct ? `(+${targetPct}%)` : ''}`
        : '';
    } else {
      targetEl.className = "font-bold text-sky-400 text-xs mt-0.5";
      if (targetPctEl) targetPctEl.className = "text-[10px] font-bold font-mono text-sky-400";
      targetEl.title = targetPrice
        ? `${isMidTerm ? 'Target 1 (Định giá hợp lý)' : 'Target 1 (T+ Chốt 50%)'}: ${formatStockPrice(targetPrice)} ${targetPct ? `(+${targetPct}%)` : ''}`
        : '';
    }
  }

  // 2. Target 2
  const target2Price = config.target2;
  const t2Box = document.getElementById("stbSummaryTarget2Box");
  if (t2Box) {
    if (!isProhibited && target2Price && target2Price > 0) {
      t2Box.classList.remove("hidden");
      const target2Pct = (target2Price && currentPrice > 0)
        ? (((target2Price - currentPrice) / currentPrice) * 100).toFixed(1)
        : null;
      const t2LabelEl = t2Box.querySelector("span:first-child");
      if (t2LabelEl) t2LabelEl.innerText = isMidTerm ? "TARGET 2 (ĐỈNH CK)" : "TARGET 2 (TREND)";
      safeSetText("stbSummaryTarget2", formatStockPrice(target2Price));
      safeSetText("stbSummaryTarget2Pct", target2Pct ? (target2Pct >= 0 ? `+${target2Pct}%` : `${target2Pct}%`) : "");
      const t2El = document.getElementById("stbSummaryTarget2");
      if (t2El) {
        t2El.title = `${isMidTerm ? 'Target 2 (Định giá đỉnh chu kỳ)' : 'Target 2 (Trend Gồng lãi)'}: ${formatStockPrice(target2Price)} ${target2Pct ? `(+${target2Pct}%)` : ''}`;
      }
    } else {
      t2Box.classList.add("hidden");
    }
  }

  // 3. Stop Loss / Trailing / Hòa vốn / Ngưỡng thoát vị thế / Chặn lãi (Amber)
  const slPrice = config.stopLoss;
  const isBreakEven = config.stopLossLabel && config.stopLossLabel.includes("Hòa vốn");
  const isTrailing = config.stopLossLabel && config.stopLossLabel.includes("Trailing");
  const isLockProfit = !!config.isLockProfit || (config.stopLossLabel && (config.stopLossLabel.includes("Chặn lãi") || config.stopLossLabel.includes("Chốt hết") || config.stopLossLabel.includes("Khóa lãi")));
  const slLabelEl = document.getElementById("stbSummaryStopLossLabel");
  const slPctEl = document.getElementById("stbSummaryStopLossPct");
  const slEl = document.getElementById("stbSummaryStopLoss");
  if (slLabelEl) {
    if (isProhibited) slLabelEl.innerText = "NGƯỠNG THOÁT VỊ THẾ";
    else if (isLockProfit) slLabelEl.innerText = "HỖ TRỢ CHẶN LÃI (SL)";
    else if (isMidTerm) slLabelEl.innerText = "QTRR TUẦN (SL)";
    else if (isBreakEven) slLabelEl.innerText = "HÒA VỐN (BE)";
    else if (isTrailing) slLabelEl.innerText = "TRAILING SL";
    else slLabelEl.innerText = "CẮT LỖ (SL)";
  }

  const slPct = (slPrice && currentPrice > 0)
    ? (((currentPrice - slPrice) / currentPrice) * 100).toFixed(1)
    : null;
  safeSetText("stbSummaryStopLoss", slPrice ? formatStockPrice(slPrice) : "--");
  safeSetText("stbSummaryStopLossPct", slPct ? `-${slPct}%` : "");
  if (slEl) {
    if (isProhibited) {
      slEl.className = "font-bold text-rose-400 text-xs mt-0.5";
      if (slPctEl) slPctEl.className = "text-[10px] font-bold font-mono text-rose-400";
    } else if (isLockProfit) {
      slEl.className = "font-bold text-amber-400 text-xs mt-0.5";
      if (slPctEl) slPctEl.className = "text-[10px] font-bold font-mono text-amber-400";
    } else {
      slEl.className = "font-bold text-rose-400 text-xs mt-0.5";
      if (slPctEl) slPctEl.className = "text-[10px] font-bold font-mono text-rose-400";
    }
    slEl.title = slPrice
      ? `${isProhibited ? 'Ngưỡng thoát vị thế bảo toàn vốn' : (isLockProfit ? 'Hỗ trợ Chặn Lãi / Chốt lời toàn bộ bảo toàn đệm lãi' : (isMidTerm ? 'Ngưỡng QTRR Tuần' : (isBreakEven ? 'Chặn hòa vốn' : (isTrailing ? 'Trailing Stop' : 'Giá cắt lỗ'))))}: ${formatStockPrice(slPrice)} ${slPct ? `(-${slPct}%)` : ''}`
      : '';
  }
}

export function setChartPriceLines(config = {}) {
  cachedPriceLinesConfig = config;
  syncSummaryPriceCard(config);
  if (!chart || !candleSeries) return;
  clearChartPriceLines();

  const LineStyle = (window.LightweightCharts && window.LightweightCharts.LineStyle) || {
    Solid: 0,
    Dotted: 1,
    Dashed: 2,
    LargeDashed: 3,
    SparseDotted: 4
  };

  const isExit = !!config.isProhibited;

  // 1. Đường Target 1 (T+ / Chốt lời 50%) - Xanh dương nhạt / Sky HOẶC Kháng cự hạ tỷ trọng (Amber)
  if (config.target && config.target > 0) {
    try {
      const lineColor = isExit ? '#f59e0b' : '#38bdf8';
      const line = candleSeries.createPriceLine({
        price: config.target,
        color: lineColor,
        lineWidth: 1.5,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: config.targetLabel || (isExit ? 'Kháng cự hạ tỷ trọng' : 'Target 1 (T+)'),
      });
      activePriceLines.push(line);
    } catch (err) {
      console.warn("Lỗi tạo đường Target 1:", err);
    }
  }

  // 1B. Đường Target 2 (Mục tiêu Xu hướng / Trend) - Tím / Purple / Indigo (Ẩn khi ở chế độ Cấm mua / Thoát vị thế)
  if (!isExit && config.target2 && config.target2 > 0) {
    try {
      const line = candleSeries.createPriceLine({
        price: config.target2,
        color: '#a855f7',
        lineWidth: 1.5,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: config.target2Label || 'Target 2 (Trend)',
      });
      activePriceLines.push(line);
    } catch (err) {
      console.warn("Lỗi tạo đường Target 2:", err);
    }
  }

  // 2. Đường Vùng Mua (Entry / Hỗ trợ) - Xanh lá / Emerald HOẶC Slate Grey nếu isProhibited (Cấm bắt đáy)
  if (config.buyZone && config.buyZone > 0) {
    try {
      const lineColor = isExit ? '#64748b' : '#10b981';
      const lineStyle = isExit ? LineStyle.SparseDotted : LineStyle.Dashed;
      const line = candleSeries.createPriceLine({
        price: config.buyZone,
        color: lineColor,
        lineWidth: 1.5,
        lineStyle: lineStyle,
        axisLabelVisible: true,
        title: config.buyZoneLabel || (isExit ? 'Hỗ trợ S1 (Cấm bắt đáy)' : 'Vùng mua'),
      });
      activePriceLines.push(line);
    } catch (err) {
      console.warn("Lỗi tạo đường Vùng mua:", err);
    }
  }

  // 3. Đường Cắt Lỗ (Stop Loss) / Chặn Lãi (Amber)
  if (config.stopLoss && config.stopLoss > 0) {
    try {
      const isLockProfit = !!config.isLockProfit || (config.stopLossLabel && (config.stopLossLabel.includes("Chặn lãi") || config.stopLossLabel.includes("Chốt hết") || config.stopLossLabel.includes("Khóa lãi")));
      const lineColor = isExit ? '#f43f5e' : (isLockProfit ? '#f59e0b' : '#f43f5e');
      const line = candleSeries.createPriceLine({
        price: config.stopLoss,
        color: lineColor,
        lineWidth: (isExit || isLockProfit) ? 2 : 1.5,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: config.stopLossLabel || (isExit ? 'Ngưỡng thoát vị thế' : (isLockProfit ? 'Hỗ trợ Chặn Lãi' : 'Cắt lỗ')),
      });
      activePriceLines.push(line);
    } catch (err) {
      console.warn("Lỗi tạo đường Cắt lỗ:", err);
    }
  }
}

export function initChart() {
  const container = document.getElementById("chartContainer");
  if (!container || !window.LightweightCharts) return;

  // Dọn dẹp price lines & observer cũ nếu đã từng khởi tạo
  clearChartPriceLines();
  if (chartResizeObserver) {
    chartResizeObserver.disconnect();
    chartResizeObserver = null;
  }

  container.innerHTML = "";

  const initialWidth = container.clientWidth || 800;
  const initialHeight = (container.clientHeight && container.clientHeight > 200) ? container.clientHeight : 520;

  chart = window.LightweightCharts.createChart(container, {
    width: initialWidth,
    height: initialHeight,
    localization: {
      locale: 'vi-VN',
      priceFormatter: formatStockPrice,
    },
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
      scaleMargins: { top: 0.08, bottom: 0.22 },
      entireTextOnly: true,
      autoScale: true,
    },
    timeScale: {
      borderColor: '#334155',
      timeVisible: true,
      secondsVisible: false
    }
  });

  // Series 1: Candlestick (Nến) - Thân nến Xanh biển (Up) / Đỏ (Down)
  candleSeries = chart.addCandlestickSeries({
    upColor: '#2563eb',
    downColor: '#ef4444',
    borderUpColor: '#2563eb',
    borderDownColor: '#ef4444',
    wickUpColor: '#3b82f6',
    wickDownColor: '#ef4444',
    priceFormat: {
      type: 'custom',
      formatter: formatStockPrice,
      minMove: 10,
    }
  });

  // Series Primitive: VÙNG MÂY XANH - VÙNG MÂY HỒNG (STB Style)
  superTrendCloudPrimitive = new SuperTrendCloudPrimitive();
  candleSeries.attachPrimitive(superTrendCloudPrimitive);

  // Series 2: Volume Histogram (Cột khối lượng phía dưới)
  volumeSeries = chart.addHistogramSeries({
    color: '#3b82f6',
    priceFormat: { type: 'volume' },
    priceScaleId: '',
    lastValueVisible: false,
    priceLineVisible: false,
  });

  chart.priceScale('').applyOptions({
    scaleMargins: {
      top: 0.84,
      bottom: 0.0,
    },
  });

  // Series 3 & 4: Đường MA20 & MA50 (Ẩn đi khi bật SuperTrend để tránh rối mắt)
  ma20Series = chart.addLineSeries({
    color: '#3b82f6',
    lineWidth: 1.5,
    title: 'MA20',
    priceFormat: {
      type: 'custom',
      formatter: formatStockPrice,
    }
  });

  ma50Series = chart.addLineSeries({
    color: '#f59e0b',
    lineWidth: 1.5,
    title: 'MA50',
    priceFormat: {
      type: 'custom',
      formatter: formatStockPrice,
    }
  });

  // Sự kiện di chuột cập nhật Legend
  chart.subscribeCrosshairMove(param => {
    if (!param.time || !param.seriesData.get(candleSeries)) {
      return;
    }
    const cData = param.seriesData.get(candleSeries);
    const vData = param.seriesData.get(volumeSeries);
    if (cData) {
      safeSetText("legOpen", formatStockPrice(cData.open));
      safeSetText("legHigh", formatStockPrice(cData.high));
      safeSetText("legLow", formatStockPrice(cData.low));
      safeSetText("legClose", formatStockPrice(cData.close));
    }
    if (vData) {
      safeSetText("legVol", formatCompactNumber(vData.value));
    }
  });

  // Tự động co giãn bằng ResizeObserver (được gỡ trước khi tạo mới tránh leak)
  if (window.ResizeObserver) {
    chartResizeObserver = new ResizeObserver(entries => {
      if (!entries || entries.length === 0 || !chart) return;
      const entry = entries[0];
      const width = entry.contentRect.width;
      const height = entry.contentRect.height;
      if (width > 0 && height > 0) {
        chart.applyOptions({ width, height });
      }
    });
    chartResizeObserver.observe(container);
  }

  // Lắng nghe window resize duy nhất 1 lần cho toàn vòng đời trang
  if (!isResizeListenerAttached) {
    window.addEventListener('resize', () => {
      const c = document.getElementById("chartContainer");
      if (chart && c) {
        chart.applyOptions({
          width: c.clientWidth,
          height: c.clientHeight || 520,
        });
      }
    });
    isResizeListenerAttached = true;
  }

  // SuperTrend Ribbon Toggle Event Listener
  const toggleBtn = document.getElementById("btnToggleSuperTrend");
  if (toggleBtn && !isSuperTrendToggleAttached) {
    toggleBtn.addEventListener("click", () => {
      toggleSuperTrend();
    });
    isSuperTrendToggleAttached = true;
  }
}

/**
 * Tính toán mảng ADX(14) theo chuẩn Wilder's Smoothing cho toàn bộ chuỗi nến.
 * Đo cường độ xu hướng để loại bỏ tín hiệu giả (whipsaw) khi thị trường đi ngang (ADX < 20).
 */
export function calculateADXSeries(candles, period = 14) {
  const n = candles ? candles.length : 0;
  const adxArr = new Array(n).fill(20.0);
  if (n < period * 2) return adxArr;

  const tr = new Array(n);
  const plusDM = new Array(n);
  const minusDM = new Array(n);

  for (let i = 1; i < n; i++) {
    const c = candles[i];
    const prev = candles[i - 1];
    tr[i] = Math.max(c.high - c.low, Math.abs(c.high - prev.close), Math.abs(c.low - prev.close));
    const upMove = c.high - prev.high;
    const downMove = prev.low - c.low;
    plusDM[i] = (upMove > downMove && upMove > 0) ? upMove : 0;
    minusDM[i] = (downMove > upMove && downMove > 0) ? downMove : 0;
  }

  let smoothTR = 0;
  let smoothPlusDM = 0;
  let smoothMinusDM = 0;
  for (let i = 1; i <= period; i++) {
    smoothTR += tr[i];
    smoothPlusDM += plusDM[i];
    smoothMinusDM += minusDM[i];
  }

  const dxList = [];
  const dxIndices = [];

  for (let i = period + 1; i < n; i++) {
    smoothTR = smoothTR - (smoothTR / period) + tr[i];
    smoothPlusDM = smoothPlusDM - (smoothPlusDM / period) + plusDM[i];
    smoothMinusDM = smoothMinusDM - (smoothMinusDM / period) + minusDM[i];

    const plusDI = smoothTR > 0 ? (smoothPlusDM / smoothTR) * 100 : 0;
    const minusDI = smoothTR > 0 ? (smoothMinusDM / smoothTR) * 100 : 0;
    const diSum = plusDI + minusDI;
    const dx = diSum > 0 ? (Math.abs(plusDI - minusDI) / diSum) * 100 : 0;

    dxList.push(dx);
    dxIndices.push(i);
  }

  if (dxList.length < period) {
    const avg = dxList.reduce((a, b) => a + b, 0) / (dxList.length || 1);
    for (let k = 0; k < n; k++) adxArr[k] = avg;
    return adxArr;
  }

  let adxVal = 0;
  for (let i = 0; i < period; i++) {
    adxVal += dxList[i];
  }
  adxVal /= period;
  adxArr[dxIndices[period - 1]] = adxVal;

  for (let i = period; i < dxList.length; i++) {
    adxVal = (adxVal * (period - 1) + dxList[i]) / period;
    adxArr[dxIndices[i]] = adxVal;
  }

  const firstValid = dxIndices[period - 1];
  for (let i = 0; i < firstValid; i++) {
    adxArr[i] = adxArr[firstValid];
  }

  return adxArr;
}

/**
 * SuperTrend Ribbon Cloud (Chuẩn đồ thị AmiBroker STB "Xanh Vào - Hồng Ra")
 * - Vùng Xanh: Khi sóng tăng, phủ dải mây màu xanh ngọc bọc ngoài nến
 * - Vùng Hồng: Khi sóng giảm, phủ dải mây màu hồng bọc ngoài nến
 * - Nến giữ màu tự nhiên (Xanh tăng / Đỏ giảm)
 * - Mũi tên & Huy hiệu: MUA: [Giá] / BÁN: [Giá]
 * - Tích hợp bộ lọc ADX(14) để tránh bẫy Sideway biên hẹp (hiển thị CHỜ TREND khi ADX < 20)
 */
export function calculateSuperTrend(candles, period = TPLUS_SUPERTREND_PERIOD, multiplier = TPLUS_SUPERTREND_MULTIPLIER, resolution = '1D') {
  if (!candles || candles.length === 0) {
    return { standardCandles: [], cloudData: [], markers: [], currentSignal: null, volColors: [], summary: null };
  }

  const n = candles.length;
  const adxSeries = calculateADXSeries(candles, ADX_PERIOD);
  const tr = new Array(n);
  const atr = new Array(n);
  const emaClose = new Array(n);
  const upperBand = new Array(n);
  const lowerBand = new Array(n);
  const finalUpper = new Array(n);
  const finalLower = new Array(n);
  const trend = new Array(n); // 1: XANH (BULL), -1: HỒNG (BEAR)
  const markers = [];
  const signals = [];
  const standardCandles = [];
  const cloudData = [];
  const volColors = [];

  // 1. Tính True Range (TR) & EMA Close
  const kClose = 2 / (period + 1);
  let sumTR = 0;

  for (let i = 0; i < n; i++) {
    const c = candles[i];
    if (i === 0) {
      tr[i] = c.high - c.low;
      emaClose[i] = c.close;
    } else {
      const prevC = candles[i - 1].close;
      tr[i] = Math.max(c.high - c.low, Math.abs(c.high - prevC), Math.abs(c.low - prevC));
      emaClose[i] = c.close * kClose + emaClose[i - 1] * (1 - kClose);
    }

    if (i < period) {
      sumTR += tr[i];
      atr[i] = sumTR / (i + 1);
    } else {
      atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period;
    }
  }

  // 2. Tính Bands & Nhận diện điểm đảo chiều lật dải (Flip) & Chốt lời chủ động (Take Profit)
  let lastFlipIdx = 0;
  let lastFlipPrice = candles[0].close;
  let lastFlipDate = candles[0].time;

  let lastBuyPrice = 0;
  let lastBuyIdx = -1;
  let hasTakenProfit = false;
  let cycleProfitPct = 0;

  for (let i = 0; i < n; i++) {
    const c = candles[i];
    const hl2 = (c.high + c.low) / 2;
    upperBand[i] = hl2 + multiplier * atr[i];
    lowerBand[i] = hl2 - multiplier * atr[i];

    if (i === 0) {
      finalUpper[i] = upperBand[i];
      finalLower[i] = lowerBand[i];
      trend[i] = c.close >= c.open ? 1 : -1;
      lastFlipPrice = c.close;
      lastFlipDate = c.time;
      if (trend[i] === 1) {
        lastBuyPrice = c.close;
        lastBuyIdx = 0;
      }
    } else {
      if (upperBand[i] < finalUpper[i - 1] || candles[i - 1].close > finalUpper[i - 1]) {
        finalUpper[i] = upperBand[i];
      } else {
        finalUpper[i] = finalUpper[i - 1];
      }

      if (lowerBand[i] > finalLower[i - 1] || candles[i - 1].close < finalLower[i - 1]) {
        finalLower[i] = lowerBand[i];
      } else {
        finalLower[i] = finalLower[i - 1];
      }

      if (trend[i - 1] === 1) {
        trend[i] = c.close < finalLower[i] ? -1 : 1;
      } else {
        trend[i] = c.close > finalUpper[i] ? 1 : -1;
      }

      if (trend[i] !== trend[i - 1]) {
        lastFlipIdx = i;
        lastFlipDate = c.time;

        if (trend[i] === 1) {
          // Lật XANH (BULLISH): Kích hoạt mốc cản trên vừa bị bứt phá
          const triggerPrice = (finalUpper[i - 1] > 0 && finalUpper[i - 1] <= c.high) ? finalUpper[i - 1] : c.close;
          lastFlipPrice = triggerPrice;
          lastBuyPrice = triggerPrice;
          hasTakenProfit = false;

          // Bộ lọc ADX để tránh bẫy thị trường đi ngang (Sideway Trap):
          const isSideway = adxSeries[i] < ADX_SIDEWAY_THRESHOLD;
          if (isSideway) {
            signals.push({
              time: c.time,
              type: 'WAIT_SIDEWAY',
              price: triggerPrice,
              high: c.high,
              low: c.low,
              text: 'CHỜ TREND: ' + formatStockPrice(triggerPrice)
            });
            markers.push({
              time: c.time,
              position: 'belowBar',
              color: '#64748b',
              shape: 'arrowUp',
              text: 'CHỜ TREND: ' + formatStockPrice(triggerPrice),
              size: 2
            });
          } else {
            const buyLabel = 'XANH: ' + formatStockPrice(triggerPrice);
            signals.push({
              time: c.time,
              type: 'BUY',
              price: triggerPrice,
              high: c.high,
              low: c.low,
              text: buyLabel
            });
            markers.push({
              time: c.time,
              position: 'belowBar',
              color: '#16a34a',
              shape: 'arrowUp',
              text: buyLabel,
              size: 2
            });
          }
        } else {
          // Lật HỒNG (BEARISH): Kích hoạt mốc hỗ trợ dưới vừa bị xuyên thủng
          const brokenSupport = (finalLower[i - 1] > 0 && finalLower[i - 1] >= c.low) ? finalLower[i - 1] : c.close;
          lastFlipPrice = brokenSupport;
          cycleProfitPct = lastBuyPrice > 0 ? ((brokenSupport - lastBuyPrice) / lastBuyPrice) * 100 : 0;
          const isProfitableExit = hasTakenProfit || (lastBuyPrice > 0 && brokenSupport >= lastBuyPrice);
          const wasSidewayBuy = lastBuyIdx >= 0 && adxSeries[lastBuyIdx] < ADX_SIDEWAY_THRESHOLD;

          const kcPrice = Math.round(finalUpper[i]);
          const exitText = 'HỒNG: ' + formatStockPrice(brokenSupport);

          signals.push({
            time: c.time,
            type: isProfitableExit ? 'SELL_EXIT' : 'SELL',
            price: brokenSupport,
            high: c.high,
            low: c.low,
            text: exitText,
            kc: kcPrice
          });
          markers.push({
            time: c.time,
            position: 'aboveBar',
            color: '#dc2626',
            shape: 'arrowDown',
            text: exitText,
            size: 2
          });
          lastBuyPrice = 0;
        }
      } else if (trend[i] === 1 && !hasTakenProfit && lastBuyPrice > 0 && i > lastBuyIdx) {
        // Kiểm tra cơ chế Chốt lời chủ động (Take Profit) khi đạt lợi nhuận T+ (>= 5.0% và nến có râu trên / hạ nhiệt)
        const gainPct = ((c.high - lastBuyPrice) / lastBuyPrice) * 100;
        const candleRange = c.high - c.low;
        const upperWick = c.high - Math.max(c.open, c.close);
        const isReversalCandle = (c.close < c.open) || (candleRange > 0 && upperWick >= 0.35 * candleRange);

        if (gainPct >= 5.0 && isReversalCandle) {
          hasTakenProfit = true;
          signals.push({
            time: c.time,
            type: 'TAKE_PROFIT',
            price: c.high,
            high: c.high,
            low: c.low,
            text: 'CHỐT LỜI: ' + formatStockPrice(c.high) + ' (+' + gainPct.toFixed(1) + '%)'
          });
          markers.push({
            time: c.time,
            position: 'aboveBar',
            color: '#d97706',
            shape: 'arrowDown',
            text: 'CHỐT LỜI: ' + formatStockPrice(c.high),
            size: 2
          });
        }
      }
    }

    // Thân nến Xanh biển (Tăng) / Đỏ (Giảm) tương phản rõ rệt với mây SuperTrend xanh lá / hồng
    standardCandles.push({
      time: c.time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      color: c.close >= c.open ? '#2563eb' : '#ef4444',
      borderColor: c.close >= c.open ? '#2563eb' : '#ef4444',
      wickColor: c.close >= c.open ? '#3b82f6' : '#ef4444'
    });

    // Đường biên bao ngoài VÙNG MÂY (Cloud Upper / Lower Envelope) chuẩn SuperTrend
    const cloudUpper = trend[i] === 1
      ? Math.max(c.high + 0.3 * atr[i], emaClose[i] + 1.1 * atr[i])
      : finalUpper[i];
    const cloudLower = trend[i] === 1
      ? finalLower[i]
      : Math.min(c.low - 0.3 * atr[i], emaClose[i] - 1.1 * atr[i]);

    cloudData.push({
      time: c.time,
      upper: cloudUpper,
      lower: cloudLower,
      trend: trend[i]
    });

    volColors.push(c.close >= c.open ? 'rgba(37, 99, 235, 0.55)' : 'rgba(239, 68, 68, 0.55)');
  }

  const lastTrend = trend[n - 1];
  const holdingBars = n - 1 - lastFlipIdx;
  const currentPrice = candles[n - 1].close;

  let profitPct = 0;
  if (lastTrend === 1) {
    profitPct = lastBuyPrice > 0 ? ((currentPrice - lastBuyPrice) / lastBuyPrice) * 100 : 0;
  } else {
    profitPct = cycleProfitPct;
  }

  const savedPct = (lastTrend === -1 && lastFlipPrice > currentPrice && lastFlipPrice > 0)
    ? (((lastFlipPrice - currentPrice) / lastFlipPrice) * 100).toFixed(1)
    : null;

  const isCurrentSideway = adxSeries[n - 1] < 20.0;
  const lastWasSideway = lastBuyIdx >= 0 && adxSeries[lastBuyIdx] < 20.0;

  const isViolatingStopLoss = lastTrend === 1 && lastBuyPrice > 0 && profitPct <= -7.0;
  const isNearStopLoss = lastTrend === 1 && lastBuyPrice > 0 && profitPct <= -5.0 && profitPct > -7.0;

  let signalActionText = 'XANH VÀO (GIỮ MUA)';
  let signalAction = 'BUY';
  let signalColor = 'emerald';

  if (lastTrend === 1) {
    if (isViolatingStopLoss) {
      signalActionText = 'VI PHẠM CẮT LỖ (ƯU TIÊN HẠ TỶ TRỌNG)';
      signalAction = 'EXIT';
      signalColor = 'rose';
    } else if (isNearStopLoss) {
      signalActionText = 'CẬN DẢI DỪNG LỖ (CHẶN BẢO VỆ VỐN)';
      signalAction = 'DEFENSIVE';
      signalColor = 'amber';
    } else if (hasTakenProfit) {
      signalActionText = 'XANH VÀO (ĐÃ CHỐT LỜI 1 PHẦN)';
      signalAction = 'HOLD';
      signalColor = 'emerald';
    } else if (lastWasSideway || isCurrentSideway) {
      signalActionText = 'CHỜ XU HƯỚNG (ADX < 20)';
      signalAction = 'WAIT';
      signalColor = 'slate';
    }
  } else {
    signalActionText = 'HỒNG RA (CANH BÁN)';
    signalAction = 'EXIT';
    signalColor = 'pink';
  }

  const currentSignal = {
    direction: lastTrend === 1 ? 'BULLISH' : 'BEARISH',
    action: signalAction,
    text: signalActionText,
    color: signalColor
  };

  const unitLabel = resolution === '1W' ? 'tuần' : (resolution === '1M' ? 'tháng' : 'phiên');
  let summaryStatusText = '';
  if (lastTrend === 1) {
    if (isViolatingStopLoss) {
      summaryStatusText = `vùng xanh nhưng đã vi phạm ngưỡng cắt lỗ (${profitPct.toFixed(1)}%), ưu tiên bảo vệ vốn / thoát vị thế`;
    } else if (isNearStopLoss) {
      summaryStatusText = `vùng xanh nhưng mấp mé dải dừng lỗ (${profitPct.toFixed(1)}%), theo dõi sát kỷ luật`;
    } else if (lastWasSideway || isCurrentSideway) {
      summaryStatusText = `vùng xanh nhưng ADX ${adxSeries[n - 1].toFixed(1)} < 20 (sideway), chờ xác nhận xu hướng`;
    } else {
      summaryStatusText = `vùng xanh, tiếp tục nắm giữ ${holdingBars} ${unitLabel}`;
    }
  } else {
    summaryStatusText = `vùng hồng, canh bán / đứng ngoài ${holdingBars} ${unitLabel}`;
  }

  let summaryBadgeText = '';
  if (lastTrend === 1) {
    if (isViolatingStopLoss) {
      summaryBadgeText = 'VÙNG XANH (VI PHẠM CẮT LỖ)';
    } else if (isNearStopLoss) {
      summaryBadgeText = 'VÙNG XANH (CẬN DẢI DỪNG LỖ)';
    } else if (hasTakenProfit) {
      summaryBadgeText = 'VÙNG XANH (GỒNG LÃI)';
    } else if (lastWasSideway || isCurrentSideway) {
      summaryBadgeText = 'VÙNG XANH (CHỜ TREND)';
    } else {
      summaryBadgeText = 'VÙNG XANH (NẮM GIỮ)';
    }
  } else {
    summaryBadgeText = 'VÙNG HỒNG (CANH BÁN)';
  }

  let summaryLastSignalType = '';
  if (lastTrend === 1) {
    if (hasTakenProfit) {
      summaryLastSignalType = 'LỆNH MUA (ĐÃ CHỐT 1 PHẦN)';
    } else if (lastWasSideway) {
      summaryLastSignalType = 'TÍN HIỆU CHỜ XU HƯỚNG';
    } else {
      summaryLastSignalType = 'LỆNH MUA';
    }
  } else {
    summaryLastSignalType = hasTakenProfit ? 'THOÁT HẾT VỊ THẾ' : (lastWasSideway ? 'THOÁT NHỊP QUAN SÁT' : 'LỆNH HỒNG (CANH BÁN)');
  }

  const summary = {
    isBullish: lastTrend === 1,
    statusText: summaryStatusText,
    badgeText: summaryBadgeText,
    lastSignalType: summaryLastSignalType,
    lastSignalPrice: lastFlipPrice,
    lastSignalDate: lastFlipDate,
    profitPct: profitPct,
    savedPct: savedPct,
    hasTakenProfit: hasTakenProfit,
    currentPrice: currentPrice,
    trailingStop: lastTrend === 1 ? finalLower[n - 1] : finalUpper[n - 1],
    adx: adxSeries[n - 1],
    isSideway: isCurrentSideway
  };

  return { standardCandles, cloudData, signals, markers, currentSignal, volColors, summary };
}

export function updateChartData(candles, resolution = '1D') {
  if (!chart || !candleSeries) {
    initChart();
  }
  if (!chart || !candleSeries || !candles || candles.length === 0) return;

  cachedCandles = candles;
  cachedResolution = resolution;

  const isIntraday = resolution === '1H' || resolution === '30' || resolution === '15' || resolution === '5';
  chart.applyOptions({
    timeScale: {
      timeVisible: isIntraday,
      secondsVisible: false
    }
  });

  const { standardCandles, cloudData, signals, currentSignal, volColors, summary } = calculateSuperTrend(candles, TPLUS_SUPERTREND_PERIOD, TPLUS_SUPERTREND_MULTIPLIER, resolution);

  // 1. Áp dụng nến tự nhiên & Dải VÙNG MÂY bọc ngoài
  candleSeries.setData(standardCandles);

  if (isSuperTrendEnabled) {
    if (superTrendCloudPrimitive) superTrendCloudPrimitive.setData(cloudData, signals);
    candleSeries.setMarkers([]);
    ma20Series.applyOptions({ visible: false });
    ma50Series.applyOptions({ visible: false });

    // Cập nhật Header Summary Card (chuẩn phong cách STB)
    const summaryCard = document.getElementById("superTrendSummaryCard");
    if (summaryCard && summary) {
      summaryCard.classList.remove("hidden");
      const tickerEl = document.getElementById("displayTicker") || document.getElementById("stockSymbol");
      safeSetText("stbSummaryTicker", tickerEl ? tickerEl.innerText : "--");
      const recEl = document.getElementById("stbSummaryRecommendation");
      if (recEl) {
        recEl.innerText = `Khuyến nghị: ${summary.statusText}`;
        if (currentSignal.color === 'rose' || currentSignal.action === 'EXIT') {
          recEl.className = "font-bold text-xs text-rose-400";
        } else if (currentSignal.color === 'amber' || currentSignal.action === 'DEFENSIVE') {
          recEl.className = "font-bold text-xs text-amber-400";
        } else if (summary.isBullish) {
          recEl.className = "font-bold text-xs text-emerald-400";
        } else {
          recEl.className = "font-bold text-xs text-pink-400";
        }
      }
      safeSetText("stbSummaryLastOrder", `${summary.lastSignalType} GIÁ: ${formatStockPrice(summary.lastSignalPrice)}`);

      const profitEl = document.getElementById("stbSummaryProfit");
      if (profitEl) {
        if (summary.isBullish) {
          profitEl.innerText = (summary.profitPct >= 0 ? '+' : '') + summary.profitPct.toFixed(2) + '% (Đang giữ)';
          profitEl.className = summary.profitPct >= 0 ? "font-bold text-emerald-400" : "font-bold text-rose-400";
        } else {
          const sign = summary.profitPct >= 0 ? '+' : '';
          const cycleStr = `${sign}${summary.profitPct.toFixed(2)}% (Chu kỳ)`;
          const savedStr = summary.savedPct ? ` | Tránh lỗ: +${summary.savedPct}%` : '';
          profitEl.innerText = cycleStr + savedStr;
          profitEl.className = summary.profitPct >= 0 ? "font-bold text-emerald-400" : (summary.savedPct ? "font-bold text-sky-400" : "font-bold text-slate-300");
        }
      }
      safeSetText("stbSummaryDate", summary.lastSignalDate || "--");
      safeSetText("stbSummaryCurrentPrice", formatStockPrice(summary.currentPrice));

      // Cập nhật các ô Target 1, Target 2, Stop Loss
      const defaultExit = !!summary.isViolatingStopLoss;
      if (cachedPriceLinesConfig && summary.isViolatingStopLoss) {
        cachedPriceLinesConfig.isProhibited = true;
      }
      syncSummaryPriceCard(cachedPriceLinesConfig || {
        stopLoss: summary.trailingStop,
        stopLossLabel: 'Trailing SL',
        isProhibited: defaultExit
      }, summary.currentPrice);
    }
  } else {
    if (superTrendCloudPrimitive) superTrendCloudPrimitive.setData([], []);
    candleSeries.setMarkers([]);
    ma20Series.applyOptions({ visible: true });
    ma50Series.applyOptions({ visible: true });
    const summaryCard = document.getElementById("superTrendSummaryCard");
    if (summaryCard) summaryCard.classList.add("hidden");
  }

  // Luôn đồng bộ các đường mốc giá (Target T+ > Vùng mua > Cắt lỗ) nếu có config
  if (cachedPriceLinesConfig) {
    setChartPriceLines(cachedPriceLinesConfig);
  }

  // 2. Volume Histogram
  const volData = [];
  const ma20Data = [];
  const ma50Data = [];
  const closePrices = candles.map(c => c.close);

  for (let i = 0; i < candles.length; i++) {
    const item = candles[i];
    const vColor = item.close >= item.open ? 'rgba(37, 99, 235, 0.50)' : 'rgba(239, 68, 68, 0.50)';

    volData.push({
      time: item.time,
      value: item.volume,
      color: vColor
    });

    if (i >= 19) {
      const slice20 = closePrices.slice(i - 19, i + 1);
      const avg20 = slice20.reduce((a, b) => a + b, 0) / 20;
      ma20Data.push({ time: item.time, value: avg20 });
    }

    if (i >= 49) {
      const slice50 = closePrices.slice(i - 49, i + 1);
      const avg50 = slice50.reduce((a, b) => a + b, 0) / 50;
      ma50Data.push({ time: item.time, value: avg50 });
    }
  }

  volumeSeries.setData(volData);
  ma20Series.setData(ma20Data);
  ma50Series.setData(ma50Data);

  chart.timeScale().fitContent();

  // 3. Update SuperTrend Signal Badge
  const signalBadgeEl = document.getElementById("superTrendSignalBadge");
  if (signalBadgeEl && currentSignal) {
    if (currentSignal.color === 'rose' || currentSignal.action === 'EXIT') {
      signalBadgeEl.className = "flex items-center gap-1.5 px-3 py-1 rounded-lg bg-rose-950/90 border border-rose-500 text-rose-300 font-mono text-xs font-bold shadow-md shadow-rose-950/50";
      signalBadgeEl.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-rose-400 animate-pulse"></i> <span>TÍN HIỆU: ${currentSignal.text}</span>`;
    } else if (currentSignal.color === 'amber' || currentSignal.action === 'DEFENSIVE') {
      signalBadgeEl.className = "flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-950/90 border border-amber-500 text-amber-300 font-mono text-xs font-bold shadow-md shadow-amber-950/50";
      signalBadgeEl.innerHTML = `<i class="fa-solid fa-shield text-amber-400"></i> <span>TÍN HIỆU: ${currentSignal.text}</span>`;
    } else if (currentSignal.direction === 'BULLISH') {
      signalBadgeEl.className = "flex items-center gap-1.5 px-3 py-1 rounded-lg bg-emerald-950/90 border border-emerald-500 text-emerald-300 font-mono text-xs font-bold shadow-md shadow-emerald-950/50";
      signalBadgeEl.innerHTML = `<i class="fa-solid fa-circle-arrow-up text-emerald-400 animate-bounce"></i> <span>TÍN HIỆU: ${currentSignal.text}</span>`;
    } else {
      signalBadgeEl.className = "flex items-center gap-1.5 px-3 py-1 rounded-lg bg-pink-950/90 border border-pink-500 text-pink-300 font-mono text-xs font-bold shadow-md shadow-pink-950/50";
      signalBadgeEl.innerHTML = `<i class="fa-solid fa-circle-arrow-down text-pink-400 animate-bounce"></i> <span>TÍN HIỆU: ${currentSignal.text}</span>`;
    }
  }

  const lastC = candles[candles.length - 1];
  safeSetText("legOpen", formatStockPrice(lastC.open));
  safeSetText("legHigh", formatStockPrice(lastC.high));
  safeSetText("legLow", formatStockPrice(lastC.low));
  safeSetText("legClose", formatStockPrice(lastC.close));
  safeSetText("legVol", formatCompactNumber(lastC.volume));
}

export function toggleSuperTrend() {
  isSuperTrendEnabled = !isSuperTrendEnabled;
  const toggleBtnLabel = document.getElementById("superTrendToggleLabel");
  const toggleBtnDot = document.getElementById("superTrendToggleDot");
  if (toggleBtnLabel) {
    toggleBtnLabel.innerText = isSuperTrendEnabled ? "SuperTrend: BẬT" : "SuperTrend: TẮT";
  }
  if (toggleBtnDot) {
    toggleBtnDot.className = isSuperTrendEnabled
      ? "w-2 h-2 rounded-full bg-emerald-400 inline-block animate-pulse"
      : "w-2 h-2 rounded-full bg-slate-500 inline-block";
  }
  if (cachedCandles && cachedCandles.length > 0) {
    updateChartData(cachedCandles, cachedResolution);
  }
}
