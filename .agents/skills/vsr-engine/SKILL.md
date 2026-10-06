---
name: vsr-engine
description: Phân tích và ra quyết định cổ phiếu Việt Nam (HOSE/HNX/UPCoM) theo hướng bảo toàn vốn, có entry/stop/target, R/R và quy mô vị thế. Dùng skill này bất cứ khi nào người dùng hỏi về một mã cổ phiếu VN, VN-Index, nhóm ngành, "nên mua/bán/giữ/chốt lời/cắt lỗ", danh mục đang nắm, quét cơ hội hằng ngày, hoặc muốn đặt điểm vào/ra và quản trị rủi ro, kể cả khi họ không nói "phân tích" hay "skill". Không dùng cho crypto, forex hay chứng khoán nước ngoài.
---

# VSR-Engine (bản gọn) — Ra quyết định cổ phiếu Việt Nam

Mục tiêu: kỳ vọng dương, drawdown thấp, bảo toàn vốn. `NO_TRADE` là đầu ra hợp lệ và thường là đầu ra tốt nhất. Đây là phân tích xác suất có điều kiện, không phải dự báo chắc chắn và không phải tư vấn đầu tư cá nhân hoá.

Tài liệu đi kèm:
- `references/vn-market-rules.md`: quy định giao dịch hiện hành và snapshot bối cảnh có ngày. **Đọc ở đầu mỗi lần chạy.**
- `references/engineering-spec.md`: JSON schema, backtest, audit trail. Chỉ đọc khi dựng backend/website, không cần cho trả lời hằng ngày.

## 1. Bốn nguyên tắc nền

1. **Không có edge → NO_TRADE.** Ép ra mã mỗi ngày là cách nhanh nhất để mất vốn.
2. **Điểm số không phải xác suất thắng.** Không viết "xác suất thắng X%" khi chưa calibration; dùng "độ tin cậy tín hiệu".
3. **Một chỉ báo không phải một luận điểm.** RSI thấp ≠ mua; ngoại bán ≠ bán; P/E thấp ≠ rẻ; volume lớn ≠ mua. Mọi tín hiệu volume phải đi cùng giá và vị trí trong cấu trúc.
4. **Thiếu dữ liệu thì nói thiếu.** Một con số chính xác từ dữ liệu cũ nguy hiểm hơn câu "chưa đủ dữ liệu".

## 2. Giao thức dữ liệu (làm trước mọi thứ)

Xác định chế độ dữ liệu và ghi một dòng ở đầu output:

| Chế độ | Khi nào | Được phép |
|---|---|---|
| `LIVE` | Có search/data tool, lấy được giá, KL, BCTC, tin kèm thời điểm | Toàn bộ quy trình |
| `USER_DATA` | Người dùng cung cấp số | Dùng đúng số đó, ghi "theo số bạn đưa lúc …" |
| `NO_DATA` | Không có tool và không có số | Chỉ nêu khung và kịch bản có điều kiện ("nếu đóng cửa trên X với KL ≥ …"). **Cấm** đưa mức giá entry/stop/target cụ thể và điểm số. Xin tối đa 1 dữ liệu cần nhất. |

Quy tắc dữ liệu:
- Mỗi số liệu quan trọng có nguồn + thời điểm. Giá cũ hơn phiên gần nhất → ghi "dữ liệu cũ", không dùng để đặt entry.
- Thứ bậc nguồn: Tier 1 (HOSE, HNX, VSDC, UBCKNN, NHNN, Cục Thống kê, công bố thông tin/BCTC của doanh nghiệp) > Tier 2 (FiinGroup, Vietstock, CafeF, báo cáo CTCK) > Tier 3 (báo chí) > Tier 4 (mạng xã hội, tin đồn; chỉ để điều tra, không làm căn cứ BUY/SELL).
- Hai nguồn mâu thuẫn: nguồn chính thức và mới hơn thắng. Chưa giải quyết được → `DATA_CONFLICT`, hạ DC.
- Tin chưa xác minh gắn `UNVERIFIED`, không làm căn cứ chính.
- "Không tìm thấy tin xấu" ≠ "không có rủi ro pháp lý". Chưa kiểm đủ nguồn → viết "pháp lý: chưa đủ dữ liệu".
- BCTC "kỳ mới nhất hợp lệ": căn cứ theo hạn công bố luật định. Quý I và III chấp nhận số tự lập nhưng bắt buộc đối chiếu văn bản giải trình biến động LNST (nếu chênh lệch ≥ 10% yoy theo Thông tư 96/2020/TT-BTC); Quý II yêu cầu soát xét; Năm yêu cầu kiểm toán. Chỉ trừ DC khi đã quá hạn luật định mà chưa có báo cáo.
- Quy định thị trường lấy từ `references/vn-market-rules.md`. Nếu `verified_at` quá 30 ngày hoặc nghi có thay đổi, tra lại nguồn Tier 1 trước khi dùng.

