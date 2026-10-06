# Đặc tả kỹ thuật (cho đội dựng backend/website)

Agent không cần đọc file này khi trả lời hằng ngày. Nội dung được tách khỏi SKILL.md để không làm loãng ngữ cảnh runtime.

## 1. JSON output (đồng bộ enum với SKILL.md)

```json
{
  "as_of": "YYYY-MM-DDTHH:MM:SS+07:00",
  "data_mode": "LIVE|USER_DATA|NO_DATA",
  "market": {
    "regime": "RISK_ON|NEUTRAL|DEFENSIVE|NO_NEW_RISK",
    "regime_checks_passed": 0,
    "flags": ["INDEX_BREADTH_DIVERGENCE", "TAIL_LOCK_RISK"]
  },
  "candidate": {
    "ticker": "ABC",
    "exchange": "HOSE|HNX|UPCOM",
    "sector": "...",
    "horizon": "T_PLUS|MEDIUM|LONG",
    "decision": "BUY_NOW|BUY_ON_BREAKOUT|BUY_ON_PULLBACK|WAIT|HOLD|ADD|TAKE_PARTIAL_PROFIT|TAKE_PROFIT|CUT_LOSS|EXIT|NO_TRADE",
    "position_state": "NONE|HOLDING_PROFIT|HOLDING_LOSS|OVERWEIGHT|UNDERWEIGHT",
    "execution_status": "OK|LIMITED|BLOCKED",
    "scores": { "opportunity": 0, "risk": 0, "data_confidence": 0 },
    "news": [{ "label": "POSITIVE|NEGATIVE|NEUTRAL", "verified": true, "summary": "..." }],
    "trade_plan": {
      "entry_low": 0, "entry_high": 0, "trigger": "...",
      "stop": 0, "target_1": 0, "target_2": 0, "reward_risk": 0,
      "risk_budget_pct_nav": 0, "position_pct_nav": 0,
      "valid_until": "YYYY-MM-DD"
    },
    "invalidation": "...",
    "top_reasons": [],
    "top_risks": [],
    "sources": []
  }
}
```

Không đưa markdown vào trường JSON nếu backend yêu cầu machine-readable.

Source object cho mỗi nguồn quan trọng: `title, publisher, published_at, source_type (OFFICIAL|FINANCIAL_DATA|MEDIA|SOCIAL), url, claim_supported, freshness_days`. Lưu nguồn đang chứng minh điều gì, không chỉ lưu URL.

## 2. Parameter registry

Giá trị trong SKILL.md là mặc định tham chiếu. Backend ghi đè bằng registry có version.

```yaml
parameter_version: "2026.10-lean"
regime:        { pass_risk_on: 4, pass_neutral: 3, pass_defensive: 2, factors: [1.0, 0.75, 0.5, 0.0] }
breadth_univ:  { top_adtv_count: 200 }
divergence:    { rolling_window: 5, min_trigger_sessions: 2, vni_gain_pct: 0.3, max_ad_ratio: 0.8, top_contrib_pct: 50 }
tail_lock:     { t_plus_action: "HARD_NO_TRADE", stress_sessions: 10, max_sector_cluster_pct: 15 }
fs_validity:   { q1_q3_self_reported: true, explanation_variance_pct: 10 }
data_conf:     { stale_price: -30, missing_fs: -15, tier34_only: -20, conflict: -15, no_volume: -15, unverified_news: -10, min_to_act: 65 }
gates:         { buy_opp: 70, buy_risk_max: 50, buy_dc: 80, wait_opp: 60, no_trade_risk: 70, chase_atr: 0.5 }
reward_risk:   { reject_below: 1.5, acceptable: 2.0, good: 2.5 }
risk_budget:   { t_plus: [0.25, 0.75], medium: [0.5, 1.0], long: [0.5, 1.5] }
stress:        { max_loss_pct_nav: 2.0 }
caps:          { single_name_pct: 15, sector_cluster_pct: 30, open_risk_pct: 4 }
liquidity:     { check_from_pct_adtv: 1, reduce_from_pct_adtv: 5, reject_above_pct_adtv: 10 }
profit:        { partial_1_r: 1.5, partial_2_r: 2.5, distribution_signals_to_act: 3 }
validity:      { t_plus_sessions: 3, medium_weeks: 2 }
```

