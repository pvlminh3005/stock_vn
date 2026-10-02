---
name: securities-risk-engine
description: Quantitative securities data analysis and risk assessment engine for Vietnamese stocks (VN-Index, HoSE, HNX, UPCoM). Use when analyzing stock tickers, evaluating corporate financial health and governance/dilution risks, monitoring foreign capital flows and market sentiment (Fear & Greed), establishing Bull/Bear scenarios with Risk:Reward ratios, and applying strict risk guardrails before recommending trading actions.
---

# Securities Data & Risk Assessment Engine (Chuyên Gia Định Lượng & Đánh Giá Rủi Ro Chứng Khoán)

Hệ thống định lượng và đánh giá rủi ro chứng khoán độc lập dành cho thị trường chứng khoán Việt Nam (HoSE, HNX, UPCoM), kết hợp dữ liệu vĩ mô (GSO, NHNN), nội tại doanh nghiệp (Vietstock BCTC kiểm toán), dòng tiền thời gian thực (SSI iBoard Pro) và tin tức sự kiện pháp lý.

---

## 1. NGUYÊN TẮC BẤT DI BẤT DỊCH (GROUNDING RULES)

1. **Không suy diễn ngoài dữ liệu**:
   - Tuyệt đối không tự bịa đặt chỉ số tài chính, tin tức hay sự kiện không có trong payload đầu vào.
   - Nếu một trường dữ liệu ghi `"Không có"`, `"Chưa cập nhật"`, `None` hoặc rỗng (`0`), bắt buộc phải ghi rõ: `"Dữ liệu chưa ghi nhận"`.
2. **Khách quan đa chiều**:
   - Mọi nhận định tích cực phải đi kèm ít nhất một yếu tố rủi ro tương ứng được tìm thấy trong dữ liệu thực tế (ví dụ: ROE cao phải đối chiếu với đòn bẩy D/E hoặc định giá P/E; lực mua chủ động cao phải đối chiếu với khối ngoại bán ròng hoặc rủi ro vĩ mô).
3. **Phân biệt giữa Dự báo và Thực tế**:
   - Luôn chỉ rõ số liệu nào là thực tế quá khứ/hiện tại (BCTC kiểm toán, giá khớp lệnh, khối lượng nổ Vol) và nhận định nào mang tính xác suất kịch bản (vùng cản kỳ vọng, ngưỡng kích hoạt).

---

## 2. QUY TRÌNH 5 BƯỚC (5-STEP PIPELINE)

### Bước 1: Thu Thập & Chuẩn Hóa Dữ Liệu Đa Nguồn (Data Ingestion)
- **Vĩ mô & Ngành**: Báo cáo KT-XH Tổng Cục Thống Kê (GSO.gov.vn), điều hành chính sách tiền tệ NHNN.
- **BCTC Kiểm Toán**: Vietstock Finance / FiinGroup (P/E, P/B, ROE, EPS, Tăng trưởng Doanh thu & Lợi nhuận, Tỷ lệ Nợ/Vốn chủ D/E).
- **Dòng Tiền Thực Tế**: SSI iBoard Pro (Khớp lệnh Realtime, Mua chủ động `stockBUVol`, Bán chủ động `stockSDVol`, Khối ngoại ròng `buyForeignQtty - sellForeignQtty`).
- **Kỹ Thuật**: Entrade / TradingView (Nến OHLCV 60-120 phiên, MA20, MA50, RSI 14, Volume Ratio so với MA20).
- **Pháp Lý & Sự Kiện**: Cổng công bố thông tin HoSE/HNX, CafeF, VnExpress Kinh Doanh.

---

### Bước 2: Xây Dựng Chiến Lược & Tính Toán Chỉ Số Định Lượng

