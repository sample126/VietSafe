> Archived original document. File paths, credentials policy and startup instructions may be obsolete. See README.md and docs/ARCHITECTURE.md.

# TomTom đã được cấu hình cho VietSafe 3

- Khóa TomTom đã được điền vào tệp `.env` ở thư mục gốc của dự án (không hiển thị lại khóa trong tài liệu này).
- `server.py` tự đọc `TOMTOM_API_KEY` trong `.env` khi khởi động; không cần đặt key trong `public/app.js`.
- `.env.example` được giữ dưới dạng mẫu; `.gitignore` cho phép Git theo dõi `.env`, `.env.local` và tệp cấu hình khác theo yêu cầu.

## Chạy trên macOS / Windows

1. Mở Terminal hoặc PowerShell tại thư mục dự án.
2. Nếu cần: `python3 -m pip install -r requirements.txt` (Windows: dùng `py -m pip install -r requirements.txt`).
3. Khởi động bằng `python3 server.py --port 8765` (Windows: `py server.py --port 8765`).
4. Truy cập `http://127.0.0.1:8765`.
5. Kiểm tra `http://127.0.0.1:8765/api/live-status`: thuộc tính `traffic.configured` phải là `true`.
6. Trong phần Bản đồ, bật lớp **Lưu lượng TomTom trực tiếp** trong menu lớp bản đồ; phóng đến vùng Hà Nội/Bắc Ninh. Nhấn một đoạn đường để lấy dữ liệu tốc độ.

Có thể chạy `python3 kiem_tra_tomtom.py` để kiểm tra `.env` có được đọc không, hoặc `python3 kiem_tra_tomtom.py --live` để gọi TomTom thật (cần Internet, khóa có quyền Traffic API và hạn mức).

**Lưu ý:** `traffic.configured = true` chỉ chứng minh có cấu hình, chưa chứng minh khóa còn hoạt động. Nếu bản đồ vẫn không có lớp giao thông, kiểm tra Internet, quyền API, quota và phản hồi mã lỗi của TomTom. Các nguồn NASA, cảm biến ngập và AI không tự có dữ liệu khi chỉ thêm khóa TomTom.

**Bảo mật:** Bản ZIP này chứa khóa thật trong `.env` theo yêu cầu của chủ dự án. Nếu đẩy `.env` lên GitHub Public, bạn đang công khai khóa và chấp nhận nguy cơ bị lạm dụng. Ưu tiên repository Private. Nếu khóa bị lộ, hãy thu hồi và tạo khóa mới trên TomTom Developer Portal. Nếu Terminal đã có biến môi trường `TOMTOM_API_KEY` khác (kể cả rỗng), biến môi trường đó được ưu tiên; cần bỏ biến cũ hoặc thay bằng khóa đúng, rồi khởi động lại máy chủ.