**Data Confidence (DC, 0–100):** bắt đầu 100, trừ: giá không phải phiên gần nhất −30; thiếu BCTC kỳ mới nhất hợp lệ −15; chỉ có nguồn Tier 3–4 −20; `DATA_CONFLICT` −15; thiếu KL/thanh khoản −15; tin trọng yếu chưa xác minh −10. **DC < 65 → chỉ WAIT hoặc NO_TRADE.**

## 3. Quy trình phân tích

### Bước 0 — Định tuyến và giả định
Nhận diện loại yêu cầu: (a) hỏi 1 mã, (b) đang giữ mã, (c) quét cơ hội, (d) danh mục, (e) thị trường chung. Cần biết: có đang giữ không (và giá vốn), khung thời gian, vốn/margin. Thiếu thì tự giả định (chưa sở hữu, khung phù hợp câu hỏi), nêu giả định một dòng, không hỏi dồn.

Horizon: **T+** = 2–10 phiên (thoát sớm nhất chiều T+2); **MEDIUM** = 2–12 tháng; **LONG** = 12–36 tháng. Một mã có thể là T+ WAIT / Medium BUY / Long HOLD, và đó là output hợp lệ.

### Bước 1 — Regime thị trường
Chấm 5 điều kiện, mỗi điều kiện đạt = 1 điểm:
1. VN-Index > MA50 và độ dốc MA20 ≥ 0
2. VN-Index > MA200
3. ≥ 50% số mã trên MA20 (tính trên Universe Top 150–200 mã có ADTV20 lớn nhất toàn thị trường để loại bỏ nhiễu từ các mã không thanh khoản)
4. Thanh khoản 5 phiên ≥ 90% trung bình 20 phiên
5. Không có phân kỳ chỉ số–độ rộng: cờ `INDEX_BREADTH_DIVERGENCE` kích hoạt nếu rolling 5 phiên có ≥ 2 phiên xuất hiện:
   - (a) ΔVN-Index > +0.3% và tỷ lệ Tăng/Giảm (A/D) < 0.8 trên rổ VN100; HOẶC
   - (b) Top 2–3 mã vốn hóa lớn đóng góp ≥ 50% tổng số điểm tăng của chỉ số ("kéo trụ xả hàng").

| Điểm | Regime | Hệ số risk budget |
|---|---|---|
| 5–4 | `RISK_ON` | 1.0 |
| 3 | `NEUTRAL` | 0.75 |
| 2 | `DEFENSIVE` | 0.5 |
| 0–1 | `NO_NEW_RISK` | 0 (không mở vị thế mới) |

Vĩ mô và dòng tiền ngoại/tự doanh chỉ là bối cảnh. GDP tăng mạnh không đồng nghĩa thị trường tăng.

### Bước 2 — Ngành
Xếp `LEADING / IMPROVING / NEUTRAL / WEAKENING / LAGGING` theo sức mạnh tương đối ngành so với VN-Index (20 phiên), % mã ngành trên MA20 và thanh khoản ngành. Ưu tiên LEADING/IMPROVING. Ngành yếu chỉ được xét khi có catalyst riêng từ nguồn Tier 1–2. Các mã cùng cụm tương quan (ví dụ SSI, HCM, VCI, MBS) là một cược, không phải bốn.

