# Hướng Dẫn Thuật Toán Tính Thông Số & Tạo Lời Khuyên Cổ Phiếu

Tài liệu này giải thích chi tiết **cơ chế tính toán các chỉ số kỹ thuật (TA)**, **đánh giá cơ bản doanh nghiệp (FA)** và **thuật toán sinh lời khuyên / khuyến nghị hành động tự động** trong hệ thống **Stock Pro Analytics**.

---

## 1. Kiến Trúc Hệ Thống Đánh Giá Đa Chiều

Hệ thống kết hợp mô hình phân tích định lượng 2 trụ cột:
```
                     ┌───────────────────────────────────┐
                     │     Dữ Liệu Đầu Vào Thời Gian Thực│
                     └─────────────────┬─────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
┌───────────────────────────────┐             ┌───────────────────────────────────┐
│     Phân Tích Kỹ Thuật (TA)   │             │     Phân Tích Cơ Bản (FA)         │
│  - Entrade OHLCV 120 phiên    │             │  - Báo cáo tài chính quý/năm      │
│  - SSI iBoard Mua/Bán chủ động│             │  - P/E, P/B, ROE, EPS, Nợ vay     │
│  - Trọng số: 60%              │             │  - Trọng số: 40%                  │
└───────────────┬───────────────┘             └─────────────────┬─────────────────┘
                │                                               │
                └──────────────────────┬────────────────────────┘
                                       ▼
                       ┌───────────────────────────────┐
                       │  RULE-BASED INFERENCE ENGINE  │
                       │   (Hệ thống quy tắc suy diễn) │
                       └───────────────┬───────────────┘
                                       ▼
    ┌──────────────────────────────────┼──────────────────────────────────┐
    ▼                                  ▼                                  ▼
┌───────────────────────┐  ┌───────────────────────┐  ┌───────────────────────┐
│  Thước Đo & Chỉ Báo   │  │   Khuyến Nghị T+      │  │  Khuyến Nghị Trung Hạn│
│- TA Score & FA Score  │  │- Quyết định (MUA/BÁN) │  │- Tích sản / Chờ mua   │
│- RSI, Vol Ratio, R:R  │  │- Entry, TP, Stop Loss │  │- Vùng gom, Luận điểm  │
└───────────────────────┘  └───────────────────────┘  └───────────────────────┘
```

---

## 2. Công Thức & Cách Tính Toán Các Thông Số Kỹ Thuật (TA)

