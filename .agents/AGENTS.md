# Project Agent Directives - Stock RT

- **Autonomous Execution**:
  - Always approve executing necessary scripts (including `python3`, `curl`, development server management) when working on `/Users/minhpvl/Desktop/stock_rt`.
  - Do not prompt the user for routine python3 verification or daemon execution inside this project.
- **Strict Scope Boundary**:
  - Keep all changes and command targets strictly within this repository.
  - Never execute commands or alter state outside of `/Users/minhpvl/Desktop/stock_rt`.
- **Strict Real-Time Data Sourcing (No Mock/Hardcoded UI Data)**:
  - Tuyệt đối không tạo hoặc gán cứng (hardcode) dữ liệu giả lập (mock data, fake numbers, static placeholders) để hiển thị lên giao diện UI.
  - Bắt buộc phải kết nối, truy vấn hoặc trace dữ liệu thực tế từ API và các nguồn trực tuyến uy tín (SSI iBoard Pro, Vietstock Finance, CafeF, VnExpress Kinh Doanh, Cổng TTĐT Chính Phủ/GSO, vnstock).
  - Nếu trường dữ liệu chưa có, rỗng hoặc nguồn gặp lỗi tạm thời, bắt buộc thông báo trung thực là `"Dữ liệu chưa ghi nhận"`, tuyệt đối không bịa đặt số liệu tài chính hoặc nhận định sai lệch.