### Bước 3 — Cổng loại (hard filters)
Loại hoặc `NO_TRADE` nếu:
- đình chỉ; diện cảnh báo/kiểm soát/hạn chế giao dịch (với mua mới);
- thiếu BCTC trọng yếu; giá/KL bất thường không xác minh được;
- pháp lý mức 3 (mất khả năng thanh toán, gian lận trọng yếu, vấn đề kiểm toán trọng yếu); mức 2 (ảnh hưởng đáng kể đến lợi nhuận/vốn) → không mua mới;
- vị thế dự kiến / ADTV20 (theo VND) > 10%. Mức 1–5% cần kiểm tra, > 5% giảm size;
- **Cờ rủi ro hố đen thanh khoản (`TAIL_LOCK_RISK`):** xuất hiện khi doanh nghiệp có (a) Nợ vay ngắn hạn + Trái phiếu đáo hạn trong 12T vượt Tiền mặt + CFO (trừ Ngân hàng/Bảo hiểm), (b) Bị các CTCK lớn đồng loạt cắt margin, hoặc (c) Tranh chấp pháp lý/khởi tố lãnh đạo chưa rõ ràng. Mã có cờ này: **T+ → HARD_NO_TRADE**; Medium/Long chỉ được xét khi định giá chiết khấu sâu với kịch bản stress kẹt sàn ~10 phiên và trần cụm ngành bị bóp nghẹt.

Cổ phiếu tăng nóng + thanh khoản đột biến + free float thấp + tin đồn mạng xã hội → mặc định `AVOID` (nghi thao túng).

### Bước 4 — Chấm điểm
Ba điểm tách rời, thang 0–100. **Mọi trọng số là tham số tạm, chưa backtest.**

**Opportunity** (không chứa rủi ro): Technical 30 · Relative Strength 15 · Flow 15 · Fundamental 20 · Sector 10 · Catalyst 10.
- *Technical* = cấu trúc giá 40 + chất lượng breakout/retest 25 + volume trong ngữ cảnh 25 + momentum 10. RS không tính ở đây để tránh đếm đôi.
- *Flow* dựa trên 5 phiên cộng xác nhận từ giá: xác nhận 70–100, trung tính 40–69, phân phối 0–39. Một phiên đơn lẻ không đủ. Chuẩn hoá dòng ngoại theo ADTV, không dùng ngưỡng tuyệt đối chung như "−30 tỷ".
- *Fundamental* theo ngành (bên dưới). Valuation không cộng điểm; dùng làm cổng cho Medium/Long và luôn hỏi: rẻ vì thị trường định giá sai, hay vì lợi nhuận sắp giảm?

**Risk:** 5 nhóm × 0–20 (0 = an toàn, 20 = nguy hiểm): biến động (ATR%); thanh khoản/execution; gap và T+2 (mục 4); sự kiện/pháp lý/pha loãng; bối cảnh (regime, ngành, tập trung danh mục). Tổng ≥ 70 → `NO_TRADE`.

**Tin tức:** không chấm −100…+100. Gắn nhãn `POSITIVE/NEGATIVE/NEUTRAL` × `VERIFIED/UNVERIFIED` kèm một dòng tác động lên luận điểm. Ưu tiên theo độ mới: 24h > 3 ngày > 7 ngày > 30 ngày; tin cũ chỉ giữ nếu còn hiệu lực.

**Fundamental theo ngành:**
- Chung: tăng trưởng doanh thu/EPS, biên, ROE/ROIC, CFO/LNST, nợ ròng/EBITDA, phải thu và hàng tồn, giao dịch bên liên quan, pha loãng (ESOP, phát hành), chất lượng lợi nhuận (loại lãi bất thường từ thanh lý, hoàn nhập dự phòng, đầu tư tài chính).
- Ngân hàng: NIM, CASA, CIR, nợ xấu + nhóm 2, bao phủ nợ xấu, tăng trưởng tín dụng, an toàn vốn.
- Chứng khoán: dư nợ margin, thị phần môi giới, tự doanh (biến động mạnh), năng lực vốn.
- Bất động sản: pháp lý dự án, mở bán/bàn giao, tồn kho, dòng tiền, nợ và trái phiếu đáo hạn.

### Bước 5 — Reward/Risk
`Reward = Target − Entry hiệu dụng`; `Risk = Entry hiệu dụng − Stop`; đã trừ phí và thuế giao dịch. Stop dựa trên cấu trúc (swing low, hỗ trợ, MA20/50, ATR), không dựa trên biên độ sàn. Target phải có căn cứ (kháng cự, measured move, đỉnh cũ, định giá, earnings); không kéo target xa để làm đẹp R/R.
R/R < 1.5 loại · 1.5–2.0 thấp · ≥ 2.0 đạt · ≥ 2.5 tốt.

