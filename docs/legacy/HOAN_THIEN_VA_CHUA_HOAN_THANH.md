> Archived original document. File paths, credentials policy and startup instructions may be obsolete. See README.md and docs/ARCHITECTURE.md.

# VIETSAFE 3 — BÁO CÁO SỬA LỖI VÀ CHỨC NĂNG CHƯA HOÀN THÀNH
Ngày: 10/10/2026

## Đã thực hiện trong bản bàn giao
1. Thêm module `openmeteo_weather.py` kết nối API dự báo mưa Open-Meteo, cache 15 phút, kiểm tra tọa độ, giới hạn 48 giờ và timeout. API `GET /api/weather/forecast?lat=21.0285&lng=105.8542&hours=24`. **Đây là dự báo mưa, không phải độ sâu ngập.**
2. Thêm bảng `flood_observations` và endpoint `GET /api/flood/observations` trả số đo điểm đã xác minh, còn hiệu lực 2 giờ; không tự ước lượng ngập cả tuyến.
3. Thêm `POST /api/flood/observations` chỉ dành cho quản trị viên đã đăng nhập. Payload: `{ "lat":21.0285, "lng":105.8542, "depth_cm":12, "observed_at":<Unix seconds>, "source":"Tram do X", "source_reference":"X-01" }`. Chỉ nhập số đo có nguồn và quyền thu thập; `verified` nghĩa là quản trị viên đã xác nhận đầu vào chứ không phải xác nhận độc lập độ chính xác cảm biến.
4. Giao diện bản đồ hiển thị điểm đo ngập thực khi có dữ liệu; cập nhật mỗi phút; thông tin dự báo mưa Hà Nội mỗi 15 phút. Khi chưa có dữ liệu, hiển thị 0 hoặc trạng thái lỗi, không tạo dữ liệu mẫu.
5. Tắt trả kết quả mô phỏng ở API `/api/snapshot` (HTTP 409) và `/api/routes` (HTTP 501). Điều này chủ ý vô hiệu hóa những tính năng cũ còn phụ thuộc mô phỏng; bản đồ nền, các lớp TomTom/NASA và phản ánh vẫn hoạt động riêng.
6. Không đưa `.env`, kho lưu trữ Git, dữ liệu SQLite cũ và thư mục `.venv` vào tệp ZIP bàn giao; `.env.example` không chứa khóa. Tài khoản quản trị mới chỉ khởi tạo khi có biến `VIETSAFE_ADMIN_PASSWORD` đủ dài.
7. Thêm kiểm thử regression `tests/test_live_data.py`.

## Cách chạy
```bash
cd VietSafe
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\\Scripts\\activate
python -m pip install -r requirements.txt
cp .env.example .env                 # Windows: copy .env.example .env
# Điền TOMTOM_API_KEY, NASA_EARTHDATA_TOKEN và VIETSAFE_ADMIN_PASSWORD
python3 server.py --host 127.0.0.1 --port 8765
```
Mở `http://127.0.0.1:8765`. Endpoint kiểm tra: `/api/health`, `/api/live-status`, `/api/weather/forecast`, `/api/flood/observations`, `/api/tomtom/segment?lat=21.0285&lng=105.8542`, `/api/gpm/rainfall`.

Kiểm thử tại thư mục VietSafe:
```bash
python -m unittest discover -s tests -p 'test_live_data.py' -v
```

## Chưa thể hoàn thành, lý do và yêu cầu
| Hạng mục | Tình trạng, nguyên nhân | Để hoàn thiện |
|---|---|---|
| TomTom giao thông thực tế | Có mã tích hợp cũ nhưng chưa xác thực được hoạt động bằng API key hợp lệ và quota thực tế | Chủ dự án kiểm thử với key có quyền sử dụng và phạm vi phủ sóng |
| NASA GPM | Có mã tải và phân tích HDF5, chưa chạy kiểm chứng mạng thực tế với Earthdata token | Cấp token, thử tải granule và đối chiếu timestamp |
| Số đo độ sâu ngập đường | Mới có nơi nhập/lưu/hiển thị, **chưa kết nối trạm đo thật** | Thiết bị, API từ cơ quan có thẩm quyền, hợp đồng chia sẻ dữ liệu hoặc dữ liệu lịch sử xác thực |
| Liên kết số đo điểm với toàn đoạn đường | Chưa thực hiện vì dễ tạo đánh giá sai | Mô hình thủy lực/hình học và kiểm chứng thực địa |
| Định tuyến an toàn | API demo bị chặn, chưa có engine routing thực | Mạng đường hoàn chỉnh, turn restrictions, ETA/closure, đánh giá độ an toàn |
| T-GCN, dự báo giao thông, MAE/RMSE/MAPE | Chưa có model huấn luyện, chưa có bộ dữ liệu độc lập | Thu thập dữ liệu hợp pháp và đánh giá ngoài mẫu |
| Camera/IoT, nhận diện ảnh, Gemini | Chưa có nguồn dữ liệu, thiết bị hoặc model được chấp thuận | Tích hợp API/thiết bị, quyền sử dụng, giám sát chất lượng |
| Cứu hộ/hotline | Danh sách cũ chưa xác minh số điện thoại, SLA và trạng thái 24/7 | Đối chiếu trực tiếp nhà cung cấp; bỏ tuyên bố thời gian nếu chưa được chứng minh |
| Triển khai public production | Chưa đủ hardening: SHA-256 mật khẩu cũ, token client-side, thiếu HTTPS/CSRF nâng cao/rate limits cho auth, host allowlist | Di trú password hashing Argon2/PBKDF2, xác thực & phân quyền, reverse proxy TLS, test security |
| E2E trình duyệt/bên thứ ba | Không có quyền truy cập Internet/API key thật trong môi trường kiểm thử | Chạy môi trường thật, kiểm tra JS/UI và giới hạn nhà cung cấp |

## Lưu ý bảo mật đặc biệt
- ZIP gốc có `.env` và `.env.example` chứa một chuỗi giống khóa TomTom thật. **Phải thu hồi / rotate khóa**, không tái sử dụng nó nếu đã đẩy Git.
- SQLite cũ nếu đã có tài khoản mật khẩu yếu không được cải thiện tự động. Không công khai server khi chưa kiểm tra và di trú tài khoản.
- Không coi bản đồ/lớp mưa là cảnh báo an toàn di chuyển đã được kiểm chứng.
- Điều kiện giấy phép và khả năng lưu trữ dữ liệu của TomTom, Open-Meteo, OSM và NASA phải được rà soát trước khi phát hành.
