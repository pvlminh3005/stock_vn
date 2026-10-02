---
description: Tuyệt đối không tạo dữ liệu hardcode để view UI, bắt buộc phải trace từ API và nguồn trực tuyến thời gian thực
alwaysApply: true
---

# Quy Tắc Dữ Liệu Thời Gian Thực (No Hardcoded / Mock UI Data)

## 1. Nguyên Tắc Cốt Lõi
- **Cấm hoàn toàn dữ liệu giả / Hardcode**:
  - Tuyệt đối không tạo mock data, số liệu giả lập, chuỗi text gán cứng tùy tiện nhằm mục đích "làm đẹp" giao diện UI.
  - Mọi thông số giá, khối lượng, tỷ lệ mua/bán, chỉ số tài chính (P/E, P/B, ROE, EPS...), tin tức và khuyến nghị hiển thị trên UI **bắt buộc phải được trace trực tiếp từ API và các nguồn trực tuyến thực tế**.

## 2. Nguồn Dữ Liệu Trực Tuyến Được Phép Sử Dụng
- **Bảng điện & Dòng tiền**: SSI iBoard Pro API (`/stock/exchange/...`), Entrade / TradingView.
- **Báo cáo tài chính & Chỉ số cơ bản**: Vietstock Finance BCTC kiểm toán, Vnstock API (VCI, KBS), FiinGroup.
- **Tin tức & Sự kiện doanh nghiệp**: Cổng công bố thông tin HoSE/HNX, CafeF Doanh nghiệp, VnExpress Kinh Doanh.
- **Vĩ mô & Ngành**: Cổng TTĐT Chính Phủ (baochinhphu.vn), Tổng Cục Thống Kê (GSO.gov.vn), Ngân hàng Nhà nước (sbv.gov.vn).

## 3. Xử Lý Trường Hợp Thiếu Dữ Liệu
- Khi một API hoặc nguồn dữ liệu bị gián đoạn hoặc không có số liệu:
  - ❌ **KHÔNG ĐƯỢC PHÉP**: Tự gán các con số tượng trưng hoặc văn bản giả lập.
  - ✅ **BẮT BUỘC**: Hiển thị trung thực trạng thái `"Dữ liệu chưa ghi nhận"` hoặc `"Đang đồng bộ từ nguồn"`.