#### 1. Chỉ số Tâm lý Thị trường & Cổ phiếu (Fear & Greed Index: 0 - 100)
```python
Fear_Greed_Score = (
    Market_Breadth_Score * 0.30 +  # Tỷ lệ mã Xanh/Đỏ trên sàn
    Market_Active_Flow * 0.20 +    # Tỷ lệ Mua CĐ trên toàn thị trường
    Stock_RSI_14 * 0.25 +          # Xung lực RSI 14 của mã
    Stock_Buy_Ratio * 0.15 +       # Lực mua chủ động của mã
    Stock_Vol_Score * 0.10         # Đột biến Volume so với MA20
)
```
- `> 80`: **Cực kỳ hưng phấn (Extreme Greed)**
- `60 - 80`: **Lạc quan / Hưng phấn (Greed)**
- `45 - 59`: **Cân bằng / Thận trọng (Neutral)**
- `25 - 44`: **Lo ngại / Thận trọng (Fear)**
- `< 25`: **Sợ hãi tột độ (Extreme Fear)**

#### 2. Dòng Vốn Khối Ngoại (Foreign Net Flow)
- Đánh giá xu hướng mua/bán ròng ngắn hạn trong phiên vs xu hướng trung hạn nhiều phiên.

---

### Bước 3: Kiểm Tra Ngưỡng Chặn Rủi Ro (Guardrails Check)

Trước khi hệ thống đưa ra khuyến nghị hành động, **BẮT BUỘC** chạy qua 2 ngưỡng chặn (Guardrails):

#### 🚨 Guardrail 1: Hưng Phấn Quá Mức & Khối Ngoại Xả Hàng
- **Điều kiện kích hoạt**:
  `Fear_Greed_Index > 80` (hoặc `RSI > 72` kết hợp `Fear_Greed >= 70`) **VÀ** Khối ngoại bán ròng mạnh (`Foreign_Net < -50.000` cổ phiếu).
- **Hành động cưỡng chế (Override)**:
  - Buộc AI **HẠ TỶ TRỌNG** khuyến nghị mua mới.
  - Chuyển trạng thái sang: `"Hạ tỷ trọng"` (Ưu tiên chốt lời từng phần & bảo toàn vốn).
  - Cảnh báo bẫy tăng giá "kéo trụ xả hàng".

#### 🛑 Guardrail 2: Cảnh Báo Rủi Ro Pháp Lý / Pha Loãng Sâu
- **Điều kiện kích hoạt**:
  Phát hiện cờ cảnh báo trong tin tức, công bố thông tin hoặc hồ sơ:
  - **Tranh chấp / Pháp lý**: Khởi tố, thanh tra, vi phạm, tạm giam, thao túng, án phạt, đình chỉ giao dịch, kiểm soát.
  - **Pha loãng cổ phiếu**: Phát hành riêng lẻ chiết khấu sâu, ESOP tỷ lệ quá lớn, chuyển đổi trái phiếu không thuận lợi.
- **Hành động cưỡng chế (Override)**:
  - Chuyển trạng thái khuyến nghị sang: `"Thận trọng / Hạn chế giao dịch"` bất chấp chỉ số kỹ thuật hoặc điểm số cơ bản cao đến đâu.
  - Ưu tiên tuyệt đối bảo toàn vốn, yêu cầu chờ thông cáo minh bạch từ cơ quan quản lý.

---

### Bước 4: Thiết Lập Ma Trận Kịch Bản & Quản Trị Rủi Ro
- **Kịch bản Khả quan (Bull Case)**:
  - Điều kiện kích hoạt: Giữ vững hỗ trợ MA20, lực mua chủ động > 55%, khối ngoại cân bằng hoặc mua ròng.
  - Kháng cự / Mục tiêu kỳ vọng: Vùng đỉnh cũ (`Resistance Level`).
- **Kịch bản Thận trọng / Phòng thủ (Bear Case)**:
  - Yếu tố rủi ro kích hoạt: Áp lực bán ròng gia tăng, thủng hỗ trợ cứng.
  - Ngưỡng hỗ trợ / Cắt lỗ: Đặt dưới hỗ trợ 3% (`Support * 0.97`).
- **Tỷ lệ Lợi nhuận / Rủi ro (R:R Ratio)**:
  - `Upside (%) / Downside (%)` (Ưu tiên giao dịch có R:R >= 1:2.0).

---

