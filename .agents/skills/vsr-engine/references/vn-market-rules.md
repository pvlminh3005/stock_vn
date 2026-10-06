# Quy định và bối cảnh thị trường Việt Nam — registry có ngày

```
verified_at: 2026-10-06
quy_dinh_het_han: 30 ngày (hoặc ngay khi có thông báo thay đổi từ HOSE/HNX/VSDC/UBCKNN)
snapshot_het_han: 1 phiên giao dịch
```

Phần A là quy tắc tương đối bền. Phần B là ảnh chụp bối cảnh, chỉ để hiệu chỉnh kỳ vọng; mỗi lần chạy vẫn phải lấy lại giá, breadth, thanh khoản và dòng tiền.

## A. Quy tắc giao dịch

- **Thanh toán T+2:** Chứng khoán và tiền về tài khoản trước 13:00 ngày T+2 (VNDirect, Tier 2; VSDC có thông báo lịch thanh toán theo ngày nghỉ/làm bù: https://vsdc.vn/vi/ad/198931). Hàm ý: mua phiên T → bán sớm nhất chiều T+2; ngày nghỉ/làm bù làm dịch lịch, nên tính theo lịch giao dịch hiện hành. Không dùng "T+2.5" như hằng số. Thông tư 68/2024/TT-BTC (từ 02/11/2024) tháo gỡ pre-funding cho tổ chức nước ngoài, nhưng nhà đầu tư cá nhân trong nước vẫn ký quỹ 100% tiền/cổ phiếu và nhận chứng khoán chiều T+2.
- **Biên độ giá:** HOSE ±7%, HNX ±10% (tài liệu HOSE T2/2026; HNX cbtd.hnx.vn), UPCoM ±15% (VNDirect trích Thông tư 120/2020/TT-BTC, Tier 2). Ngày đầu đăng ký/niêm yết có biên độ riêng (UPCoM ±40%).
- **Mức lỗ xấu nhất khi chưa bán được cơ học** (kẹt sàn 2 phiên liên tiếp khi stop chưa có hiệu lực T+0, T+1), `1 − (1 − biên_độ)²`:

| Sàn | Biên độ | worst_gap |
|---|---|---|
| HOSE | 7% | 13.5% |
| HNX | 10% | 19.0% |
| UPCoM | 15% | 27.8% |

  Đây là mức stress cơ học, dùng để chặn size, không dùng làm stop hay làm proxy cho slippage.
- **Hố đen thanh khoản & Giải chấp chéo (Tail Lock Risk):** Cần phân biệt với kẹt sàn cơ học 2 phiên. Trong các cuộc khủng hoảng thanh khoản/trái phiếu hoặc giải chấp chéo ban lãnh đạo (bằng chứng lịch sử: NVL giảm sàn 18 phiên, PDR giảm sàn 17 phiên liên tiếp tháng 11/2022), chuỗi tắt thanh khoản trắng bên mua kéo dài 10–18 phiên khiến mức lỗ thực tế vượt 50–70%. Do đó: mã có áp lực trái phiếu đáo hạn/nợ ngắn hạn vượt tiền mặt + CFO, hoặc bị cắt margin hàng loạt, hoặc vướng khởi tố/thanh tra trọng yếu thì gắn cờ `TAIL_LOCK_RISK` $\rightarrow$ cấm T+ (`HARD_NO_TRADE`), Medium/Long chỉ được giải ngân với stress kẹt sàn ~10 phiên và hạ trần cụm ngành về $\le 15–20\%$ NAV.
- **Universe tính Độ rộng thị trường (Breadth Universe):** Toàn thị trường có khoảng 1.430 mã, nhưng ~59% số mã đứng giá/thanh khoản bằng 0 (chủ yếu tập trung ở UPCoM và HNX). Tính độ rộng trên toàn bộ 1.430 mã sẽ bị rác thanh khoản làm sai lệch. Bắt buộc đo độ rộng (% mã trên MA20) trên Universe **Top 150–200 mã có ADTV20 lớn nhất thị trường** (tương đương quy mô rổ VNAllshare + Top HNX).
- **Tính hợp lệ của BCTC theo Thông tư 96/2020/TT-BTC:** Quý I và III chấp nhận số liệu BCTC tự lập kèm đối chiếu văn bản giải trình biến động LNST (bắt buộc nộp khi LNST biến động $\ge 10\%$ yoy so với cùng kỳ); Quý II (Bán niên) yêu cầu BCTC soát xét; Cả năm yêu cầu BCTC kiểm toán. "Kỳ mới nhất hợp lệ" tính theo hạn công bố luật định (Quý: 30 ngày / 45 ngày hợp nhất; Bán niên: 45 ngày; Năm: 90 ngày). Chưa đến hạn luật định thì BCTC kỳ liền trước vẫn là hợp lệ, không bị trừ điểm Data Confidence.
- **Kẹt sàn/mất thanh khoản:** lệnh bán có thể không khớp. Ghi `execution_status = BLOCKED`, không giả định khớp ở giá stop.
- **Hạn chế giao dịch, cảnh báo, kiểm soát, đình chỉ, room ngoại, danh mục margin:** tra trên HOSE/HNX/CTCK cho từng mã dự kiến mua. Mã hạn chế giao dịch có cơ chế khớp riêng (không phải lúc nào cũng vào/ra được như mã thường).
- **KRX, non-prefunding, CCP, T+0, bán khống:** đang thay đổi nhanh. Chỉ áp dụng khi có văn bản Tier 1 xác nhận hiệu lực. Mặc định giả định T+2 và không bán khống.

## B. Snapshot bối cảnh (đến 2026-10-06)

### Vĩ mô — Cục Thống kê công bố 03/10/2026
(đối chiếu qua nhiều báo trích số liệu NSO; không tải trực tiếp được trang gốc)
- GDP quý III/2026 ước +9,95% yoy; 9 tháng +9,01% (quý I 8,15%, quý II 8,81% sau điều chỉnh). Công nghiệp–xây dựng 9 tháng +11,21%.
- CPI quý III/2026 +4,8% yoy. CPI bình quân 9 tháng 4,52% và lạm phát cơ bản 4,26%: lấy từ bản skill V5 cũ, chưa đối chiếu lại.
- Cơ cấu: nhập khẩu quý III tăng 28,75%, nhanh hơn xuất khẩu 23,27%; tăng trưởng nghiêng về đầu tư/nhập khẩu (Vietstock/Investing, Tier 2).
- Hàm ý: tăng trưởng mạnh đi cùng lạm phát cao hơn. Không quy ra "thị trường bull"; xét theo ngành và dữ liệu giá thực.

### Phân hạng FTSE Russell
- Hiệu lực 21/09/2026: Frontier → Secondary Emerging (UBCKNN). 27 mã vào rổ FTSE GEIS đợt đầu; lộ trình bốn đợt đến 09/2027, đợt đầu ~10% trọng số, các đợt sau vào 03/2027, 06/2027, 09/2027 (tỷ trọng từng đợt cần kiểm lại nguồn FTSE).
- Hàm ý: dòng thụ động giải ngân dần. Tách dòng thụ động khỏi dòng chủ động; không coi là tín hiệu mua ngắn hạn.

### Trạng thái thị trường đến 05/10/2026
- VN-Index 1.753,2 (05/10, +0,89%); đóng cửa tháng 9 ở 1.768,62; quý III −4,9%. Thanh khoản thấp (~434 triệu cp ngày 05/10).
- Khối ngoại bán ròng HOSE tháng 9 ≈ 4.830 tỷ đồng, phần lớn sau ngày nâng hạng (Elibook tổng hợp, Tier 3; cần kiểm lại với số liệu HOSE).
- Phân kỳ chỉ số–độ rộng: nhóm Vingroup đỡ chỉ số; một số phân tích ước tính chỉ số loại nhóm này thấp hơn đáng kể và mid/small-cap yếu hơn nhiều (Tier 3, chưa xác minh). Cần kiểm tra bằng breadth thật mỗi lần chạy, không dựa vào snapshot.
- Sự kiện sắp tới: BCTC quý III (dồn trong tháng 10); kỳ họp Quốc hội tháng 10 (Luật sửa đổi Luật Chứng khoán); đáo hạn phái sinh dự kiến 15/10/2026 (thứ Năm tuần thứ ba, kiểm tra lịch); các đợt cơ cấu ETF/FTSE.

### Cách dùng snapshot
- Dùng để biết cần kiểm tra gì (breadth, dòng ngoại, thanh khoản), không thay cho dữ liệu hiện tại.
- Nếu 5 điều kiện regime (SKILL.md, Bước 1) xác nhận trạng thái yếu và phân kỳ, hệ số risk budget tự giảm; mặc định ưu tiên WAIT/NO_TRADE, chỉ mở vị thế nhỏ ở mã ngành dẫn dắt có xác nhận.
