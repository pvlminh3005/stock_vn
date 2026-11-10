---
description: Tuyệt đối không tạo dữ liệu hardcode để view UI, bắt buộc phải trace từ API và nguồn trực tuyến thời gian thực
alwaysApply: true
---

# Quy Tắc Dữ Liệu Thời Gian Thực (No Hardcoded / Mock UI Data)

## 1. Nguyên Tắc Cốt Lõi
- **Cấm hoàn toàn dữ liệu giả / Hardcode**:
  - Tuyệt đối không tạo mock data, số liệu giả lập, chuỗi text gán cứng tùy tiện nhằm mục đích "làm đẹp" giao diện UI.
  - Tuyệt đối không gán cứng các chuỗi số liệu tài chính hoặc tỷ lệ % cố định trong mã HTML (ví dụ: `(-5.5%)`, `(+7.5%)`, giá mẫu tĩnh). Mọi nhãn tỷ lệ % và giá trị số phải là phần tử động nhận dữ liệu thực từ JS.
  - Tuyệt đối không sử dụng các công thức nhân tĩnh (heuristic) cố định như `p * 0.945` (-5.5%) hoặc `p * 1.075` (+7.5%) trong cả hàm đổi mã client-side và khối fallback backend.
  - Mọi thông số giá, khối lượng, tỷ lệ mua/bán, ngưỡng Cắt lỗ, Mục tiêu T+, Hỗ trợ S1 / Kháng cự R1, chỉ số tài chính (P/E, P/B, ROE, EPS...), tin tức và khuyến nghị hiển thị trên UI **bắt buộc phải được trace và tính toán động trực tiếp từ nến kỹ thuật thực tế (Fractal Pivots, ATR14), API và các nguồn trực tuyến thực tế**, hoặc biên độ dao động chính xác của từng sàn (HOSE: 7%, HNX: 10%, UPCoM: 15%).

## 2. Nguồn Dữ Liệu Trực Tuyến Được Phép Sử Dụng
- **Bảng điện & Dòng tiền**: SSI iBoard Pro API (`/stock/exchange/...`), Entrade / TradingView.
- **Báo cáo tài chính & Chỉ số cơ bản**: Vietstock Finance BCTC kiểm toán, Vnstock API (VCI, KBS), FiinGroup.
- **Tin tức & Sự kiện doanh nghiệp**: Cổng công bố thông tin HoSE/HNX, CafeF Doanh nghiệp, VnExpress Kinh Doanh.
- **Vĩ mô & Ngành**: Cổng TTĐT Chính Phủ (baochinhphu.vn), Tổng Cục Thống Kê (GSO.gov.vn), Ngân hàng Nhà nước (sbv.gov.vn).

## 3. Xử Lý Trường Hợp Thiếu Dữ Liệu
- Khi một API hoặc nguồn dữ liệu bị gián đoạn hoặc không có số liệu:
  - ❌ **KHÔNG ĐƯỢC PHÉP**: Tự gán các con số tượng trưng hoặc văn bản giả lập.
  - ✅ **BẮT BUỘC**: Hiển thị trung thực trạng thái `"Dữ liệu chưa ghi nhận"` hoặc `"Đang đồng bộ từ nguồn"`.
