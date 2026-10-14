> Archived original document. File paths, credentials policy and startup instructions may be obsolete. See README.md and docs/ARCHITECTURE.md.

# Cấu hình NASA Earthdata cho VietSafe

## Đã bổ sung

- `NASA_EARTHDATA_TOKEN` và API key TomTom đã được cấu hình trong `.env`. **Theo yêu cầu chủ dự án, `.env` được Git theo dõi** (ưu tiên GitHub repository Private).
- `server.py` đã hỗ trợ đọc `.env` khi khởi động. `nasa_gpm.py` sử dụng biến môi trường này để xác thực truy cập GPM IMERG tại NASA GES DISC.
- API nội bộ: `GET /api/live-status` để kiểm tra trường `rainfall.configured` và `GET /api/gpm/rainfall` để đọc dữ liệu mưa NASA.
- Token hết hạn **13/12/2026 lúc 07:47:40 (giờ Việt Nam)** theo trường `exp` của JWT (chưa kiểm chứng chữ ký và quyền truy cập online).

## Chạy trên Mac hoặc Linux

```bash
cd VietSafe
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python kiem_tra_nasa.py
python server.py --port 8765
```

Truy cập: http://127.0.0.1:8765

## Kiểm tra dữ liệu thực

```bash
python kiem_tra_nasa.py --online
```

Lệnh này cần kết nối Internet và được cấp quyền truy cập GES DISC. `NASA_EARTHDATA_TOKEN` chỉ giúp xác thực; không đảm bảo NASA luôn có granule mới hay tài khoản được cấp quyền. Mở giao diện bản đồ để quan sát lớp mưa khi API lấy được dữ liệu.

## Triển khai Render / Docker

`.env` được Git theo dõi theo yêu cầu, nhưng `.dockerignore` vẫn loại `.env` khỏi image. Khi deploy Render, cần đặt `NASA_EARTHDATA_TOKEN` và `TOMTOM_API_KEY` bằng Environment Variables/Secrets tại dịch vụ; việc đẩy `.env` lên GitHub không tự cấu hình Render.

Với Docker:

```bash
docker build -t vietsafe-ai .
docker run --rm -p 8765:8765 --env-file .env vietsafe-ai
```

`.dockerignore` loại `.env` khỏi bản build Docker nhưng `--env-file` cung cấp token cho container lúc chạy. Chú ý file `.env` này còn chứa cấu hình bí mật khác, nên chỉ chạy trên máy tin cậy.

## Lưu ý nguồn dữ liệu

NASA GPM IMERG là **ước lượng cường độ mưa** (mm/giờ) theo ô lưới khoảng 0,1°, không phải đo độ sâu nước ngập tại từng con đường. Xem thời điểm đo (`time_start`/`time_end`) và trạng thái cache trước khi sử dụng để kết luận.

**Cảnh báo:** Nếu repository GitHub ở chế độ Public, cả NASA token và TomTom key sẽ bị công khai. Thao tác này có thể gây lạm dụng quota hoặc bị thu hồi khóa. Giữ repository Private, hoặc cân nhắc GitHub Secrets. `.env.local` cũng được Git theo dõi theo yêu cầu. Hiện chưa có mật khẩu quản trị được đặt; nếu nhập mật khẩu thực và push Public thì mật khẩu sẽ bị lộ.
