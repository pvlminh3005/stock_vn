# Hướng Dẫn Sử Dụng TradingView Lightweight Charts & Cách Nạp Data Từng Mã

Tài liệu này hướng dẫn đầy đủ từ **cách import thư viện**, **tinh chỉnh giao diện biểu đồ chuyên nghiệp**, cho đến **cách đổ dữ liệu cho từng mã cổ phiếu sau mỗi sự kiện tìm kiếm**.

---

## 1. Import Thư Viện

Thư viện **TradingView Lightweight Charts** (v4.x) hoàn toàn mã nguồn mở (Apache 2.0), miễn phí 100%, không cần API Key hay tài khoản:

### Cách 1: Dùng thẻ `<script>` qua CDN (Đang dùng trong dự án)
Nhúng trực tiếp vào thẻ `<head>` của file [index.html](file:///Users/minhpvl/Desktop/stock_rt/index.html):
```html
<!-- TradingView Lightweight Charts v4.1.1 Standalone -->
<script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
```

### Cách 2: Dùng NPM (Nếu dự án dùng Webpack / Vite / React / Vue)
```bash
npm install lightweight-charts
```
```javascript
import { createChart, CrosshairMode } from 'lightweight-charts';
```

---

## 2. Thiết Lập Khung HTML & Tinh Chỉnh Giao Diện Biểu Đồ (UI Styling)

### 2.1. Chuẩn bị Container HTML
Đặt chiều cao cụ thể (ví dụ: `520px`) và bo góc hiện đại:
```html
<div id="chartContainer" class="w-full h-[520px] rounded-xl overflow-hidden border border-slate-800 bg-slate-950 relative"></div>
```

### 2.2. Khởi tạo Biểu đồ với UI Dark Mode & Tinh Chỉnh Chuyên Nghiệp

```javascript
import { formatStockPrice } from './utils.js';

const container = document.getElementById("chartContainer");

const chart = window.LightweightCharts.createChart(container, {
  width: container.clientWidth || 800,
  height: container.clientHeight || 520,

  // 1. Định dạng giá chuẩn tiếng Việt (ví dụ: 62,70)
  localization: {
    locale: 'vi-VN',
    priceFormatter: formatStockPrice, // Format dạng 2 chữ số thập phân
  },

  // 2. Màu sắc giao diện (Dark Mode cao cấp)
  layout: {
    background: { color: '#090d16' },
    textColor: '#94a3b8',
    fontSize: 11,
    fontFamily: 'ui-sans-serif, system-ui, sans-serif'
  },

  // 3. Đường lưới ngang & dọc (Subtle Grid)
  grid: {
    vertLines: { color: '#1e293b' },
    horzLines: { color: '#1e293b' }
  },

  // 4. Con trỏ chuột chữ thập (Crosshair nét đứt)
  crosshair: {
    mode: window.LightweightCharts.CrosshairMode.Normal,
    vertLine: { color: '#475569', width: 1, style: 2 },
    horzLine: { color: '#475569', width: 1, style: 2 }
  },

  // 5. Cột giá bên phải (Right Price Scale):
  // Chừa 8% lề trên và 22% lề dưới để nến giá không bao giờ chạm cột khối lượng
  rightPriceScale: {
    borderColor: '#334155',
    scaleMargins: {
      top: 0.08,    // Lề trên 8%
      bottom: 0.22, // Lề dưới 22% (dành không gian phía dưới cho volume)
    },
    entireTextOnly: true,
    autoScale: true,
  },

  // 6. Trục thời gian đáy (Time Scale)
  timeScale: {
    borderColor: '#334155',
    timeVisible: false, // Bật true nếu xem nến Intraday 1H, 15m
    secondsVisible: false
  }
});
```

---

### 2.3. Khởi Tạo Các Series Dữ Liệu (Nến, Khối Lượng, Đường MA)

#### A. Chuỗi nến Nhật (Candlestick Series)
```javascript
const candleSeries = chart.addCandlestickSeries({
  upColor: '#10b981',         // Thân nến tăng: Xanh ngọc
  downColor: '#ef4444',       // Thân nến giảm: Đỏ tươi
  borderUpColor: '#10b981',
  borderDownColor: '#ef4444',
  wickUpColor: '#10b981',     // Râu nến
  wickDownColor: '#ef4444',
  priceFormat: {
    type: 'custom',
    formatter: formatStockPrice, // Định dạng giá 2 số thập phân (62,70)
    minMove: 10,
  }
});
```

#### B. Chuỗi khối lượng thu gọn ở đáy (Volume Histogram Series)
Áp dụng kỹ thuật overlay độc lập (`priceScaleId: ''`) và hạ thấp cột volume xuống tối đa 16% chiều cao đáy:
```javascript
const volumeSeries = chart.addHistogramSeries({
  color: '#3b82f6',
  priceFormat: { type: 'volume' },
  priceScaleId: '',        // Đặt overlay độc lập để không ảnh hưởng thang giá nến
  lastValueVisible: false, // Ẩn nhãn khối lượng đè lên trục giá bên phải
  priceLineVisible: false, // Ẩn đường kẻ dóng ngang
});

// Giới hạn cột Volume chỉ chiếm tối đa 16% dưới đáy biểu đồ
chart.priceScale('').applyOptions({
  scaleMargins: {
    top: 0.84, // 84% chiều cao bên trên để trống hoàn toàn cho nến giá
    bottom: 0.0,
  },
});
```

#### C. Chuỗi đường xu hướng MA (Line Series)
```javascript
const ma20Series = chart.addLineSeries({
  color: '#3b82f6',
  lineWidth: 1.5,
  title: 'MA20',
  priceFormat: { type: 'custom', formatter: formatStockPrice }
});

const ma50Series = chart.addLineSeries({
  color: '#f59e0b',
  lineWidth: 1.5,
  title: 'MA50',
  priceFormat: { type: 'custom', formatter: formatStockPrice }
});
```

---

### 2.4. Tự Động Co Giãn 100% Khung Hình (`ResizeObserver`)
Đảm bảo canvas biểu đồ tự động ôm sát 100% kích thước khung `#chartContainer` khi thay đổi kích thước cửa sổ hoặc responsive, không bị khoảng trống đen ở đáy:
```javascript
if (window.ResizeObserver) {
  const resizeObserver = new ResizeObserver(entries => {
    if (!entries || entries.length === 0 || !chart) return;
    const { width, height } = entries[0].contentRect;
    if (width > 0 && height > 0) {
      chart.applyOptions({ width, height });
    }
  });
  resizeObserver.observe(container);
}
```

---

### 2.5. Lắng Nghe Sự Kiện Di Chuột Cập Nhật Legend O-H-L-C
```javascript
chart.subscribeCrosshairMove(param => {
  if (!param.time || !param.seriesData.get(candleSeries)) return;

  const cData = param.seriesData.get(candleSeries);
  const vData = param.seriesData.get(volumeSeries);

  if (cData) {
    document.getElementById("legOpen").innerText = formatStockPrice(cData.open);
    document.getElementById("legHigh").innerText = formatStockPrice(cData.high);
    document.getElementById("legLow").innerText = formatStockPrice(cData.low);
    document.getElementById("legClose").innerText = formatStockPrice(cData.close);
  }
  if (vData) {
    document.getElementById("legVol").innerText = formatCompactNumber(vData.value);
  }
});
```

---

## 3. Cách Nạp & Cập Nhật Data Từng Mã Sau Mỗi Sự Kiện Tìm Kiếm

### 3.1. Nguyên Lý Vàng:
1. **Biểu đồ (`createChart`) và các Series chỉ khởi tạo 1 lần duy nhất** lúc load trang.
2. Khi người dùng tra cứu mã mới (ví dụ từ `FPT` sang `HPG`): **Tuyệt đối không hủy (destroy) hay tạo lại chart**, mà chỉ cần gọi **`series.setData(newData)`**.
3. Phương thức `setData()` sẽ tự động xóa sạch toàn bộ lịch sử nến của mã cũ và render tức thì nến của mã mới.

---

### 3.2. Hàm Nạp Dữ Liệu Lên Biểu Đồ: `updateChartData(candles, resolution)`

```javascript
function updateChartData(candles, resolution = '1D') {
  if (!chart || !candleSeries || !candles || candles.length === 0) return;

  // 1. Cấu hình trục thời gian hiển thị giờ/phút nếu xem Intraday
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

    // A. Nến kỹ thuật
    candleData.push({
      time: item.time,   // 'YYYY-MM-DD' hoặc UNIX timestamp giây
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close
    });

    // B. Cột khối lượng (xanh khi đóng cửa >= mở cửa, đỏ khi giảm)
    volData.push({
      time: item.time,
      value: item.volume,
      color: item.close >= item.open ? 'rgba(16, 185, 129, 0.45)' : 'rgba(239, 68, 68, 0.45)'
    });

    // C. Tính MA20
    if (i >= 19) {
      const slice20 = closePrices.slice(i - 19, i + 1);
      const avg20 = slice20.reduce((a, b) => a + b, 0) / 20;
      ma20Data.push({ time: item.time, value: avg20 });
    }

    // D. Tính MA50
    if (i >= 49) {
      const slice50 = closePrices.slice(i - 49, i + 1);
      const avg50 = slice50.reduce((a, b) => a + b, 0) / 50;
      ma50Data.push({ time: item.time, value: avg50 });
    }
  }

  // Nạp dữ liệu mới vào các Series (xóa data cũ ngay lập tức)
  candleSeries.setData(candleData);
  volumeSeries.setData(volData);
  ma20Series.setData(ma20Data);
  ma50Series.setData(ma50Data);

  // Zoom toàn bộ dữ liệu vừa vặn màn hình
  chart.timeScale().fitContent();

  // Cập nhật thanh Legend O-H-L-C với cây nến mới nhất
  const lastC = candles[candles.length - 1];
  document.getElementById("legOpen").innerText = formatStockPrice(lastC.open);
  document.getElementById("legHigh").innerText = formatStockPrice(lastC.high);
  document.getElementById("legLow").innerText = formatStockPrice(lastC.low);
  document.getElementById("legClose").innerText = formatStockPrice(lastC.close);
  document.getElementById("legVol").innerText = formatCompactNumber(lastC.volume);
}
```

---

### 3.3. Hàm Điều Phối Trung Tâm: `loadStock(ticker)`

Khi có yêu cầu tra cứu mã, hàm `loadStock` sẽ gọi Backend API và chuyển tiếp dữ liệu nến cho biểu đồ:

```javascript
import { getStockDetail } from './api.js';

export async function loadStock(ticker) {
  if (!ticker) return;
  const sym = ticker.trim().toUpperCase();

  showLoading(sym); // Hiện màn hình loading

  try {
    const resSelect = document.getElementById("chartTimeframeSelect");
    const currentResolution = resSelect ? (resSelect.value || '1D') : '1D';

    // 1. Gọi API Backend (trả về full thông tin: giá, chỉ số, nến kỹ thuật)
    const data = await getStockDetail(sym, currentResolution);

    // 2. Render các bảng thông tin cơ bản, chấm điểm & chỉ báo
    renderQuickHeader(data);
    renderVerdictAndScores(data);
    renderVisualMeters(data);
    renderActionCards(data.technicals);

    // 3. ĐỔ DỮ LIỆU NẾN LÊN BIỂU ĐỒ TRADINGVIEW
    updateChartData(data.candles, currentResolution);

  } catch (err) {
    console.error("Lỗi khi load mã:", err);
    alert(`Lỗi tải dữ liệu cho mã ${sym}: ${err.message}`);
  } finally {
    hideLoading(); // Ẩn màn hình loading
  }
}
```

---

### 3.4. Bắt Các Sự Kiện Tìm Kiếm Để View Data Từng Mã

Dự án hỗ trợ **5 điểm tương tác** để người dùng xem biểu đồ của bất kỳ mã nào:

```javascript
function initEvents() {
  const input = document.getElementById("tickerInput");
  const searchBtn = document.getElementById("searchBtn");
  const select = document.getElementById("tickerSelect");
  const suggestions = document.getElementById("searchSuggestions");

  const doSearch = () => {
    const val = input ? input.value.trim().toUpperCase() : "";
    if (val) {
      suggestions?.classList.add("hidden");
      loadStock(val); // 👉 Gọi nạp data mã vừa nhập
    }
  };

  // 1. Sự kiện Click nút "Tra cứu"
  if (searchBtn) {
    searchBtn.addEventListener("click", (e) => {
      e.preventDefault();
      doSearch();
    });
  }

  // 2. Sự kiện Nhấn phím Enter trong ô input
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        doSearch();
      }
    });
  }

  // 3. Sự kiện Click chọn từ danh sách Autocomplete gợi ý
  if (suggestions) {
    suggestions.addEventListener("mousedown", (e) => {
      const item = e.target.closest(".suggestion-item");
      if (item) {
        e.preventDefault();
        const t = item.getAttribute("data-ticker");
        if (t) {
          if (input) input.value = t;
          suggestions.classList.add("hidden");
          loadStock(t); // 👉 Nạp data mã vừa click chọn
        }
      }
    });
  }

  // 4. Sự kiện Chọn mã từ dropdown "Chọn mã hot"
  if (select) {
    select.addEventListener("change", (e) => {
      const val = e.target.value;
      if (val) {
        if (input) input.value = val;
        loadStock(val); // 👉 Nạp data mã hot
      }
    });
  }

  // 5. Sự kiện Click các thẻ Chip gợi ý nhanh (FPT, MWG, HPG, TCB...)
  document.querySelectorAll(".chip-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const t = btn.getAttribute("data-ticker");
      if (t) {
        if (input) input.value = t;
        loadStock(t); // 👉 Nạp data chip được click
      }
    });
  });

  // 6. Sự kiện Đổi khung thời gian biểu đồ (D1, W1, 1H, 15m)
  const tfSelect = document.getElementById("chartTimeframeSelect");
  if (tfSelect) {
    tfSelect.addEventListener("change", async (e) => {
      const newRes = e.target.value;
      const chartRes = await fetch(`/api/chart?ticker=${currentTicker}&resolution=${newRes}`).then(r => r.json());
      if (chartRes && chartRes.candles) {
        updateChartData(chartRes.candles, newRes); // 👉 Vẽ lại nến khung thời gian mới
      }
    });
  }
}
```

---

## 4. Tóm Tắt Quy Trình End-to-End

```
[Người dùng Click Tra Cứu / Chọn Mã]
              │
              ▼
    loadStock(ticker)
              │
              ▼
  fetch('/api/stock?ticker=...') ──► Trả về { candles: [...], technicals, fundamentals }
              │
              ▼
updateChartData(data.candles)
              │
   ┌──────────┴──────────┐
   ▼                     ▼
candleSeries.setData()  volumeSeries.setData()
   │                     │
   └──────────┬──────────┘
              ▼
  chart.timeScale().fitContent()
              │
              ▼
[Canvas hiển thị Nến, Volume và MA của mã mới tức thì]
```