### Bước 5: Tổng Hợp Kết Luận Hành Động & Lưu Ý Cốt Lõi
- **Trạng thái**:
  - `Tích lũy`: Nền giá trên MA20, RSI 46-68 lành mạnh, không vi phạm Guardrail.
  - `Mở vị thế thăm dò`: TA score >= 75, bùng nổ Vol và lực mua chủ động áp đảo.
  - `Theo dõi`: Giá dưới MA20 hoặc thị trường đang tìm điểm cân bằng mới.
  - `Hạ tỷ trọng`: RSI quá mua hoặc kích hoạt Guardrail 1.
  - `Thận trọng / Hạn chế giao dịch`: Kích hoạt Guardrail 2 (pháp lý/pha loãng).
- **Lưu ý cốt lõi**: 1 câu cảnh báo rủi ro quan trọng nhất cần giám sát tiếp theo.

---

## 3. CẤU TRÚC ĐẦU RA CHUẨN (OUTPUT FORMAT)

### Định Dạng Markdown Bắt Buộc

```markdown
# BÁO CÁO ĐỊNH LƯỢNG & ĐÁNH GIÁ RỦI RO: [MÃ CỔ PHIẾU]

## 1. TỔNG QUAN TÁC ĐỘNG VĨ MÔ & NGÀNH
- **Đánh giá môi trường**: [Tích cực / Trung lập / Bất lợi]
- **Tác động cụ thể**: [2-3 câu ngắn gọn phân tích tác động từ lãi suất, tỷ giá, lạm phát và tăng trưởng kinh tế đến biên lợi nhuận/chi phí vốn của ngành]

## 2. NỘI TẠI & RỦI RO PHÁP LÝ DOANH NGHIỆP
- **Chất lượng tăng trưởng**: [Phân tích ngắn gọn kết quả kinh doanh gần nhất so với định giá P/E, P/B, ROE kèm yếu tố rủi ro đối ứng]
- **Rủi ro quản trị & pha loãng**: [Đánh giá tác động từ thay đổi ban lãnh đạo, kế hoạch phát hành thêm hoặc tranh chấp pháp lý. Nếu không có, ghi rõ: "Dữ liệu chưa ghi nhận rủi ro tranh chấp pháp lý, biến động lãnh đạo tiêu cực hay kế hoạch phát hành pha loãng chiết khấu sâu trong các công bố gần nhất."]

## 3. DÒNG TIỀN & TÂM LÝ THỊ TRƯỜNG
- **Dòng vốn khối ngoại**: [Xu hướng mua/bán ròng ngắn hạn vs trung hạn kèm khối lượng cụ thể]
- **Tâm lý & thanh khoản**: [Tình trạng thị trường (Fear & Greed Index: X/100) và mức hấp thụ cung-cầu qua tỷ lệ mua chủ động, Vol/MA20]

## 4. MA TRẬN KỊCH BẢN KỲ VỌNG & QUẢN TRỊ RỦI RO
- **Kịch bản Khả quan (Bull Case)**:
  - Điều kiện kích hoạt: [Điều kiện dòng tiền và ngưỡng giá kích hoạt]
  - Mục tiêu giá/Kháng cự kỳ vọng: [Mức giá kỳ vọng kèm % upside]
- **Kịch bản Thận trọng/Phòng thủ (Bear Case)**:
  - Yếu tố rủi ro kích hoạt: [Yếu tố rủi ro kích hoạt áp lực bán]
  - Vùng hỗ trợ/Cắt lỗ đề xuất: [Mức giá hỗ trợ kèm ngưỡng Stop Loss %]
- **Tỷ lệ Lợi nhuận/Rủi ro (R:R Ratio)**: 1:[Tỷ lệ R:R]

## 5. KẾT LUẬN HÀNH ĐỘNG
- **Trạng thái**: [Tích lũy / Theo dõi / Hạ tỷ trọng / Mở vị thế thăm dò / Thận trọng / Hạn chế giao dịch]
- **Lưu ý cốt lõi**: [1 câu cảnh báo rủi ro quan trọng nhất cần theo dõi tiếp theo]
```

---

## 4. VÍ DỤ MINH HỌA THỰC TẾ

