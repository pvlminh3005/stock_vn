# Hướng Dẫn Deploy Lên Render, Cấu Hình MongoDB Atlas & Giữ Server Luôn Thức (Keep-Alive)

Tài liệu này hướng dẫn chi tiết quy trình triển khai hệ thống **Stock Pro Analytics** lên nền tảng đám mây Render, kết nối cơ sở dữ liệu MongoDB Atlas (Cloud) để đồng bộ danh mục sổ lệnh, và thiết lập Cron-job giữ ứng dụng chạy liên tục 24/7 nhằm đảm bảo bot Telegram quét realtime 15 phút/lần chuẩn xác.

---

## 1. Thiết Lập Cơ Sở Dữ Liệu MongoDB Atlas (Miễn Phí Vĩnh Viễn)

Hệ thống sử dụng MongoDB Atlas để lưu trữ sổ lệnh cá nhân, cấu hình Tổng NAV và lịch sử cảnh báo, cho phép bạn truy cập danh mục đồng nhất trên cả máy tính lẫn điện thoại di động.

### Bước 1.1: Tạo Cụm Database Miễn Phí (Cluster M0)
1. Đăng ký/Đăng nhập tại: [https://www.mongodb.com/cloud/atlas](https://www.mongodb.com/cloud/atlas).
2. Tạo một Cluster mới:
   * **Tier**: Chọn gói **M0 Free (Shared)** (512 MB lưu trữ miễn phí vĩnh viễn).
   * **Provider & Region**: Chọn **AWS** hoặc **Google Cloud**, chọn vùng gần Việt Nam (khuyên dùng **Singapore `ap-southeast-1`** để truy vấn nhanh nhất).
   * Đặt tên Cluster (ví dụ: `Cluster0` hoặc `StockCluster`) và bấm **Create Deployment**.

### Bước 1.2: Tạo Tài Khoản Truy Cập Database (Database User)
1. Vào mục **Security** $\rightarrow$ **Database Access** ở thanh menu bên trái.
2. Bấm **Add New Database User**.
3. Chọn phương thức xác thực **Password**:
   * Nhập **Username** (ví dụ: `stock_user`).
   * Nhập **Password** an toàn và lưu lại mật khẩu này.
   * Quyền hạn (**Database User Privileges**): Chọn `Read and write to any database`.
4. Bấm **Add User**.

### Bước 1.3: Cấp Quyền Truy Cập Mạng (Network Access)
> ⚠️ **Bắt buộc**: Render và các dịch vụ Cloud sử dụng dải IP động thay đổi liên tục, do đó cần mở quyền kết nối toàn cầu.
1. Vào mục **Security** $\rightarrow$ **Network Access**.
2. Bấm nút **Add IP Address**.
3. Bấm vào nút **ALLOW ACCESS FROM ANYWHERE** (hệ thống sẽ tự điền `0.0.0.0/0`).
4. Bấm **Confirm** và đợi khoảng 1 phút đến khi trạng thái chuyển sang màu xanh **Active**.

### Bước 1.4: Lấy Chuỗi Kết Nối (Connection String URI)
1. Quay lại trang **Database Deployments**, bấm nút **Connect** bên cạnh cụm Database của bạn.
2. Chọn phương thức **Drivers** (Driver: `Python`, Version: `3.12 or later`).
3. Sao chép chuỗi kết nối hiển thị trên màn hình:
   ```text
   mongodb+srv://<username>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
4. Thay thế `<username>` và `<password>` bằng tài khoản đã tạo ở Bước 1.2.  
   *(Lưu ý: Nếu mật khẩu có chứa ký tự đặc biệt như `@`, `#`, `%` thì cần URL-encode, ví dụ ký tự `@` chuyển thành `%40`).*

---

## 2. Hướng Dẫn Deploy Lên Render (Web Service)

### Bước 2.1: Tạo Web Service Trên Render
1. Đăng nhập vào [https://dashboard.render.com/](https://dashboard.render.com/).
2. Bấm nút **New +** ở góc trên cùng $\rightarrow$ Chọn **Web Service**.
3. Liên kết với kho mã nguồn GitHub của bạn và chọn repository dự án.
4. Thiết lập các thông số cơ bản:
   * **Name**: Đặt tên ứng dụng (ví dụ: `stock-pro-analytics`).
   * **Region**: Khuyên dùng `Singapore` (để cùng vùng mạng với MongoDB Atlas).
   * **Branch**: Nhánh Git chính của bạn (ví dụ: `main` hoặc nhánh feature đang triển khai).
   * **Runtime**: `Python 3`.
   * **Build Command**:
     ```bash
     pip install -r requirements.txt
     ```
   * **Start Command**:
     ```bash
     ./start.sh prod
     ```
     *(hoặc: `python3 backend/server.py --env prod`)*
   * **Instance Type**: Chọn gói `Free`.

### Bước 2.2: Khai Báo Biến Môi Trường (Environment Variables)
Tại trang thiết lập dịch vụ (hoặc trong mục **Environment** ở menu bên trái), bạn thêm các biến môi trường sau:

| Tên biến (Key) | Giá trị mẫu (Value) | Mô tả |
| :--- | :--- | :--- |
| `APP_ENV` | `production` | Định danh môi trường chạy Production (tự động nạp `envs/.env.production`) |
| `TELEGRAM_BOT_TOKEN` | `<bot_token_lay_tu_botfather>` | Token của Telegram Bot dùng để bắn cảnh báo |
| `TELEGRAM_CHAT_ID` | `<chat_id_cua_ban>` | ID tài khoản hoặc nhóm Telegram nhận thông báo |
| `APP_PUBLIC_URL` | `https://<ten-app-cua-ban>.onrender.com` | Đường dẫn public của trang web trên Render |
| `APP_ACCESS_PIN` | `<ma_pin_tu_chon>` | Mã PIN bảo mật truy cập ứng dụng (tùy chọn) |
| `MONGODB_URI` | `mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority` | Chuỗi kết nối MongoDB Atlas đã tạo ở Phần 1 |
| `MONGODB_DB_NAME` | `stock_pro_db` | Tên cơ sở dữ liệu lưu trữ trên MongoDB |
| `PORTFOLIO_RETENTION_DAYS` | `180` | Số ngày tự động dọn dẹp các lệnh đã bán (Mặc định 6 tháng) |
| `WHITELIST_HOSTS` | `minhpvl-stock-vn.onrender.com` | Host được miễn trừ kiểm tra mã PIN |

5. Bấm **Save Changes** hoặc **Create Web Service** để Render tự động build và triển khai.

---

## 3. Cấu Hình Cron-Job Giữ Server Luôn Thức (Keep-Alive 24/7)

### Vì Sao Cần Cấu Hình Này?
Gói **Render Free Tier** sẽ tự động đưa server vào trạng thái "ngủ" (Spin down) nếu không có yêu cầu HTTP nào gửi đến trong vòng **15 phút**.  
Khi server bị ngủ:
* Tiến trình quét chạy ngầm (`portfolio_scheduler`) sẽ tạm dừng.
* Bot Telegram sẽ **không thể gửi cảnh báo cắt lỗ/chốt lời 15 phút/lần** và sẽ bị lỡ **bản tin tổng hợp nến SuperTrend lúc 14:30**.

### Các Bước Cấu Hình Với Cron-job.org (Miễn Phí)
1. Truy cập và đăng ký tài khoản miễn phí tại: [https://cron-job.org](https://cron-job.org).
2. Vào mục **Cronjobs** $\rightarrow$ Bấm nút **Create cronjob**.
3. Điền các thông tin:
   * **Title**: `Keep Alive Stock RT`
   * **URL**: Đường dẫn Render của bạn kèm endpoint `/ping` (cực nhẹ < 40 bytes, tránh lỗi vượt dung lượng), ví dụ:
     ```text
     https://<ten-app-cua-ban>.onrender.com/ping
     ```
   * **Execution schedule**: Chọn `Custom` $\rightarrow$ Đặt biểu thức:
     ```text
     */10 8-15 * * 1-5
     ```
     *(Đảm bảo Timezone chọn `Asia/Ho_Chi_Minh` để chạy từ 08:00 sáng đến 15:50 chiều T2 - T6)*
   * **Request Method**: `GET` (hoặc `HEAD`)
4. Bấm **Create**.

> 💡 **Kết quả**: Cứ mỗi 10 phút, cron-job.org sẽ tự động ping vào trang web của bạn một lần, giúp server Render duy trì trạng thái hoạt động liên tục trong toàn bộ các phiên giao dịch từ Thứ 2 đến Thứ 6.

### Tùy Chọn Bổ Trợ: Tự Động Đánh Thức Qua GitHub Actions (`.github/workflows/wake_up_render.yml`)
Dự án đã tích hợp sẵn GitHub Actions workflow tự động chạy vào **08:50 sáng giờ Việt Nam** (trước giờ ATO 10 phút) vào các ngày Thứ 2 đến Thứ 6 để đánh thức Render thức dậy sẵn sàng:
- Sử dụng `curl -I` gửi request nhẹ tới endpoint `/ping`.
- Cơ chế retry 5 lần (khoảng cách 15s) đảm bảo máy chủ thức giấc 100% kể cả khi bị ngủ sâu.
- Bạn có thể kiểm tra hoặc kích hoạt thủ công trong tab **Actions** $\rightarrow$ **Wake up Render App** $\rightarrow$ **Run workflow**.

---

## 4. Kiểm Tra & Đồng Bộ Dữ Liệu Ban Đầu

### 4.1. Tự Động Đồng Bộ Dữ Liệu Cũ
* Hệ thống có sẵn cơ chế **Auto Sync**: Khi server khởi động và kết nối thành công tới MongoDB Atlas lần đầu tiên, nếu database trên cloud chưa có dữ liệu, toàn bộ dữ liệu danh mục cũ từ file SQLite local (`data/portfolio.db`) sẽ tự động được đồng bộ lên MongoDB Atlas.
* Bạn cũng có thể chủ động kích hoạt đồng bộ bất cứ lúc nào bằng lệnh:
  ```bash
  python3 backend/db/sync_to_mongo.py
  ```

### 4.2. Kiểm Tra Hoạt Động Của Telegram Alert
1. Bạn có thể mở trình duyệt và truy cập endpoint sau để kiểm tra bot Telegram có gửi tin nhắn thành công không:
   ```text
   https://<ten-app-cua-ban>.onrender.com/api/telegram/test?ticker=SSI
   ```
2. Nếu màn hình trả về `{"success": true}`, bot Telegram của bạn đã sẵn sàng nhận các cảnh báo thị trường và sổ lệnh tự động.

