# VietSafe — Prototype Bản Đồ Mô Phỏng Ngập, Ùn Tắc Và Sự Cố Giao Thông

> **Đề tài dự thi Cuộc thi Dữ liệu vì Cuộc sống — Data for Life 2026**  
> _Prototype giao diện và quy trình phản ánh cộng đồng. Bản đồ, dự báo và tuyến đường dùng dữ liệu mô phỏng; không phải dịch vụ cảnh báo hoặc dẫn đường thực tế._

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-teal.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Web%20%7C%20Mobile%20Responsive-orange.svg)](<>)
[![Zero Dependency](https://img.shields.io/badge/Dependencies-Zero%20External%20Pip-green.svg)](<>)

---

## 📌 Bối cảnh vấn đề và định hướng giải pháp

- **Mục tiêu nghiên cứu**: Khảo sát cách kết hợp thông tin giao thông, tình trạng ngập và phản ánh cộng đồng để hỗ trợ nhận biết rủi ro.
- **Phạm vi prototype hiện tại**: Ứng dụng dựng tay mạng đường 36 đoạn/25 nút; sinh trạng thái mưa, tốc độ, độ sâu và chỉ số nguy cơ bằng kịch bản/quy tắc. Không kết nối dữ liệu khí tượng, cảm biến, camera, giao thông hay dữ liệu vệ tinh. Tuyến gợi ý chỉ để minh họa thuật toán, không phải tuyến an toàn.

---

## ✨ Các tính năng chính (Modules)

1. **Bản đồ trực quan tương tác (Interactive Map)**:
   - Giám sát 36 đoạn đường và 25 nút giao trọng điểm nội thành Hà Nội (mạng đường giản lược, dựng tay trong `core/network.py`).
   - Màu sắc thể hiện trạng thái trong kịch bản mô phỏng; phản ánh đã được quản trị viên xác minh được gắn nhãn riêng.
   - Chuyển mốc kịch bản: **Hiện tại**, **+30 phút**, **+60 phút**; snapshot mô phỏng được làm mới mỗi 10 giây, không có nghĩa là dữ liệu hiện trường được cập nhật.
   - Tìm địa điểm (không phân biệt dấu tiếng Việt), danh sách sự kiện có bộ lọc, banner cảnh báo khi có đoạn đường bị chặn.
2. **Dự báo rủi ro (Forecast Engine)**:
   - Biểu đồ theo quy tắc cho nguy cơ ngập (/100), rủi ro tổng hợp (/100) và tốc độ ước tính ở các mốc Hiện tại, +15, +30, +45, +60 phút.
   - Các con số là chỉ số mô phỏng, không phải đo đạc hiện trường hoặc xác suất đã hiệu chỉnh. Đoạn chưa đủ dữ liệu được ghi rõ.
3. **Định tuyến thông minh né điểm ngập (Smart Routing)**:
   - Thuật toán Dijkstra có phạt theo chỉ số rủi ro mô phỏng, tính riêng cho **xe máy** và **ô tô**, tại các mốc hiện tại / +30 / +60 phút.
   - Loại khỏi tuyến minh họa: đoạn được đánh dấu đóng trong kịch bản (ngập mô phỏng ≥ 30 cm hoặc phản ánh mức 3 đã xác minh), đoạn chưa đủ dữ liệu, và đoạn có nguy cơ ngập mô phỏng
     từ 82/100 (xe máy) hoặc 88/100 (ô tô).
   - Gợi ý tối đa 2 phương án: **Ưu tiên ít rủi ro mô phỏng** và **Ưu tiên thời gian ước tính**. Không dùng để dẫn đường.
4. **Phản ánh từ cộng đồng (Crowdsourcing)**:
   - Người dân (cần đăng nhập) gửi phản ánh ngập / ùn tắc / sự cố kèm định vị GPS hoặc ghim trên bản đồ, và ảnh hiện trường (JPG/PNG/WebP, ≤ 1,5 MB).
   - Chống lạm dụng: giới hạn 10 phản ánh/phút/IP, chặn gửi trùng trong 5 phút, kiểm tra chữ ký file ảnh, phản ánh tự hết hạn sau 2 giờ.
   - Phản ánh mới ở trạng thái **chờ xác minh** và chưa ảnh hưởng bản đồ hay định tuyến; chỉ phản ánh đã được admin xác minh mới có tác dụng.
5. **Ứng cứu khẩn cấp (Rescue)**:
   - Danh sách hiện có 6 mục giả định và 3 mục tham khảo chưa xác minh; chưa có dịch vụ được xác minh để gọi. Các liên hệ chỉ được kích hoạt sau khi xác minh độc lập.
   - Biểu mẫu chỉ dùng trình diễn ở trình duyệt, không gửi yêu cầu hay dữ liệu cá nhân đến backend. Không nhập thông tin thật khi dùng demo.
6. **Bàn làm việc Quản trị viên (Admin)**:
   - Kiểm duyệt phản ánh (_Chờ xác minh → Đã xác minh → Đã xử lý_, hoặc _Từ chối_).
   - Đổi kịch bản mưa mô phỏng: _Trời khô (0 mm/h)_, _Mưa lớn (28 mm/h)_, _Mưa rất lớn (55 mm/h)_.
   - Trang **Nguồn dữ liệu** (chỉ admin) và xuất dữ liệu: phản ánh dạng CSV, nhật ký dự báo dạng JSON.

---

## 🏛️ Kiến trúc hệ thống và mô hình dự báo

```
  Mạng đường dựng tay (25 nút, 36 đoạn) ─┐
  Kịch bản mưa + quy tắc mô phỏng ────────┼─> Snapshot mô phỏng
  Phản ánh do người dùng gửi ─────────────┘       │
      (pending không ảnh hưởng đường;             ├─> Bản đồ / biểu đồ minh họa
       verified được áp dụng riêng)               └─> Tuyến đường thử nghiệm

  Nghiên cứu AI tùy chọn: checkpoint cục bộ + dữ liệu lịch sử
  (tách biệt với bản đồ chính; không hiệu chỉnh Hà Nội/không cảnh báo công khai)
```

Không có nguồn quan trắc ngoài nào đang cấp dữ liệu cho bản đồ. Danh mục nguồn ở giao diện là kế hoạch tham khảo, không phải kết nối đã triển khai. Các phản ánh đã xác minh vẫn là báo cáo người dùng được kiểm tra thủ công, không thay thế cảm biến hay xác minh hiện trường độc lập.

Chi tiết luồng dữ liệu và quyết định thiết kế: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

Chạy đúng giao diện mới trên local/Render và xử lý lệnh chạy cũ:
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## 🚀 Hướng dẫn cài đặt và khởi chạy

### Chạy nhanh

Chỉ cần **Python 3.10+** — ứng dụng không phụ thuộc thư viện ngoài, không cần build.

| Hệ điều hành  | Cách chạy                                                                                                                             |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| Windows       | Bấm đúp [`scripts/start.cmd`](scripts/start.cmd)                                                                                      |
| macOS / Linux | `sh scripts/start.sh [cổng]` &nbsp;hoặc&nbsp; `cd backend && python3 -m vietsafe`                                                     |
| Docker        | `docker build -t vietsafe . && docker run -p 8765:8765 vietsafe` (xem lưu ý ở [DEVELOPMENT.md](docs/DEVELOPMENT.md#8-vấn-đề-đã-biết)) |

Mở **http://127.0.0.1:8765**. Chia sẻ cho người khác xem qua Internet: [`scripts/share-internet.cmd`](scripts/share-internet.cmd)
(Cloudflare Tunnel) hoặc deploy lên Render bằng [`render.yaml`](render.yaml) (xem lưu ý ở
[DEVELOPMENT.md](docs/DEVELOPMENT.md#8-vấn-đề-đã-biết)).

### Chia sẻ đường link Internet ra ngoài cho mọi người (Cloudflare Tunnel)

Để gửi link cho người khác hoặc Ban giám khảo xem thử trên điện thoại:

1. Nhấp đúp vào **`scripts/share-internet.cmd`** (Windows). Script cần `cloudflared.exe` đặt ở thư mục gốc dự án; nếu không có,
   script dùng phương án dự phòng `npx localtunnel` (cần Node.js). Nếu máy chủ chưa chạy, script tự khởi động.
2. Copy đường link HTTPS xuất hiện trên màn hình (dạng `https://xxxx.trycloudflare.com`) và gửi cho người dùng.

---

## 🔐 Tài khoản minh họa (Demo Accounts)

| Vai trò           | Tên đăng nhập | Mật khẩu       | Quyền hạn                                                                   |
| ----------------- | ------------- | -------------- | --------------------------------------------------------------------------- |
| **Quản trị viên** | `admin`       | `vietsafe2026` | Toàn quyền kiểm duyệt phản ánh, đổi kịch bản, xem tab Dữ liệu, xuất báo cáo |
| **Người dân**     | `nguoidan`    | `matkhau123`   | Gửi tin báo ngập/ùn tắc, định vị GPS, đính kèm ảnh                          |

> Đây là mật khẩu mặc định chỉ dùng để demo. Khi chia sẻ công khai, đặt `VIETSAFE_ADMIN_PASSWORD` và `VIETSAFE_CITIZEN_PASSWORD`
> **trước lần chạy đầu** (mật khẩu chỉ áp dụng lúc tạo DB). Người dân cũng có thể tự đăng ký tài khoản mới.

---

## 📁 Cấu trúc thư mục dự án

```
vietsafe/
├── backend/                 Máy chủ Python (chỉ dùng thư viện chuẩn)
│   ├── vietsafe/            Package chính
│   │   ├── core/            Logic nghiệp vụ thuần: mạng đường, mô phỏng, dự báo, định tuyến, tìm kiếm
│   │   ├── web/             Tầng HTTP
│   │   │   ├── controllers/ Các endpoint API, mỗi file một nhóm: system, auth, report, admin
│   │   │   ├── server.py    Handler HTTP: kiểm tra Host/Origin, header an ninh
│   │   │   ├── router.py    Bảng route, Request/Response, phân quyền
│   │   │   ├── ratelimit.py Giới hạn tốc độ theo IP
│   │   │   └── static.py    Phục vụ file tĩnh của frontend
│   │   ├── app.py           Khởi tạo ứng dụng
│   │   ├── auth.py          Tài khoản, phiên đăng nhập
│   │   ├── config.py        Mọi hằng số và biến môi trường
│   │   ├── db.py            SQLite + schema
│   │   ├── reports.py       Phản ánh cộng đồng
│   │   └── service.py       Ghép DB với core (snapshot, kịch bản, nhật ký dự báo)
│   └── tests/               Test backend (unittest)
├── frontend/                Giao diện web (HTML + CSS + ES modules)
│   ├── index.html           Khung của mọi trang và hộp thoại
│   ├── css/                 Các file CSS theo khu vực giao diện
│   ├── js/                  Module JavaScript (main.js là điểm vào; views/, data/)
│   ├── vendor/              Leaflet (đóng gói sẵn, chạy offline)
│   └── tests/               Smoke test giao diện (jsdom)
├── docs/                    Tài liệu kỹ thuật (.md) + tài liệu thuyết minh / hướng dẫn sử dụng (.docx)
├── scripts/                 Script chạy / chia sẻ (Windows .cmd/.ps1, macOS/Linux .sh)
├── data/                    SQLite sinh ra khi chạy (không commit)
└── Dockerfile, render.yaml, pyproject.toml, package.json, requirements.txt ...
```

---

## Tài liệu

| Muốn biết...                                                       | Đọc                                                                          |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| Kiến trúc tổng thể, luồng dữ liệu, các quyết định thiết kế         | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)                                 |
| Backend: module, API, cơ sở dữ liệu, cách thêm endpoint            | [docs/BACKEND.md](docs/BACKEND.md)                                           |
| Frontend: module, state, cách thêm trang / thành phần              | [docs/FRONTEND.md](docs/FRONTEND.md)                                         |
| Cài môi trường, chạy test, quy trình làm việc nhóm, vấn đề đã biết | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)                                   |
| Thuyết minh giải pháp                                              | [docs/VIETSAFE_MO_TA_GIAI_PHAP.docx](docs/VIETSAFE_MO_TA_GIAI_PHAP.docx)     |
| Hướng dẫn sử dụng                                                  | [docs/HUONG_DAN_SU_DUNG_VIETSAFE.docx](docs/HUONG_DAN_SU_DUNG_VIETSAFE.docx) |

---

## 🧪 Kiểm thử (Testing)

Dự án có bộ kiểm thử tự động cho cả backend và giao diện:

```bash
cd backend && python3 -m unittest discover -s tests -t .   # Backend unittest suite
npm install && npm run test:frontend                       # Frontend smoke tests (cần Node 20+)
```

Tình trạng hiện tại của các lệnh kiểm thử và công cụ format/lint: xem [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#8-vấn-đề-đã-biết).

---

## Tùy chọn AI nghiên cứu

Tùy chọn AI nghiên cứu: xem [cách chạy mô hình đã huấn luyện](docs/AI_FORECAST.md) và [kế hoạch tích hợp để review](docs/AI_INTEGRATION_PLAN.md). Trang Dự báo có lối vào mô hình Bellinge, FloodNet và SZ-Taxi. Đây là phát lại dữ liệu lịch sử; chưa hiệu chỉnh cho Hà Nội. Các checkpoint/dữ liệu cần được cung cấp cục bộ, không nằm trong repository.

## Mô phỏng xuất hiện ngập và độ sâu

Chạy `scripts/start-flood-simulator.cmd`, mở http://127.0.0.1:8791/flood-simulator.html.
Chỉnh mưa, độ sâu ban đầu và khả năng thoát nước để xem diễn biến 30/60 phút.
Đây là mô phỏng cân bằng nước với thông số giả định, chưa phải AI dự báo Hà Nội.
Không cần cài thư viện ngoài. Xem [hướng dẫn và dữ liệu cần để nối AI sau này](docs/FLOOD_SIMULATOR.md).

## 📄 Bản quyền và Tác giả

- Phát triển bởi Đội ngũ **VietSafe AI** cho cuộc thi **Data for Life 2026**.
- Mã nguồn phát hành theo giấy phép [MIT License](LICENSE).