### Bước 6 — Cổng quyết định
Quyết định là lớp cuối, không phải phép cộng điểm.

| Action | Điều kiện (tất cả) |
|---|---|
| `BUY_NOW` | regime ≥ NEUTRAL · ngành không WEAKENING/LAGGING (hoặc có catalyst) · Opportunity ≥ 70 · Risk ≤ 50 · R/R ≥ 2.0 · DC ≥ 80 · setup đã xác nhận · giá ≤ entry_high + 0.5×ATR14 |
| `BUY_ON_BREAKOUT` / `BUY_ON_PULLBACK` | Như BUY_NOW nhưng trigger chưa xảy ra; phải nêu trigger giá, điều kiện KL và mức hủy |
| `WAIT` | Opportunity ≥ 60 nhưng thiếu một cổng (timing, R/R 1.5–2.0, DC 65–79, giá đã chạy quá xa → chờ retest) |
| `NO_TRADE` | Risk ≥ 70, hoặc R/R < 1.5, hoặc DC < 65, hoặc rớt cổng loại, hoặc regime `NO_NEW_RISK` |

Ví dụ: Opportunity 90, Risk 78, R/R 2.8 → `NO_TRADE`. Opportunity 80, Risk 24, R/R 3.1, DC 94, Bull, ngành dẫn dắt → `BUY_ON_BREAKOUT` hoặc `BUY_NOW` tùy trigger đã xảy ra chưa.

Xếp hạng ≠ BUY: xếp theo khả năng hành động × Opportunity × payoff đã trừ rủi ro. Mã hạng 1 vẫn có thể là WAIT.

Khi tín hiệu mâu thuẫn, ưu tiên theo thứ tự: pháp lý nghiêm trọng/ràng buộc thực thi → thanh khoản/khả năng thoát → rủi ro danh mục → regime → ngành → cấu trúc giá → cơ bản → dòng tiền → định giá/catalyst. Với LONG, cơ bản đứng trên cấu trúc giá.

## 4. Quy mô vị thế (risk-budget-first)

Risk budget mỗi lệnh (% NAV, trước hệ số regime): T+ 0.25–0.75 · Medium 0.5–1.0 · Long 0.5–1.5 (mỗi luận điểm). Giảm khi có sự kiện gần (BCTC, GDKHQ, đáo hạn phái sinh), biến động cao hoặc danh mục tương quan cao.

```
stop_eff    = max(khoảng cách tới stop cấu trúc, 2 × ATR14%)
size_risk   = risk_budget × hệ_số_regime / stop_eff
worst_gap   = 1 − (1 − biên_độ)²          # kẹt sàn 2 phiên liên tiếp khi chưa bán được (HOSE: 13.5%, HNX: 19%, UPCoM: 27.8%)
size_stress = 2% NAV / worst_gap
size        = min(size_risk, size_stress, trần_mã, trần_cụm_ngành, trần_thanh_khoản)
```

Lý do: hàng mới mua không bán được trước chiều T+2, nên stop chỉ có hiệu lực từ đó; trong 2 phiên đầu, mức lỗ xấu nhất bị chặn bởi biên độ chứ không phải bởi stop. Mã có cờ `TAIL_LOCK_RISK` thì cấm T+; nếu giữ Medium/Long thì `worst_gap` stress tính theo kẹt ~10 phiên: `1 - (1 - biên_độ)^10`.

Trần tham chiếu (tạm): 1 mã ≤ 15% NAV; 1 cụm ngành ≤ 30% NAV (khi cụm ngành có rủi ro thanh khoản hệ thống/giải chấp chéo như BĐS tháng 11/2022 thì giảm trần cụm xuống ≤ 15–20% NAV); tổng open risk ≤ 4% NAV. Làm tròn xuống lô 100 cp; nếu size sau làm tròn không còn ý nghĩa → `NO_TRADE`. Không đề xuất margin trừ khi người dùng nêu; nếu họ đang dùng margin và regime từ DEFENSIVE trở xuống, ưu tiên giảm đòn bẩy.

## 5. Vị thế đang có

Trạng thái: `NONE / HOLDING_PROFIT / HOLDING_LOSS / OVERWEIGHT / UNDERWEIGHT`. Cùng một mã có thể là WAIT với người chưa mua và HOLD với người đang giữ.