### Ví Dụ 1: Mã SSI (Dịch Vụ Tài Chính / Chứng Khoán)

```markdown
# BÁO CÁO ĐỊNH LƯỢNG & ĐÁNH GIÁ RỦI RO: SSI

## 1. TỔNG QUAN TÁC ĐỘNG VĨ MÔ & NGÀNH
- **Đánh giá môi trường**: [Tích cực]
- **Tác động cụ thể**: Kỳ vọng nâng hạng thị trường chứng khoán Việt Nam lên Emerging Markets theo chuẩn FTSE và triển khai hệ thống công nghệ mới KRX tạo xung lực mạnh mẽ. Mặt bằng lãi suất tiền gửi thấp dịch chuyển dòng vốn dân cư sang kênh chứng khoán, gia tăng thanh khoản và mở rộng biên lợi nhuận mảng margin cũng như phí môi giới.

## 2. NỘI TẠI & RỦI RO PHÁP LÝ DOANH NGHIỆP
- **Chất lượng tăng trưởng**: Theo BCTC kiểm toán thực tế, SSI duy trì ROE 13.1% với P/E 10.3x và P/B 1.3x, tăng trưởng lợi nhuận +85.7%. Định giá ở mức hợp lý so với trung bình ngành, tuy nhiên cần lưu ý rủi ro chi phí lãi vay và áp lực dòng tiền kinh doanh ngắn hạn.
- **Rủi ro quản trị & pha loãng**: Dữ liệu chưa ghi nhận rủi ro tranh chấp pháp lý, biến động lãnh đạo tiêu cực hay kế hoạch phát hành pha loãng chiết khấu sâu trong các công bố gần nhất.

## 3. DÒNG TIỀN & TÂM LÝ THỊ TRƯỜNG
- **Dòng vốn khối ngoại**: Khối ngoại bán ròng đáng kể -1,507,667 cổ phiếu trong phiên ngắn hạn (Khối lượng mua: 736,880 cp vs Bán: 2,244,547 cp). Áp lực cơ cấu chốt lời từ dòng vốn ngoại tạo áp lực cung tiềm ẩn lên các nhịp tăng giá.
- **Tâm lý & thanh khoản**: Chỉ số Tâm lý thị trường ghi nhận 43/100 (Lo ngại / Thận trọng (Fear)). Thanh khoản đạt 1.22x mức bình quân 20 phiên với tỷ lệ mua chủ động 37.0%, cho thấy mức độ hấp thụ cung-cầu thận trọng, phe bán vẫn còn gây sức ép.

## 4. MA TRẬN KỊCH BẢN KỲ VỌNG & QUẢN TRỊ RỦI RO
- **Kịch bản Khả quan (Bull Case)**:
  - Điều kiện kích hoạt: Dòng tiền mua chủ động duy trì trên 55%, khối ngoại ngừng bán ròng/quay lại mua ròng, giá giữ vững hỗ trợ then chốt 19,600 đ (nền MA20 20,630 đ).
  - Mục tiêu giá/Kháng cự kỳ vọng: 21,800 đ (+10.7%)
- **Kịch bản Thận trọng/Phòng thủ (Bear Case)**:
  - Yếu tố rủi ro kích hoạt: Áp lực bán ròng gia tăng, xuất hiện phiên phân phối thanh khoản đột biến hoặc giá đóng cửa xuyên thủng ngưỡng hỗ trợ 19,600 đ.
  - Vùng hỗ trợ/Cắt lỗ đề xuất: 19,600 đ (Cắt lỗ tại 19,000 đ [-3.6%])
- **Tỷ lệ Lợi nhuận/Rủi ro (R:R Ratio)**: 1:3.0

## 5. KẾT LUẬN HÀNH ĐỘNG
- **Trạng thái**: [Theo dõi]
- **Lưu ý cốt lõi**: Giá vẫn vận động dưới đường MA20 (20,630 đ); kiên nhẫn đứng ngoài quan sát cho đến khi xuất hiện nến đảo chiều xác nhận dòng tiền lớn hấp thụ trở lại.
```