Tất cả các thông số kỹ thuật được tính toán trực tiếp trong hàm `analyze_technicals_and_scoring()` tại file [server.py](file:///Users/minhpvl/Desktop/stock_rt/server.py#L462):

### 2.1. Chỉ số Sức mạnh Tương đối - RSI 14 phiên (Relative Strength Index)
- **Công thức**:
  - `RS = (Trung bình tăng 14 phiên) / (Trung bình giảm 14 phiên)`
  - `RSI = 100 - (100 / (1 + RS))`
- **Phân loại ngưỡng**:
  - `RSI > 70`: **Vùng quá mua** &rarr; Cảnh báo rủi ro đảo chiều, hạn chế mua đuổi.
  - `RSI < 35`: **Vùng quá bán** &rarr; Tiềm ẩn cơ hội bắt đáy nảy kỹ thuật.
  - `46 <= RSI <= 68`: **Vùng tích lũy xung lực lành mạnh** &rarr; Lý tưởng để giải ngân.

---

### 2.2. Đường Trung Bình Động MA20 & MA50
- **MA20 (Ngắn hạn)**: Trung bình cộng giá đóng cửa của 20 phiên giao dịch gần nhất.
- **MA50 (Trung hạn)**: Trung bình cộng giá đóng cửa của 50 phiên giao dịch gần nhất.
- **Ý nghĩa**:
  - `Giá >= MA20`: Cổ phiếu nằm trong **Kênh tăng ngắn hạn (Up-trend)**.
  - `Giá < MA20`: Cổ phiếu suy yếu, áp lực điều chỉnh ngắn hạn.
  - `MA20 cắt lên trên MA50`: Tín hiệu giao cắt vàng (Golden Cross), xu hướng tăng trung hạn được xác nhận.

---

### 2.3. Tỷ Lệ Đột Biến Khối Lượng (Volume Ratio)
Đánh giá mức độ tham gia của dòng tiền lớn so với mức trung bình 20 phiên:
- **Công thức**:
  `Vol Ratio = (Khối lượng khớp lệnh hôm nay) / (Khối lượng bình quân 20 phiên - Vol MA20)`

| Giá trị `Vol Ratio` | Tín hiệu dòng tiền | Màu sắc hiển thị |
| :--- | :--- | :--- |
| **`>= 1.5x`** | **BÙNG NỔ DÒNG TIỀN**: Dòng tiền cá mập nhập cuộc mạnh | `emerald` (Xanh ngọc) |
| **`1.0x - 1.49x`** | **Thanh khoản tích cực**: Dòng tiền duy trì tốt | `blue` (Xanh dương) |
| **`0.6x - 0.99x`** | **Thanh khoản bình quân**: Giao dịch ổn định | `slate` (Xám) |
| **`<= 0.6x`** | **Cạn cung test nền**: Lực bán đã cạn kiệt, chờ bứt phá | `amber` (Vàng) |

---

### 2.4. Tỷ Lệ Mua / Bán Chủ Động (Active Flow)
Lấy trực tiếp từ dữ liệu sổ lệnh SSI iBoard:
- `stockBUVol`: Khối lượng khớp chủ động vào giá Dư Bán (Bên mua chấp nhận mua lên).
- `stockSDVol`: Khối lượng khớp chủ động vào giá Dư Mua (Bên bán chủ động xả xuống).
- **Công thức**:
  `Buy Ratio = (stockBUVol / (stockBUVol + stockSDVol)) * 100%`
- **Ý nghĩa**: Nếu `Buy Ratio >= 55%`, phe Mua đang hoàn toàn làm chủ thế trận.

---

### 2.5. Xác Định Vùng Hỗ Trợ & Kháng Cự Động (Dynamic Support / Resistance)
Hệ thống quét biên độ dao động của **25 phiên giao dịch gần nhất** để tìm:
- **Hỗ trợ cứng (`Support Level`)**: Giá thấp nhất trong 25 phiên (`min(lows[-25:])`).
- **Kháng cự đỉnh (`Resistance Level`)**: Giá cao nhất trong 25 phiên (`max(highs[-25:])`).
- **Cơ chế tự sửa lỗi logic**:
  - Nếu `Support >= Current Price`: Tự động đặt lại hỗ trợ tại `Current Price * 0.96` (cách 4%).
  - Nếu `Resistance <= Current Price`: Tự động đặt lại kháng cự tại `Current Price * 1.08` (cách 8%).

---

### 2.6. Điểm Vào Lệnh (Entry), Chốt Lời (Target) & Cắt Lỗ (Stop Loss)
- **Vùng mua gom (Entry)**:
  - `Entry Min = max(Support * 1.01, Current Price * 0.985)`
  - `Entry Max = Current Price * 0.995`
- **Giá mục tiêu chốt lời (Target)**: Trùng với kháng cự đỉnh cũ (`Resistance Level`).
- **Giá cắt lỗ (Stop Loss)**: Đặt dưới hỗ trợ cứng 3% để phòng thủ thủng nền:
  - `Stop Loss = Support Level * 0.97`
- **Tỷ lệ Lợi nhuận / Rủi ro (R:R Ratio)**:
  - `Upside (%) = ((Target - Current Price) / Current Price) * 100%`
  - `Downside (%) = ((Current Price - Stop Loss) / Current Price) * 100%`
  - `R:R Ratio = Upside / Downside` *(Hệ thống ưu tiên các giao dịch có tỷ lệ R:R từ 1:2.0 trở lên)*.

---

## 3. Thang Điểm Kỹ Thuật (TA Score / 100)

Thang điểm kỹ thuật bắt đầu từ mốc cơ sở **40 điểm** và cộng/trừ điểm theo quy tắc định lượng:

```python
ta_score = 40

# 1. Vị thế giá so với MA (Tối đa +35 điểm)
if current_price >= ma20:
  ta_score += 25  # Giữ được kênh tăng ngắn hạn
if current_price >= ma50:
  ta_score += 10  # Xu hướng trung hạn ủng hộ

# 2. Xung lực RSI (Tối đa +15 điểm, trừ tối đa 15 điểm)
if 50 <= rsi <= 65:
  ta_score += 15  # Vùng xung lực đẹp nhất
elif 40 <= rsi < 50:
  ta_score += 8  # Chớm tích cực
elif rsi > 70:
  ta_score -= 15  # Trừ điểm vì rủi ro đu đỉnh quá mua
elif rsi < 35:
  ta_score += 5  # Thưởng điểm vì tiềm năng nảy kỹ thuật

# 3. Đột biến Volume (Tối đa +15 điểm)
if vol_ratio >= 1.5:
  ta_score += 15  # Tiền lớn vào quyết liệt
elif vol_ratio >= 1.1:
  ta_score += 8  # Thanh khoản tốt

# 4. Tỷ lệ Mua chủ động (Tối đa +10 điểm, trừ tối đa 5 điểm)
if buy_ratio >= 55:
  ta_score += 10  # Lực cầu chiếm ưu thế
elif buy_ratio < 45:
  ta_score -= 5  # Phe bán áp đảo

# Giới hạn điểm số trong khoảng [10, 98]
ta_score = max(10, min(98, ta_score))
```

---

## 4. Hệ Thống Quy Tắc Ra Lời Khuyên & Khuyến Nghị Tự Động

### 4.1. Lời khuyên Lướt Sóng Ngắn Hạn (Card T+)
Quyết định T+ được suy luận qua 5 tầng điều kiện ưu tiên:

```
                  ┌──────────────────────┐
                  │    Kiểm tra RSI?     │
                  └──────────┬───────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼ (> 72)                          ▼ (<= 72)
┌──────────────────────────────┐     ┌──────────────────────┐
│  QUÁ MUA - HẠN CHẾ ĐUA GIÁ   │     │  TA Score >= 75 và   │
│- Type: danger (Đỏ)           │     │   Vol Ratio >= 1.2?  │
│- Lý do: RSI quá cao, nguy cơ │     └──────────┬───────────┘
│  chỉnh khi gặp đỉnh cũ       │                │
└──────────────────────────────┘       ┌────────┴────────┐
                                       ▼ (Đúng)          ▼ (Sai)
                        ┌──────────────────────────────┐ ┌──────────────────────┐
                        │ MUA MẠNH - BÙNG NỔ DÒNG TIỀN │ │ Price >= MA20 và     │
                        │- Type: success (Xanh)        │ │  46 <= RSI <= 68?    │
                        │- Lý do: Vượt MA20 + Vol bùng │ └──────────┬───────────┘
                        │  nổ + Cầu chủ động cao       │            │
                        └──────────────────────────────┘   ┌────────┴────────┐
                                                           ▼ (Đúng)          ▼ (Sai)
                                            ┌──────────────────────────────┐ ┌──────────────────────┐
                                            │ MUA TÍCH LŨY T+ (ĐẠT CHUẨN)  │ │      RSI < 36?       │
                                            │- Type: success (Xanh)        │ └──────────┬───────────┘
                                            │- Lý do: Nền giá trên MA20,   │            │
                                            │  RSI chuẩn, R/R tốt          │   ┌────────┴────────┐
                                            └──────────────────────────────┘   ▼ (Đúng)          ▼ (Sai)
                                                                ┌──────────────────────────────┐ ┌──────────────────────────────┐
                                                                │  BẮT ĐÁY NẢY KỸ THUẬT        │ │  QUAN SÁT / CHƯA CÓ ĐIỂM VÀO │
                                                                │- Type: warning (Vàng)        │ │- Type: danger (Đỏ)           │
                                                                │- Lý do: Quá bán chạm hỗ trợ  │ │- Lý do: Giá dưới MA20, bán   │
                                                                │  cứng, nhịp hồi T+3          │ │  chủ động áp đảo             │
                                                                └──────────────────────────────┘ └──────────────────────────────┘
```

#### Chi tiết các trường hợp:
1. **`RSI > 72`**:
   - **Quyết định**: `QUÁ MUA - HẠN CHẾ ĐUA GIÁ` (Màu đỏ cảnh báo).
   - **Lời khuyên**: RSI chạm vùng quá mua, giá tiệm cận kháng cự đỉnh cũ. Ưu tiên canh chốt lời, tuyệt đối không mua đuổi.
2. **`TA Score >= 75` và `Vol Ratio >= 1.2`**:
   - **Quyết định**: `MUA MẠNH - BÙNG NỔ DÒNG TIỀN` (Màu xanh ngọc).
   - **Lời khuyên**: Giá giữ vững trên MA20, khối lượng bùng nổ gấp `x{vol_ratio}` lần bình quân. Lực mua chủ động áp đảo (`{buy_ratio}%`).
3. **`Price >= MA20` và `46 <= RSI <= 68`**:
   - **Quyết định**: `MUA TÍCH LŨY T+ (ĐẠT CHUẨN)` (Màu xanh ngọc).
   - **Lời khuyên**: Nến duy trì trên MA20, RSI lành mạnh, tỷ lệ R:R đạt chuẩn `1:{rr_ratio}`. Mở vị thế gom trong các nhịp rung lắc.
4. **`RSI < 36`**:
   - **Quyết định**: `BẮT ĐÁY NẢY KỸ THUẬT (RỦI RO CAO)` (Màu vàng).
   - **Lời khuyên**: Cổ phiếu chiết khấu sâu về vùng hỗ trợ cứng `{support} đ`. Đánh nhanh nhịp hồi phục T+3 kiểm định lại MA20.
5. **Các trường hợp còn lại**:
   - **Quyết định**: `QUAN SÁT / CHƯA CÓ ĐIỂM VÀO` (Màu xám/đỏ).
   - **Lời khuyên**: Giá vận động dưới MA20, lực bán chủ động vẫn chiếm ưu thế. Cần chờ dòng tiền lớn xác nhận lại xu hướng.

---

### 4.2. Lời khuyên Đầu Tư Trung & Dài Hạn (Card Trung Hạn)
Dựa trên chất lượng doanh nghiệp (FA Score), ROE, P/E và vị thế giá so với đường MA50:

1. **`FA Score >= 70` và `Current Price <= MA50 * 1.08`**:
   - **Quyết định**: `GOM MUA TÍCH SẢN (VÙNG GIÁ TỐT)` (Màu xanh).
   - **Lời khuyên**: Doanh nghiệp cơ bản xuất sắc (Hạng A), ROE `{roe}%`. Vùng giá đang chiết khấu an toàn gần MA50, thích hợp gom dần tích sản theo phương pháp DCA.
2. **`P/E > 22.0`**:
   - **Quyết định**: `CHỜ CHIẾT KHẤU THÊM (P/E CAO)` (Màu vàng).
   - **Lời khuyên**: P/E hiện tại `{pe}x` đã phản ánh phần lớn kỳ vọng tương lai, biên an toàn chưa đủ dày để giải ngân tỷ trọng lớn.
3. **Mặc định**:
   - **Quyết định**: `NẮM GIỮ THEO DÕI NỀN` (Màu vàng).
   - **Lời khuyên**: Định giá ở mức hợp lý, tiếp tục theo dõi báo cáo kết quả kinh doanh quý tiếp theo.

---

### 4.3. Banner Kết Luận Toàn Diện (Overall Verdict)
Tổng hợp điểm số chung theo trọng số:
- **Công thức tính điểm**:
  `Total Score = (TA Score * 0.60) + (FA Score * 0.40)`


| Điều kiện | Danh hiệu & Đánh giá tổng hợp | Màu sắc |
| :--- | :--- | :--- |
| `TA Score >= 75` & `FA Score >= 70` | 🌟 **CỔ PHIẾU HOÀN HẢO**: FA xuất sắc & Dòng tiền T+ bùng nổ | `emerald` |
| `TA Score >= 70` | ⚡ **DÒNG TIỀN T+ MẠNH**: Ưu tiên lướt sóng ngắn hạn | `blue` |
| `FA Score >= 75` | 💎 **DOANH NGHIỆP GIÁ TRỊ**: Thích hợp gom tích sản trung hạn | `indigo` |
| `TA Score < 45` & `FA Score < 50` | ⚠️ **CẢNH BÁO RỦI RO**: Cả kỹ thuật và cơ bản đều suy yếu | `rose` |
| Trường hợp khác | ⏳ **TRẠNG THÁI TRUNG TÍNH**: Tích lũy chờ đợi tín hiệu mới | `amber` |

---

## 5. Bảng Chỉ Số Tài Chính Cơ Bản (Fundamental Metrics - FA)

Dữ liệu cơ bản được tự động tải từ **BCTC thực tế thông qua thư viện `vnstock`** và lưu đệm vào SQLite tại [server.py](file:///Users/minhpvl/Desktop/stock_rt/server.py#L130-L330):


| Chỉ số | Ý nghĩa | Ngưỡng đánh giá tốt |
| :--- | :--- | :--- |
| **P/E (Price to Earnings)** | Định giá theo lợi nhuận | `<= 15.0x` (rẻ), `15 - 20x` (hợp lý), `> 22x` (cao) |
| **P/B (Price to Book)** | Định giá theo giá trị sổ sách | `<= 1.8x` đối với ngân hàng, `<= 2.5x` đối với sản xuất |
| **ROE (%)** | Hiệu quả sinh lời trên vốn chủ | `>= 18%` (Doanh nghiệp có lợi thế cạnh tranh bền vững) |
| **EPS (VNĐ)** | Lợi nhuận kiếm được trên mỗi cổ phần | Càng cao càng tốt (tối thiểu `> 2.500 đ`) |
| **Tăng trưởng DT / LN (%)** | Tốc độ tăng trưởng so với cùng kỳ | `> 15% / năm` thể hiện doanh nghiệp đang mở rộng quy mô |
| **D/E (Nợ / Vốn chủ sở hữu)** | Đòn bẩy tài chính & sức khỏe nợ | `<= 1.0x` (Sản xuất), `<= 3.0x` (Xây lắp/BĐS) |

---

## 6. Ví Dụ Cụ Thể Về Output Trả Về Của 1 Mã

Khi gọi API `/api/stock?ticker=FPT&resolution=1D`, JSON trả về chứa đầy đủ các phân tích trên:

```json
{
  "code": "FPT",
  "name": "Công ty Cổ phần FPT",
  "price": 62700,
  "percentChange": 0.32,
  "technicals": {
    "rsi": 58.4,
    "ma20": 61200,
    "ma50": 58900,
    "volRatio": 1.45,
    "volSignal": "Thanh khoản tích cực (x1.45)",
    "buyRatio": 59.2,
    "support": 59500,
    "resistance": 66000,
    "rrRatio": 2.1,
    "taScore": 82,
    "totalScore": 84,
    "overallStatus": "🌟 CỔ PHIẾU HOÀN HẢO: FA xuất sắc & Dòng tiền T+ bùng nổ",
    "overallColor": "emerald",
    "tPlus": {
      "decision": "MUA MẠNH - BÙNG NỔ DÒNG TIỀN",
      "type": "success",
      "entry": "61.500 - 62.200 đ",
      "target": "66.000 đ (+5.3%)",
      "stop": "57.700 đ (-8.0%)",
      "reason": "Giá giữ vững trên MA20 (61.200 đ), Volume bùng nổ gấp 1.45x lần trung bình 20 phiên. Lực cầu chủ động chiếm 59.2%."
    },
    "midTerm": {
      "decision": "GOM MUA TÍCH SẢN (VÙNG GIÁ TỐT)",
      "type": "success",
      "entry": "59.000 - 62.000 đ",
      "target": "75.000 đ (+19.6%)",
      "stop": "55.000 đ",
      "reason": "Doanh nghiệp FA loại A (Tập đoàn FPT), ROE đạt 27.5%. Giá chiết khấu hấp dẫn gom theo phương pháp DCA."
    }
  },
  "fundamentals": {
    "pe": 21.8,
    "pb": 5.2,
    "roe": 27.5,
    "eps": 4850,
    "faScore": 88
  }
}
```

---

## 7. Chuyên Gia Định Lượng & Đánh Giá Rủi Ro (Securities Risk Assessment Engine)

Hệ thống tích hợp bộ công cụ định lượng độc lập và đánh giá rủi ro chuyên sâu chuẩn 5 phần, vận hành dựa trên **3 Nguyên tắc bất di bất dịch (Grounding Rules)** và **Hệ thống Ngưỡng chặn (Risk Guardrails)**:

### 7.1. Ba Nguyên Tắc Bất Di Bất Dịch (Grounding Rules)
1. **Không suy diễn ngoài dữ liệu**: Tuyệt đối không tự bịa đặt chỉ số tài chính, tin tức hay sự kiện không có trong payload đầu vào. Nếu một trường dữ liệu ghi "Không có", "Chưa cập nhật" hoặc rỗng, nêu rõ là *"Dữ liệu chưa ghi nhận"*.
2. **Khách quan đa chiều**: Mọi nhận định tích cực phải đi kèm ít nhất một yếu tố rủi ro tương ứng được tìm thấy trong dữ liệu thực tế.
3. **Phân biệt giữa Dự báo và Thực tế**: Luôn chỉ rõ số liệu nào là thực tế quá khứ/hiện tại và nhận định nào mang tính xác suất kịch bản.

### 7.2. Ba Ngưỡng Chặn Rủi Ro (Risk Guardrails)
- **🚨 Guardrail 1 (Hưng phấn quá mức + Khối ngoại xả hàng)**:
  - Nếu `market_fear_greed_index > 80` (hoặc RSI > 72 & tâm lý hưng phấn) kết hợp khối ngoại bán ròng mạnh (`foreign_net < -50.000` cp): Buộc AI hạ tỷ trọng khuyến nghị mua mới, ưu tiên quản trị chốt lời bảo vệ thành quả.
- **🛑 Guardrail 2 (Rủi ro pháp lý / Pha loãng sâu)**:
  - Nếu phát hiện cờ cảnh báo về tranh chấp pháp lý (`legal_disputes`) hoặc kế hoạch phát hành riêng lẻ chiết khấu sâu: Chuyển trạng thái khuyến nghị sang *"Thận trọng / Hạn chế giao dịch"* bất chấp tín hiệu kỹ thuật.
- **⚠️ Guardrail 3 (Chất lượng Lợi nhuận kém + Đòn bẩy Nợ cao)**:
  - Nếu Dòng tiền thuần HĐKD (`OCF < 0`) kết hợp đòn bẩy Nợ/VCSH cao (`D/E > 1.8x`) hoặc Sức mạnh giá quá yếu (`RS < 40`): Cảnh báo rủi ro dòng tiền giấy/khoản phải thu, tự động thắt chặt trần giải ngân không quá 10% NAV và cấm dùng đòn bẩy Margin.

### 7.3. Cấu Trúc Đầu Ra 5 Phần Bắt Buộc
1. **Tổng quan tác động Vĩ mô & Ngành**: Đánh giá môi trường [Tích cực / Trung lập / Bất lợi], tác động từ lãi suất, tỷ giá, lạm phát đến biên LN & chi phí vốn.
2. **Nội tại & Rủi ro pháp lý doanh nghiệp**: Chất lượng tăng trưởng (BCTC vs P/E, P/B, ROE, OCF & Gross/Net Margin) và rủi ro quản trị & pha loãng.
3. **Dòng tiền & Tâm lý thị trường**: Dòng vốn khối ngoại, Fear & Greed Index, Sức mạnh giá tương đối RS O'Neil (1-99) và Alpha vs VN-Index.
4. **Ma trận kịch bản kỳ vọng & Quản trị rủi ro**: Bull Case (kích hoạt, mục tiêu giá), Bear Case (rủi ro, hỗ trợ/cắt lỗ), Tỷ lệ R:R.
5. **Kết luận hành động**: Trạng thái [Tích lũy / Theo dõi / Hạ tỷ trọng / Mở vị thế thăm dò / Thận trọng / Hạn chế giao dịch], Hướng dẫn quy mô vị thế (Pilot 35% vs Pyramid 65%), Lưu ý cốt lõi quan trọng nhất.

---

## 8. Các Tiêu Chí Nâng Cao Chuẩn Quỹ Đầu Tư Định Lượng (Advanced Institutional Criteria)

Để khắc phục hoàn toàn những hạn chế của phân tích kỹ thuật đơn lẻ hoặc phân tích tài chính tĩnh, hệ thống đã tích hợp 4 tiêu chí cốt lõi chuẩn Phố Wall và các Quỹ tương hỗ (Mutual Funds):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                 BỐN TRỤ CỘT ĐỊNH LƯỢNG NÂNG CAO (INSTITUTIONAL)              │
├───────────────────────────────┬─────────────────────────────────────────────┤
│ 1. SỨC MẠNH GIÁ RS O'NEIL     │ So sánh tương quan Alpha với VN-Index       │
│    (CANSLIM Rating 1-99)      │ Phân loại Siêu cổ phiếu dẫn dắt (Leader)    │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ 2. CHẤT LƯỢNG LỢI NHUẬN (OCF) │ Dòng tiền HĐKD thực tế vs LNST sổ sách      │
│    & BIÊN LỢI NHUẬN / NIM     │ Nhận diện bẫy "lợi nhuận trên giấy"         │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ 3. QUẢN TRỊ VỊ THẾ & NAV      │ Ngân sách rủi ro cố định 1.5% NAV           │
│    (Position Sizing Guide)    │ Giải ngân Pilot (35%) -> Pyramid (65%)      │
├───────────────────────────────┼─────────────────────────────────────────────┤
│ 4. ĐA KHUNG THỜI GIAN         │ Đồng thuận Xu hướng D1 (MA20) & W1 (MA10)   │
│    (Multi-Timeframe Confluence│ Tránh bẫy Bulltrap / Beartrap ngược xu thế  │
└───────────────────────────────┴─────────────────────────────────────────────┘
```

### 8.1. Chỉ Số Sức Mạnh Giá Tương Đối RS Rating (1 - 99 vs VN-Index)
Dựa trên nguyên lý **CANSLIM của William O'Neil**: Nhà đầu tư tổ chức luôn tìm kiếm cổ phiếu thể hiện sức mạnh vượt trội hơn thị trường chung.

- **Dữ liệu đầu vào**:
  - Chuỗi nến đóng cửa 120 phiên của cổ phiếu và chỉ số VN-Index (lấy từ cổng API Entrade Real-time).
- **Công thức tính toán**:
  - `Return 1 Tháng (1M) = (Close_t / Close_{t-20} - 1) * 100%`
  - `Return 3 Tháng (3M) = (Close_t / Close_{t-60} - 1) * 100%`
  - `Alpha 1M = Return_CP_1M - Return_VNI_1M`
  - `Alpha 3M = Return_CP_3M - Return_VNI_3M`
  - Điểm hiệu suất tổng hợp: `Weighted Return = (Return_1M * 0.40) + (Return_3M * 0.60)`
  - Điểm hiệu suất VN-Index: `Weighted VNI = (VNI_1M * 0.40) + (VNI_3M * 0.60)`
  - `Alpha Composite = Weighted Return - Weighted VNI`
  - `RS Score = int(clamp(50 + (Alpha Composite * 1.5), 1, 99))`
- **Phân loại cấp bậc (Tier)**:
  - `RS >= 80`: **Siêu cổ phiếu (Top 20% dẫn dắt)** &rarr; Ưu tiên số 1 khi thị trường chung tạo đáy hoặc bứt phá.
  - `65 <= RS < 80`: **Trên trung bình (Outperform)** &rarr; Cổ phiếu khỏe, thanh khoản tốt.
  - `45 <= RS < 65`: **Trung bình (In-line thị trường)** &rarr; Vận động bám sát chỉ số chung.
  - `RS < 45`: **Yếu hơn thị trường (Laggard)** &rarr; Tránh mua bắt đáy vì dòng tiền lớn chưa tham gia.

---

### 8.2. Đánh Giá Chất Lượng Lợi Nhuận (Quality of Earnings: OCF vs LNST) & Biên Lãi
Một doanh nghiệp có LNST tăng trưởng cao vẫn có thể phá sản nếu dòng tiền kinh doanh bị âm liên tục do bị khách hàng chiếm dụng vốn (nợ đọng phải thu) hoặc tồn kho ứ đọng.

- **Dòng tiền thuần HĐKD (Operating Cash Flow - OCF)**:
  - Khai thác từ Báo cáo Lưu chuyển Tiền tệ quý gần nhất (nguồn BCTC chuẩn kiểm toán).
  - So sánh `OCF` với Lợi nhuận Sau thuế (`LNST`):
    - `OCF > 0` và `OCF >= LNST`: **Chất lượng LN loại A (Tiền tươi thóc thật)** &rarr; Khả năng trả nợ và chia cổ tức tiền mặt vững chắc.
    - `OCF > 0` nhưng `OCF < LNST`: **Trung bình** &rarr; Doanh nghiệp cần vốn lưu động cho chu kỳ kinh doanh.
    - `OCF < 0` trong khi LNST dương: **BÁO ĐỘNG ĐỎ** &rarr; Lợi nhuận chỉ nằm trên sổ sách, rủi ro nợ xấu và tắc nghẽn thanh khoản tiềm ẩn.
- **Biên Lợi Nhuận (Gross / Net Margin)**:
  - `Biên Lợi Nhuận Gộp = (Lợi nhuận gộp / Doanh thu thuần) * 100%`: Đo lường lợi thế cạnh tranh độc quyền (Moat) và năng lực chuyển áp lực giá đầu vào sang khách hàng.
  - `Biên Lợi Nhuận Ròng = (LNST / Doanh thu thuần) * 100%`: Đo lường hiệu quả quản lý chi phí tài chính, bán hàng và quản lý DN.
  - **Chỉ tiêu chuyên biệt cho Ngành Ngân Hàng**:
    - **NIM (Net Interest Margin - Biên Lãi Thuần)**: Thước đo hiệu quả sinh lời cốt lõi của ngân hàng thương mại.
    - **LDR (Loan to Deposit Ratio - Tỷ lệ Dư tín dụng / Vốn huy động)**: Giám sát an toàn thanh khoản theo quy định của Ngân hàng Nhà nước.

---

### 8.3. Hướng Dẫn Quản Trị Vị Thế & Quy Mô Giải Ngân (Position Sizing Guide)
Nhà đầu tư chuyên nghiệp không bao giờ "all-in" vào 1 lệnh hoặc mua bình quân giá xuống (averaging down) khi đang lỗ.

- **Ngân Sách Rủi Ro Cố Định (Fixed Portfolio Risk Budget = 1.5% NAV)**:
  - Không cho phép khoản lỗ tối đa của một vị thế vượt quá **1.5% tổng tài sản ròng (NAV)**.
  - Khoảng cách cắt lỗ: `% Stop Loss = (Entry Price - Stop Loss Price) / Entry Price * 100%`
  - Quy mô vị thế tối đa được phép:
    $$\text{Max \% NAV} = \min\left(25\%,\; \text{round}\left(\frac{1.5\%}{\% \text{Stop Loss}} \times 100\%\right)\right)$$
    *(Khống chế trần không vượt quá 25% NAV cho một cổ phiếu riêng lẻ để đảm bảo đa dạng hóa danh mục).*
- **Chiến Thuật Mua Kim Tự Tháp 2 Bước (Pyramiding Strategy)**:
  - **Bước 1 - Vị thế Thăm dò (Pilot Position - 35% quy mô mục tiêu)**:
    - Giải ngân khi cổ phiếu xuất hiện điểm mua kỹ thuật chuẩn (Pocket Pivot, Test MA20 thành công).
  - **Bước 2 - Vị thế Gia tăng (Pyramid Position - 65% còn lại)**:
    - **Chỉ kích hoạt** khi vị thế thăm dò đã chạy và sinh lãi đệm an toàn (`+3% đến +5%`).
    - Tuyệt đối không gia tăng vị thế khi lô thăm dò đang bị âm tiền.

---

### 8.4. Đồng Thuận Xu Hướng Đa Khung Thời Gian (Multi-Timeframe Trend Confluence)
Tránh "nhìn một cây mà không thấy cả cánh rừng" bằng cách kết hợp khung Ngày (D1) và khung Tuần (W1):

- **Khung Trung Hạn - Tuần (W1)**: Đường trung bình động **10 tuần (Weekly MA10)** đại diện cho chi phí vốn trung bình của các quỹ đầu tư lớn trong 2.5 tháng.
- **Khung Ngắn Hạn - Ngày (D1)**: Đường trung bình động **20 ngày (Daily MA20)** định hướng điểm xoay T+.
- **3 Trạng thái Đồng thuận**:
  1. **ĐỒNG THUẬN TĂNG (BULLISH CONFLUENCE)**:
     - `Giá > D1 MA20` **VÀ** `Giá > W1 MA10`: Xu hướng lớn và xu hướng ngắn hạn cùng ủng hộ. Độ an toàn cao nhất, tự tin giải ngân đủ tỷ trọng.
  2. **ĐỒNG THUẬN GIẢM (BEARISH CONFLUENCE)**:
     - `Giá < D1 MA20` **VÀ** `Giá < W1 MA10`: Cổ phiếu nằm trong kênh Downtrend trung - dài hạn. Mọi nhịp bật tăng ngắn hạn chỉ là bẫy Bulltrap. Khuyến nghị đứng ngoài.
  3. **XUNG ĐỘT KHUNG THỜI GIAN (PULLBACK / DIVERGENCE)**:
     - `Giá < MA20 ngày` nhưng `Giá > MA10 tuần`: Nhịp điều chỉnh bình thường trong một xu hướng tăng lớn (Cơ hội mua rung lắc).
     - `Giá > MA20 ngày` nhưng `Giá < MA10 tuần`: Nhịp hồi kỹ thuật ngắn hạn gặp cản xu hướng tuần. Chỉ nên lướt sóng nhanh với tỷ trọng nhỏ (Pilot).