- **ADD:** chỉ khi vị thế đầu ≥ +1R, breakout xác nhận, stop đã nâng ≥ hòa vốn và danh mục còn room rủi ro. Không bình quân giá xuống.
- **Chốt lời:** +1.5R cân nhắc chốt 20–30%; +2.5R chốt thêm 25–35%; phần còn lại trailing theo swing low/MA20/ATR. Không chốt chỉ vì RSI > 70 hay ngoại bán. Đếm dấu hiệu phân phối: đóng cửa yếu, KL lớn ngày giảm, breakout thất bại, thủng hỗ trợ, RS xấu đi; ≥ 3/5 → `TAKE_PARTIAL_PROFIT` hoặc `EXIT`.
- **CUT_LOSS:** đóng cửa dưới mức invalidation, luận điểm kỹ thuật hỏng, hoặc rủi ro vượt budget. Không nới stop để né ghi nhận lỗ.
- **EXIT:** luận điểm cơ bản hỏng, pháp lý mức 3, hoặc rủi ro đổi nhanh. Nếu không bán được (kẹt sàn, mất thanh khoản): `decision = EXIT`, `execution_status = BLOCKED`. Không giả vờ đã thoát ở giá stop.

## 6. Chống FOMO và bắt đáy

Không nâng WAIT → BUY chỉ vì: giá tăng nhanh, mã lên top tăng giá, mạng xã hội bàn nhiều, tin chưa xác minh, hoặc người dùng muốn mua. Breakout đã chạy quá `entry_high + 0.5×ATR14` → WAIT chờ retest.

Chỉ xét bắt đáy khi lực bán yếu đi, cấu trúc tạo đáy, KL xác nhận, RS cải thiện và regime không phải `NO_NEW_RISK`. Giảm 10–20%, RSI < 30, P/E thấp hay chạm hỗ trợ cũ đều không đủ.

## 7. Định dạng output

Ngắn, quyết định ở đầu, không giải thích lại phương pháp. Giữ tên action bằng tiếng Anh, phần còn lại tiếng Việt.

**Mặc định (1 mã hoặc 1 vị thế):**
```
[MÃ] ([sàn]) — ACTION · HORIZON · [LIVE/USER_DATA] [nguồn, thời điểm] · DC xx
Vì sao (≤3 ý): …
Kế hoạch: Entry … | Trigger … | Invalidation/Stop … | T1 … T2 … | R/R …
Size: x% NAV (risk y% NAV) · Hiệu lực đến: [phiên/ngày]
Rủi ro chính (≤3): …
Kết luận: một câu.
```

Hiệu lực: T+ hết hạn sau 3 phiên, Medium sau 2 tuần, hoặc ngay khi chạm invalidation hay có tin trọng yếu.

**Quét thị trường / báo cáo ngày:** Regime + một dòng lý do (5 điều kiện) → ngành dẫn dắt/yếu → chỉ liệt kê mã đã qua cổng (0 mã là hợp lệ), tối đa 5 mã mỗi nhóm TOP T+ / MEDIUM / LONG, kèm WATCHLIST và AVOID ngắn. Mỗi mã dùng định dạng mặc định rút gọn.

Chỉ nêu Opportunity, Risk, DC; không dội toàn bộ điểm con. Kết bằng một dòng: "Thông tin tham khảo, không phải tư vấn đầu tư cá nhân; ngưỡng điểm là tham số tạm, chưa backtest."

JSON cho backend: xem `references/engineering-spec.md`.

## 8. Tự kiểm tra trước khi gửi

1. Giá/KL thuộc phiên nào, mốc giờ nào? Có số cũ nào đang bị dùng như hiện tại?
2. BCTC kỳ nào? Tin nào còn `UNVERIFIED`?
3. Target và stop có căn cứ cấu trúc? R/R đã trừ phí và thuế?
4. Size đã qua đủ ba lớp: risk budget, stress-gap, thanh khoản/danh mục?
5. Nêu được một lý do mạnh để luận điểm này sai?
6. Có đang tìm cớ để BUY vì người dùng muốn mua?

Câu nào không trả lời được → ghi thiếu, hạ DC, cân nhắc WAIT/NO_TRADE.
