import { formatStockPrice, formatCompactNumber } from '../utils.js?v=4.0';

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

      if (isBuy) {
        // Tín hiệu MUA: Mũi tên xanh lá trỏ lên đáy nến, ô chữ nhật bo góc nền xanh lá chữ trắng
        const priceVal = s.low !== undefined ? s.low : s.price;
        const yBase = series.priceToCoordinate(priceVal);
        if (yBase === null) continue;

        const arrowTipY = yBase + 4;
        const arrowBaseY = yBase + 11;
        const boxY = yBase + 13;

        // 1. Mũi tên tam giác màu xanh lá
        ctx.beginPath();
        ctx.moveTo(x, arrowTipY);
        ctx.lineTo(x - 5, arrowBaseY);
        ctx.lineTo(x + 5, arrowBaseY);
        ctx.closePath();
        ctx.fillStyle = '#16a34a';
        ctx.fill();
        ctx.strokeStyle = '#15803d';
        ctx.lineWidth = 1;
        ctx.stroke();

        // 2. Ô chữ nhật bo góc màu xanh lá
        drawRoundedRect(ctx, boxX, boxY, boxWidth, boxHeight, 3);
        ctx.fillStyle = '#16a34a';
        ctx.shadowColor = 'rgba(0, 0, 0, 0.45)';
        ctx.shadowBlur = 4;
        ctx.shadowOffsetY = 1;
        ctx.fill();

        ctx.shadowColor = 'transparent';
        ctx.strokeStyle = '#22c55e';
        ctx.lineWidth = 1;
        ctx.stroke();

        // 3. Text chữ màu trắng
        ctx.fillStyle = '#ffffff';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(labelText, x, boxY + boxHeight / 2);
      } else {
        // Tín hiệu BÁN: Mũi tên đỏ trỏ xuống đỉnh nến, ô chữ nhật bo góc nền đỏ chữ trắng
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

export function setChartPriceLines(config = {}) {
  cachedPriceLinesConfig = config;
  if (!chart || !candleSeries) return;
  clearChartPriceLines();

  // Khi đang bật SuperTrend Cloud (Vùng Xanh/Hồng), không vẽ các đường cản ngang gây rối mắt như ảnh mẫu STB
  if (isSuperTrendEnabled) return;

  const LineStyle = (window.LightweightCharts && window.LightweightCharts.LineStyle) || {
    Solid: 0,
    Dotted: 1,
    Dashed: 2,
    LargeDashed: 3,
    SparseDotted: 4
  };

  // 1. Đường Target T+ (Kháng cự / Chốt lời) - Xanh dương nhạt / Sky
  if (config.target && config.target > 0) {
    try {
      const line = candleSeries.createPriceLine({
        price: config.target,
        color: '#38bdf8',
        lineWidth: 1.5,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: config.targetLabel || 'Target T+',
      });
      activePriceLines.push(line);
    } catch (err) {
      console.warn("Lỗi tạo đường Target:", err);
    }
  }

  // 2. Đường Vùng Mua (Entry / Hỗ trợ) - Xanh lá / Emerald
  if (config.buyZone && config.buyZone > 0) {
    try {
      const line = candleSeries.createPriceLine({
        price: config.buyZone,
        color: '#10b981',
        lineWidth: 1.5,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: config.buyZoneLabel || 'Vùng mua',
      });
      activePriceLines.push(line);
    } catch (err) {
      console.warn("Lỗi tạo đường Vùng mua:", err);
    }
  }

  // 3. Đường Cắt Lỗ (Stop Loss) - Đỏ / Rose
  if (config.stopLoss && config.stopLoss > 0) {
    try {
      const line = candleSeries.createPriceLine({
        price: config.stopLoss,
        color: '#f43f5e',
        lineWidth: 1.5,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: config.stopLossLabel || 'Cắt lỗ',
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
 * SuperTrend Ribbon Cloud (Chuẩn đồ thị AmiBroker STB "Xanh Vào - Hồng Ra")
 * - Vùng Xanh: Khi sóng tăng, phủ dải mây màu xanh ngọc bọc ngoài nến
 * - Vùng Hồng: Khi sóng giảm, phủ dải mây màu hồng bọc ngoài nến
 * - Nến giữ màu tự nhiên (Xanh tăng / Đỏ giảm)
 * - Mũi tên & Huy hiệu: MUA: [Giá] / BÁN: [Giá]
 */
export function calculateSuperTrend(candles, period = 10, multiplier = 1.8) {
  if (!candles || candles.length === 0) {
    return { standardCandles: [], cloudData: [], markers: [], currentSignal: null, volColors: [], summary: null };
  }

  const n = candles.length;
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

  // 2. Tính Bands & Nhận diện điểm đảo chiều lật dải (Flip)
  let lastFlipIdx = 0;
  let lastFlipPrice = candles[0].close;
  let lastFlipDate = candles[0].time;

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
        lastFlipPrice = c.close;
        lastFlipDate = c.time;

        if (trend[i] === 1) {
          // Huy hiệu MUA: Mũi tên xanh lá, chữ MUA: [Giá] bọc trong ô xanh lá chữ trắng
          signals.push({
            time: c.time,
            type: 'BUY',
            price: c.close,
            high: c.high,
            low: c.low,
            text: 'MUA: ' + formatStockPrice(c.close)
          });
          markers.push({
            time: c.time,
            position: 'belowBar',
            color: '#16a34a',
            shape: 'arrowUp',
            text: 'MUA: ' + formatStockPrice(c.close),
            size: 2
          });
        } else {
          // Huy hiệu BÁN: Mũi tên đỏ, chữ BÁN: [Giá] bọc trong ô đỏ chữ trắng
          signals.push({
            time: c.time,
            type: 'SELL',
            price: c.close,
            high: c.high,
            low: c.low,
            text: 'BÁN: ' + formatStockPrice(c.close)
          });
          markers.push({
            time: c.time,
            position: 'aboveBar',
            color: '#dc2626',
            shape: 'arrowDown',
            text: 'BÁN: ' + formatStockPrice(c.close),
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

    // Đường biên bao ngoài VÙNG MÂY (Cloud Upper / Lower Envelope) ôm trọn hành vi nến như STB
    const cloudUpper = Math.max(c.high + 0.4 * atr[i], emaClose[i] + 1.3 * atr[i]);
    const cloudLower = Math.min(c.low - 0.4 * atr[i], emaClose[i] - 1.3 * atr[i]);

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
  const profitPct = lastFlipPrice > 0 ? ((currentPrice - lastFlipPrice) / lastFlipPrice) * 100 : 0;

  const currentSignal = {
    direction: lastTrend === 1 ? 'BULLISH' : 'BEARISH',
    action: lastTrend === 1 ? 'BUY' : 'EXIT',
    text: lastTrend === 1 ? 'XANH VÀO (GIỮ MUA)' : 'HỒNG RA (CANH BÁN)',
    color: lastTrend === 1 ? 'emerald' : 'pink'
  };

  const summary = {
    isBullish: lastTrend === 1,
    statusText: lastTrend === 1
      ? `vùng xanh, tiếp tục nắm giữ ${holdingBars} phiên`
      : `vùng hồng, canh bán / đứng ngoài ${holdingBars} phiên`,
    badgeText: lastTrend === 1 ? 'VÙNG XANH (NẮM GIỮ)' : 'VÙNG HỒNG (CANH BÁN)',
    lastSignalType: lastTrend === 1 ? 'LỆNH MUA' : 'LỆNH BÁN',
    lastSignalPrice: lastFlipPrice,
    lastSignalDate: lastFlipDate,
    profitPct: profitPct,
    currentPrice: currentPrice,
    trailingStop: lastTrend === 1 ? finalLower[n - 1] : finalUpper[n - 1]
  };

  return { standardCandles, cloudData, signals, markers, currentSignal, volColors, summary };
}

export function updateChartData(candles, resolution = '1D') {
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

  const { standardCandles, cloudData, signals, currentSignal, volColors, summary } = calculateSuperTrend(candles, 10, 1.8);

  // 1. Áp dụng nến tự nhiên & Dải VÙNG MÂY bọc ngoài
  candleSeries.setData(standardCandles);

  if (isSuperTrendEnabled) {
    if (superTrendCloudPrimitive) superTrendCloudPrimitive.setData(cloudData, signals);
    candleSeries.setMarkers([]);
    ma20Series.applyOptions({ visible: false });
    ma50Series.applyOptions({ visible: false });
    clearChartPriceLines();

    // Cập nhật Header Summary Card (chuẩn phong cách STB cũ)
    const summaryCard = document.getElementById("superTrendSummaryCard");
    if (summaryCard && summary) {
      summaryCard.classList.remove("hidden");
      const tickerEl = document.getElementById("stockSymbol");
      safeSetText("stbSummaryTicker", tickerEl ? tickerEl.innerText : "--");
      safeSetText("stbSummaryRecommendation", `Khuyến nghị: ${summary.statusText}`);
      safeSetText("stbSummaryLastOrder", `${summary.lastSignalType} GIÁ: ${formatStockPrice(summary.lastSignalPrice)}`);

      const profitEl = document.getElementById("stbSummaryProfit");
      if (profitEl) {
        profitEl.innerText = (summary.profitPct >= 0 ? '+' : '') + summary.profitPct.toFixed(2) + '%';
        profitEl.className = summary.profitPct >= 0 ? "font-bold text-emerald-400" : "font-bold text-rose-400";
      }
      safeSetText("stbSummaryDate", summary.lastSignalDate || "--");
      safeSetText("stbSummaryCurrentPrice", formatStockPrice(summary.currentPrice));
      safeSetText("stbSummaryTarget", cachedPriceLinesConfig?.target ? formatStockPrice(cachedPriceLinesConfig.target) : "--");
      safeSetText("stbSummaryStopLoss", cachedPriceLinesConfig?.stopLoss ? formatStockPrice(cachedPriceLinesConfig.stopLoss) : (summary.trailingStop ? formatStockPrice(summary.trailingStop) : "--"));
    }
  } else {
    if (superTrendCloudPrimitive) superTrendCloudPrimitive.setData([], []);
    candleSeries.setMarkers([]);
    ma20Series.applyOptions({ visible: true });
    ma50Series.applyOptions({ visible: true });
    if (cachedPriceLinesConfig) {
      setChartPriceLines(cachedPriceLinesConfig);
    }
    const summaryCard = document.getElementById("superTrendSummaryCard");
    if (summaryCard) summaryCard.classList.add("hidden");
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
    if (currentSignal.direction === 'BULLISH') {
      signalBadgeEl.className = "flex items-center gap-1.5 px-3 py-1 rounded-lg bg-emerald-950/90 border border-emerald-500 text-emerald-300 font-mono text-xs font-bold shadow-md shadow-emerald-950/50";
      signalBadgeEl.innerHTML = '<i class="fa-solid fa-circle-arrow-up text-emerald-400 animate-bounce"></i> <span>TÍN HIỆU: XANH VÀO (GIỮ MUA)</span>';
    } else {
      signalBadgeEl.className = "flex items-center gap-1.5 px-3 py-1 rounded-lg bg-pink-950/90 border border-pink-500 text-pink-300 font-mono text-xs font-bold shadow-md shadow-pink-950/50";
      signalBadgeEl.innerHTML = '<i class="fa-solid fa-circle-arrow-down text-pink-400 animate-bounce"></i> <span>TÍN HIỆU: HỒNG RA (CANH BÁN)</span>';
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