Mọi ngưỡng ở trên là tham số tạm, chưa được backtest. Không đổi ngưỡng chỉ vì vài giao dịch gần nhất sai; mỗi thay đổi ghi: version, ngày, tham số đổi, lý do, kết quả backtest, hạn chế đã biết.

## 3. Backtest và calibration

- Test trên bull, bear, sideways, biến động cao, thanh khoản thấp, giai đoạn nhiều sự kiện; theo từng ngành và nhóm vốn hóa.
- Có in-sample, out-of-sample và walk-forward. Tránh overfit một giai đoạn.
- Chỉ số: expectancy, profit factor, average win/loss, max drawdown, win rate, thời gian nắm giữ, turnover, slippage thực tế, tỷ lệ false breakout, tỷ lệ chạm stop, chuỗi thua dài nhất.
- Chiến lược win rate cao nhưng EV âm → loại.
- Chỉ hiển thị "xác suất thắng" khi đã có nhãn lịch sử, calibration và Brier score (hoặc tương đương) trên out-of-sample. Nếu chưa, dùng "độ tin cậy tín hiệu".
- Kiểm tra riêng worst_gap: so mức lỗ thực tế trong 2 phiên đầu sau điểm mua với giả định stress.

## 4. Audit trail và vòng phản hồi

Mỗi khuyến nghị lưu: snapshot đầu vào, regime, ngành, điểm, nguồn tin, version tham số, entry/stop/target, action, timestamp, `valid_until`, kết quả sau đó.
Mỗi giao dịch đóng lưu thêm: exit, realized R, MFE, MAE, thời gian nắm giữ, lý do thoát, slippage, regime/ngành lúc vào. Sau mỗi chu kỳ đánh giá: loại tín hiệu nào có expectancy tốt, loại nào tạo false breakout, ngành/horizon nào có lợi thế.

## 5. Production checklist

```
[ ] Registry quy định thị trường + lịch giao dịch + lịch thanh toán T+2
[ ] Pipeline OHLCV EOD (và intraday nếu dùng), có timestamp, đánh dấu delayed/realtime
[ ] Thanh khoản (ADTV20 theo VND, free float), phân loại ngành
[ ] Breadth (% trên MA20/MA50, A/D, new high/low) để tính 5 điều kiện regime
[ ] BCTC, corporate actions, tin tức, cảnh báo pháp lý/quản trị
[ ] Calculator: kỹ thuật, flow, R/R, position sizing (gồm size_stress), portfolio risk
[ ] Backtest, walk-forward, out-of-sample
[ ] Log nguồn, timestamp, audit trail
[ ] Chế độ NO_DATA: chặn xuất mức giá và điểm số
```

## 6. Điều website không được làm

Hiển thị "chắc chắn tăng"; hiển thị win probability chưa calibration; dùng tin cũ như hiện tại; giấu timestamp; bỏ qua thanh khoản; giả định khớp stop chắc chắn; ép xuất mã mua mỗi ngày; đưa target tùy ý; dùng một điểm duy nhất thay cho phân tích.

## 7. Lưu ý pháp lý (cần tham vấn luật sư)

Khuyến nghị mua/bán cá nhân hoá kèm tỷ trọng vị thế có thể rơi vào hoạt động tư vấn đầu tư chứng khoán có điều kiện theo Luật Chứng khoán. Trước khi ra mắt website, xác định cách định vị nội dung (thông tin tham khảo/phân tích so với tư vấn cá nhân) và disclaimer phù hợp.
