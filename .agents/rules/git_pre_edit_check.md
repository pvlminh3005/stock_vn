---
description: Bắt buộc kiểm tra git status / diff mới nhất trước khi sửa code nhằm đảm bảo không ghi đè hay làm mất code vừa cập nhật
alwaysApply: true
---

# Quy Tắc Kiểm Tra Git Trước Khi Chỉnh Sửa Code (Safe Code Modification & Git Sync)

## 1. Nguyên Tắc Cốt Lõi
- Khi người dùng đồng ý/phê duyệt (approved) kế hoạch hoặc yêu cầu thực hiện sửa code, Agent **tuyệt đối không được apply code dựa trên nội dung cũ/stale cache**.
- Trước khi thực hiện bất kỳ thao tác ghi đè hoặc chỉnh sửa (`edit_file`, `write_file`, `apply_patch`), Agent **bắt buộc phải kiểm tra trạng thái Git thực tế** để bảo đảm an toàn dữ liệu, không ghi đè làm mất mã nguồn người dùng vừa cập nhật.

## 2. Quy Trình Bắt Buộc Trước Khi Chỉnh Sửa Code
1. **Kiểm tra Git Status**:
   - Chạy `git status` để kiểm tra danh sách các file đang có uncommitted changes (`modified`, `untracked`).
2. **Kiểm tra Git Diff & Đọc nội dung mới nhất từ đĩa**:
   - Với mỗi file chuẩn bị sửa, kiểm tra `git diff <file>` hoặc dùng `read_file` để đọc trực tiếp nội dung mới nhất từ file trên đĩa ngay tại thời điểm sửa.
   - Xác định chính xác các đoạn code, hàm, biến hoặc logic mà người dùng vừa mới cập nhật hoặc bổ sung.
3. **Bảo toàn thay đổi gần nhất (Preserve Recent Updates)**:
   - Khi áp dụng bản vá (`edit_file` / `apply_patch`), chỉ thay thế đúng phạm vi cần sửa.
   - **Tuyệt đối không xóa hoặc đảo ngược (revert) các dòng code mới vừa được cập nhật** trong working tree.
   - Nếu phát hiện xung đột (conflict) giữa code mới của người dùng và phương án sửa của Agent: dừng lại giải thích rõ ràng và xin ý kiến người dùng, hoặc tích hợp hòa hợp mà không làm mất tính đúng đắn của code người dùng.
4. **Hậu kiểm sau khi sửa (Post-edit Verification)**:
   - Ngay sau khi áp dụng thay đổi, chạy lại `git diff <file>` để tự review xem thay đổi có đúng mong đợi hay không, đảm bảo không có đoạn code mới nào bị ghi đè ngoài ý muốn.

