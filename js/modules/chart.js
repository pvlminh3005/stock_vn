import { formatStockPrice, formatCompactNumber } from '../utils.js?v=2.6';

let chart = null;
let candleSeries = null;
let volumeSeries = null;
let ma20Series = null;
let ma50Series = null;

function safeSetText(id, text) {
  const el = document.getElementById(id);
  if (el) el.innerText = (text !== undefined && text !== null) ? text : "--";
}

export function initChart() {
  const container = document.getElementById("chartContainer");
  if (!container || !window.LightweightCharts) return;

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

  // Series 1: Candlestick (Nến)
  candleSeries = chart.addCandlestickSeries({
    upColor: '#10b981',
    downColor: '#ef4444',
    borderUpColor: '#10b981',
    borderDownColor: '#ef4444',
    wickUpColor: '#10b981',
    wickDownColor: '#ef4444',
    priceFormat: {
      type: 'custom',
      formatter: formatStockPrice,
      minMove: 10,
    }
  });

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

  // Series 3 & 4: Đường MA20 & MA50
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

  // Tự động co giãn toàn bộ chiều rộng và chiều cao container bằng ResizeObserver
  if (window.ResizeObserver) {
    const resizeObserver = new ResizeObserver(entries => {
      if (!entries || entries.length === 0 || !chart) return;
      const entry = entries[0];
      const width = entry.contentRect.width;
      const height = entry.contentRect.height;
      if (width > 0 && height > 0) {
        chart.applyOptions({ width, height });
      }
    });
    resizeObserver.observe(container);
  }

  window.addEventListener('resize', () => {
    if (chart && container) {
      chart.applyOptions({
        width: container.clientWidth,
        height: container.clientHeight || 520,
      });
    }
  });
}

export function updateChartData(candles, resolution = '1D') {
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

  const lastC = candles[candles.length - 1];
  safeSetText("legOpen", formatStockPrice(lastC.open));
  safeSetText("legHigh", formatStockPrice(lastC.high));
  safeSetText("legLow", formatStockPrice(lastC.low));
  safeSetText("legClose", formatStockPrice(lastC.close));
  safeSetText("legVol", formatCompactNumber(lastC.volume));
}
