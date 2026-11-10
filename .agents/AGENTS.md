# Project Agent Directives - Stock RT

- **Autonomous Execution**:
  - Always approve executing necessary scripts (including `python3`, `curl`, development server management) when working on `/Users/minhpvl/Desktop/stock_rt`.
  - Do not prompt the user for routine python3 verification or daemon execution inside this project.
- **Strict Scope Boundary**:
  - Keep all changes and command targets strictly within this repository.
  - Never execute commands or alter state outside of `/Users/minhpvl/Desktop/stock_rt`.
- **Strict Real-Time Data Sourcing (No Mock/Hardcoded UI Data)**:
  - Tuyệt đối không tạo hoặc gán cứng (hardcode) dữ liệu giả lập (mock data, fake numbers, static placeholders) để hiển thị lên giao diện UI.
  - Tuyệt đối không gán cứng chuỗi số liệu tài chính/tỷ lệ phần trăm trong file template HTML (như `(-5.5%)`, `(+7.5%)`, số giá cố định) — toàn bộ nhãn và số liệu phải là thẻ động (`<span>`, ID riêng) nhận dữ liệu từ JS/API.
  - Tuyệt đối không dùng công thức ngón tay cái tĩnh cố định (như `p * 0.945`, `p * 1.075`) trong cả logic client-side (đổi mã) và backend fallback. Mọi khuyến nghị Cắt lỗ, Mục tiêu chốt lời, Hỗ trợ S1/Kháng cự R1, R:R bắt buộc phải tính toán động từ nến kỹ thuật thực tế (Fractal Pivots, ATR14) hoặc theo đúng biên độ dao động từng sàn (HOSE: 7%, HNX: 10%, UPCoM: 15%).
  - Bắt buộc phải kết nối, truy vấn hoặc trace dữ liệu thực tế từ API và các nguồn trực tuyến uy tín (Entrade Realtime Engine, Bảng giá thị trường trực tuyến, Vietstock Finance, CafeF, VnExpress Kinh Doanh, Cổng TTĐT Chính Phủ/GSO, vnstock).
  - Nếu trường dữ liệu chưa có, rỗng hoặc nguồn gặp lỗi tạm thời, bắt buộc thông báo trung thực là `"Dữ liệu chưa ghi nhận"`, tuyệt đối không bịa đặt số liệu tài chính hoặc nhận định sai lệch.
- **Strict Pre-Edit Git Verification & Code Preservation**:
  - Khi được approved để sửa code hoặc chuẩn bị can thiệp file, bắt buộc phải kiểm tra `git status` và `git diff` / đọc nội dung file mới nhất trên đĩa trước khi ghi đè hoặc tạo bản vá.
  - Tuyệt đối không apply code dựa trên cache cũ làm mất đi những thay đổi hoặc code mới vừa được cập nhật trong working tree.
  - Sau khi chỉnh sửa, luôn kiểm tra lại diff (`git diff`) để đảm bảo các thay đổi mới nhất vẫn được bảo toàn nguyên vẹn.

