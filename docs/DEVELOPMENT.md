# Hướng dẫn phát triển

Dành cho thành viên mới trong nhóm: cài môi trường, chạy, test, format và quy trình làm việc chung.

## 1. Yêu cầu

| Công cụ | Phiên bản            | Dùng để                                     | Bắt buộc?                          |
| ------- | -------------------- | ------------------------------------------- | ---------------------------------- |
| Python  | 3.10+                | Chạy backend và test backend                | Có                                 |
| Node.js | 20+ (khuyến nghị 22) | Smoke test giao diện, Prettier, ESLint      | Chỉ khi chạy test/format giao diện |
| ruff    | bản mới              | Format và lint backend (`pip install ruff`) | Không                              |
| Git     | bất kỳ               | Quản lý mã nguồn                            | Có                                 |

**Chạy ứng dụng không cần cài gì ngoài Python.** Node và `ruff` chỉ là công cụ phát triển. Test backend dùng `unittest` có sẵn trong Python.
Gói Node khai báo trong `package.json` (cài bằng `npm install`); `requirements.txt` chỉ ghi chú, không có gói Python nào bắt buộc.

## 2. Chạy ứng dụng

| Cách              | Lệnh                                                                                              |
| ----------------- | ------------------------------------------------------------------------------------------------- |
| Windows (bấm đúp) | `scripts\start.cmd` (gọi `start.ps1`, thêm `-Port 9000` để đổi cổng)                              |
| macOS / Linux     | `sh scripts/start.sh [cổng]`                                                                      |
| Trực tiếp         | `cd backend && python3 -m vietsafe [--port 9000] [--host 127.0.0.1]`                              |
| Docker            | `docker build -t vietsafe . && docker run -p 8765:8765 vietsafe` (xem [mục 8](#8-vấn-đề-đã-biết)) |

Mở http://127.0.0.1:8765. **Sửa frontend: chỉ cần tải lại trang** (file tĩnh được phục vụ trực tiếp, header `Cache-Control: no-cache`).
**Sửa backend: dừng (Ctrl+C) và chạy lại.** Muốn làm lại dữ liệu từ đầu: xóa `data/vietsafe.sqlite3`.

Biến môi trường (đổi mật khẩu demo, đường dẫn DB...): [BACKEND.md → Cấu hình](BACKEND.md#cấu-hình).

## 3. Các lệnh thường dùng

Dự án không có Makefile; chạy trực tiếp các lệnh sau từ thư mục gốc.

| Việc                               | Lệnh                                                                                       |
| ---------------------------------- | ------------------------------------------------------------------------------------------ |
| Test backend                       | `cd backend && python3 -m unittest discover -s tests -t .`                                 |
| Test giao diện                     | `npm run test:frontend` (cần `npm install` lần đầu)                                        |
| Format backend                     | `ruff format backend`                                                                      |
| Lint backend                       | `ruff check backend`                                                                       |
| Format giao diện                   | `npm run format` (Prettier: `frontend/js`, `frontend/css`, `frontend/tests`, `index.html`) |
| Kiểm tra format giao diện          | `npm run format:check`                                                                     |
| Lint giao diện                     | `npm run lint` (ESLint — xem [mục 8](#8-vấn-đề-đã-biết))                                   |
| Kiểm tra giao diện (format + lint) | `npm run check:js`                                                                         |

Cấu hình `ruff` nằm trong `pyproject.toml` (độ dài dòng 100, bộ luật `E F I B UP`).

## 4. Kiểm thử

Có ba lớp, chi tiết ở từng tài liệu:

1. **Backend** — 51 test `unittest` (logic lõi, dịch vụ, HTTP, phân quyền). → [BACKEND.md](BACKEND.md#kiểm-thử)
2. **Smoke test frontend** — nạp module thật trong jsdom + backend thật, 34 kiểm tra. → [FRONTEND.md](FRONTEND.md#7-kiểm-thử-frontend)
3. **Thủ công trên trình duyệt** — vẫn cần cho phần _trông thế nào_ (bố cục, màu, bản đồ thật). Sau mỗi thay đổi giao diện,
   mở app và thử: bản đồ, các tab, tìm tuyến, gửi phản ánh, đăng nhập admin → duyệt phản ánh, màn hình điện thoại.

**Quy tắc: thay đổi hành vi thì kèm test.** Sửa lỗi → viết test tái hiện lỗi trước rồi mới sửa.

Test không bao giờ đụng dữ liệu thật: backend dùng SQLite tạm (`tests/helpers.py`), smoke test đặt `VIETSAFE_DB` tạm.
Chưa có hệ thống CI tự động; hãy chạy các lệnh ở mục 3 trước khi mở Pull Request.

## 5. Quy trình làm việc nhóm

**Nhánh và commit**

- `main` luôn chạy được. Mỗi việc một nhánh ngắn: `feat/<mô-tả>`, `fix/<mô-tả>`, `docs/<mô-tả>`; mở Pull Request vào `main`.
- Commit nhỏ, thông điệp rõ việc đã làm (ví dụ `fix: tên đường gần nhất không hiện khi dùng GPS ở trang Ứng cứu`).
- **Tách commit định dạng khỏi commit logic** — nếu phải format lại file lớn, làm một PR/commit riêng chỉ chứa việc đó.

**Chia việc để ít xung đột**

| Khu vực                               | File thường sửa                                                                                             |
| ------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Một trang giao diện                   | `frontend/js/views/<trang>.js`, `frontend/css/<trang>.css`, một khối trong `index.html`                     |
| Endpoint mới                          | `backend/vietsafe/reports.py`/`service.py`, `web/controllers/<nhóm>_controller.py`, test, `docs/BACKEND.md` |
| Công thức dự báo / định tuyến         | `backend/vietsafe/core/*`, `tests/test_core.py`                                                             |
| Dữ liệu tĩnh (nguồn dữ liệu, hotline) | `frontend/js/data/*.js`                                                                                     |

**Checklist trước khi mở PR**

- [ ] Có test cho hành vi mới / lỗi đã sửa
- [ ] Đã chạy test backend và test giao diện (mục 3)
- [ ] Đã thử trên trình duyệt (hoặc điện thoại) nếu đụng giao diện
- [ ] Cập nhật tài liệu liên quan (`docs/`, bảng API...) nếu đổi hành vi, cấu trúc hoặc API
- [ ] Không commit `data/*.sqlite3`, mật khẩu, khóa API (đã có trong `.gitignore`)
- [ ] Không thêm thư viện ngoài vào backend khi chưa thống nhất trong nhóm (đang là "chỉ thư viện chuẩn")

**Khi review** chú ý: mọi chuỗi động trong `innerHTML` đã qua `esc()`; endpoint mới có khai báo quyền; logic đặt đúng lớp
(`core/` không import `web/`); controller mới đã được nạp trong `web/controllers/__init__.py`.

## 6. Triển khai

| Mục tiêu                 | Cách                                                                                                                                                    |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Demo trên máy            | `scripts\start.cmd` (Windows) / `sh scripts/start.sh` (macOS, Linux)                                                                                    |
| Chia sẻ tạm qua Internet | `scripts\share-internet.cmd` (Windows; cần `cloudflared.exe` ở thư mục gốc, nếu không có sẽ dùng `npx localtunnel`; tự khởi động máy chủ nếu chưa chạy) |
| Render                   | Kết nối repo, dùng `render.yaml`; **đặt** `VIETSAFE_ADMIN_PASSWORD` và `VIETSAFE_CITIZEN_PASSWORD` trong dashboard (xem [mục 8](#8-vấn-đề-đã-biết))     |
| Docker                   | `Dockerfile` ở gốc (Python 3.11-slim); chạy bằng user không phải root; gắn volume vào `/app/data` để giữ dữ liệu (xem [mục 8](#8-vấn-đề-đã-biết))       |

Bản đồ nền chạy được trên `localhost`; deploy lên tên miền thật có thể cần khóa Stadia Maps (`STADIA_API_KEY` trong `frontend/js/config.js`) —
nếu không, ứng dụng tự chuyển sang tile OpenStreetMap rồi sang sơ đồ ngoại tuyến.

Máy chủ mặc định lắng nghe ở `localhost` và chỉ nhận Host là `localhost`/`127.0.0.1` cùng cổng hoặc tên miền có hậu tố trong `ALLOWED_HOST_SUFFIXES`
(`config.py`). Khi chạy sau tunnel/hosting khác, thêm hậu tố tương ứng vào danh sách này.

## 7. Xử lý sự cố thường gặp

| Hiện tượng                                                 | Nguyên nhân / cách xử lý                                                                                                                              |
| ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Cổng 8765 đang bận`                                       | Có tiến trình khác dùng cổng: chạy với `--port 8766`. Thông báo này cũng hiện khi không bind được địa chỉ `--host`                                    |
| Banner "Mất kết nối" dù server đang chạy                   | Lỗi JS khi vẽ bị nuốt: mở Console (F12) xem dòng `refresh thất bại:`                                                                                  |
| Trang trắng, Console báo module / MIME                     | Mở file `index.html` trực tiếp bằng `file://`: phải truy cập qua `http://127.0.0.1:8765`                                                              |
| POST trả 403                                               | Thiếu header `X-VietSafe: local` hoặc `Origin` lạ (gọi bằng curl: thêm header; xem [BACKEND.md](BACKEND.md#ví-dụ))                                    |
| Truy cập từ máy khác trong mạng LAN không được / bị 403    | Cố ý: mặc định server chỉ nghe ở `localhost` và chỉ nhận Host là localhost/tunnel. Dùng `share-internet` hoặc thêm hậu tố vào `ALLOWED_HOST_SUFFIXES` |
| Đổi mật khẩu admin trong biến môi trường không có tác dụng | Chỉ áp dụng khi tạo DB lần đầu: xóa `data/vietsafe.sqlite3` rồi chạy lại                                                                              |
| `npm run test:frontend` báo không tìm thấy `python3`       | Đặt biến `PYTHON`, ví dụ `PYTHON=python npm run test:frontend`                                                                                        |
| Nền bản đồ trắng / lưới                                    | Stadia chặn (tên miền thật cần khóa) → tự chuyển OSM → ngoại tuyến; xem mục Triển khai                                                                |
