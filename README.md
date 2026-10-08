# VietSafe AI — Bản Đồ Cảnh Báo Ngập, Ùn Tắc Và Sự Cố Giao Thông Thời Gian Thực

> **Đề tài dự thi Cuộc thi Dữ liệu vì Cuộc sống — Data for Life 2026**  
> _Bản mẫu thực nghiệm giải pháp (Proof-of-Concept / MVP) hỗ trợ dự báo sớm 30–60 phút và gợi ý tuyến tránh rủi ro._

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-teal.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Web%20%7C%20Mobile%20Responsive-orange.svg)]()
[![Zero Dependency](https://img.shields.io/badge/Dependencies-Zero%20External%20Pip-green.svg)]()

---

## 📌 Bối cảnh vấn đề và định hướng giải pháp

- **Thực trạng**: Các ứng dụng bản đồ hiện nay (Google Maps, Apple Maps...) thường chỉ thông báo khi tuyến đường đã bị ngập hoặc tắc nghẽn (phản ứng sau sự việc). Người dân chuẩn bị ra đường lúc trời bắt đầu mưa không thể biết trước đoạn nào sẽ ngập sâu trong 30–60 phút tới để chủ động chọn lộ trình phù hợp.
- **Giải pháp VietSafe AI**: Nền tảng tổng hợp dữ liệu thời tiết (lượng mưa), độ trũng địa hình, lịch sử giao thông và phản ánh cộng đồng; ứng dụng mô hình dự báo không-thời gian để đưa ra cảnh báo sớm đón đầu trước 30–60 phút và điều hướng tìm tuyến tránh an toàn theo từng loại phương tiện (xe máy vs ô tô).

---

## ✨ Các tính năng chính (Modules)

1. **Bản đồ trực quan tương tác (Interactive Map)**:
   - Giám sát 36 đoạn đường và 25 nút giao trọng điểm nội thành Hà Nội (mạng đường giản lược, dựng tay trong `core/network.py`).
   - Phân cấp trực quan: Xanh (Thông thoáng), Cam (Ùn tắc), Xanh dương (Ngập nước), Đỏ (Sự cố nghiêm trọng / Chặn đường).
   - Chuyển nhanh thời điểm hiển thị: **Hiện tại**, **+30 phút**, **+60 phút**; dữ liệu tự làm mới mỗi 10 giây.
   - Tìm địa điểm (không phân biệt dấu tiếng Việt), danh sách sự kiện có bộ lọc, banner cảnh báo khi có đoạn đường bị chặn.
2. **Dự báo rủi ro (Forecast Engine)**:
   - Biểu đồ đường kép: chỉ số nguy cơ ngập (/100) và rủi ro tổng hợp (/100) tại các mốc Hiện tại, +15, +30, +45, +60 phút.
   - Bảng chi tiết theo từng đoạn đường (nguy cơ ngập, tốc độ ước tính, rủi ro tổng hợp). Đoạn chưa đủ dữ liệu hiển thị
     "Chưa đủ dữ liệu" thay vì số bịa.
3. **Định tuyến thông minh né điểm ngập (Smart Routing)**:
   - Thuật toán Dijkstra có phạt theo rủi ro dự báo, tính riêng cho **xe máy** và **ô tô**, tại thời điểm hiện tại / +30 / +60 phút.
   - Loại khỏi tuyến: đoạn bị chặn (ngập ≥ 30 cm hoặc phản ánh mức 3 đã xác minh), đoạn chưa đủ dữ liệu, và đoạn có nguy cơ ngập dự báo
     từ 82/100 (xe máy) hoặc 88/100 (ô tô).
   - Gợi ý tối đa 2 phương án: **Ưu tiên ít rủi ro** và **Ưu tiên thời gian** (chỉ hiện một nếu hai tuyến trùng nhau).
4. **Phản ánh từ cộng đồng (Crowdsourcing)**:
   - Người dân (cần đăng nhập) gửi phản ánh ngập / ùn tắc / sự cố kèm định vị GPS hoặc ghim trên bản đồ, và ảnh hiện trường (JPG/PNG/WebP, ≤ 1,5 MB).
   - Chống lạm dụng: giới hạn 10 phản ánh/phút/IP, chặn gửi trùng trong 5 phút, kiểm tra chữ ký file ảnh, phản ánh tự hết hạn sau 2 giờ.
   - Phản ánh mới ở trạng thái **chờ xác minh** và chưa ảnh hưởng bản đồ hay định tuyến; chỉ phản ánh đã được admin xác minh mới có tác dụng.
5. **Ứng cứu khẩn cấp (Rescue)**:
   - Trang tra hotline cứu hộ theo loại phương tiện và loại sự cố (chết máy do ngập, thủy kích, hỏng ắc quy...).
   - Hiện chạy hoàn toàn ở trình duyệt, chưa có API điều phối ở backend; số hotline là dữ liệu tĩnh cần xác minh trước khi công khai.
6. **Bàn làm việc Quản trị viên (Admin)**:
   - Kiểm duyệt phản ánh (_Chờ xác minh → Đã xác minh → Đã xử lý_, hoặc _Từ chối_).
   - Đổi kịch bản thời tiết tức thì: _Trời khô (0 mm/h)_, _Mưa lớn (28 mm/h)_, _Mưa rất lớn (55 mm/h)_.
   - Trang **Nguồn dữ liệu** (chỉ admin) và xuất dữ liệu: phản ánh dạng CSV, nhật ký dự báo dạng JSON.

---

## 🏛️ Kiến trúc hệ thống và mô hình dự báo

```
                          ┌─────────────────────────────────────────────────────────┐
                          │         Nguồn dữ liệu đa tầng và Viễn thám NASA         │
                          │ • Lượng mưa vệ tinh radar NASA GPM (IMERG 30 phút)      │
                          │ • Độ ẩm đất bão hòa NASA SMAP và Địa hình NASA SRTM DEM │
                          │ • Phản ánh cộng đồng (Ảnh hiện trường) + Trạm quan trắc │
                          │ • Mạng đường bộ (Đồ thị không gian OpenStreetMap)       │
                          └───────────────────────────┬─────────────────────────────┘
                                                      │
                                                      ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                           MÔ HÌNH DỰ BÁO 2 TẦNG                                 │
    │                                                                                 │
    │  [Tầng 1 - Bản thử nghiệm Web PoC / MVP]                                        │
    │  • Spatial-Rule Baseline (spatial-rule-demo-1.0):                               │
    │    Mô hình quy tắc không-thời gian giải thích được (Explainable AI),            │
    │    chạy nhẹ trên CPU không đòi hỏi GPU/Kafka.                                   │
    │                                                                                 │
    │  [Tầng 2 - Đề tài Nghiên cứu Khoa học Data for Life]                            │
    │  • T-GCN (Temporal Graph Convolutional Network) + Physics-Informed AI:          │
    │    GCN học tương quan không gian mạng đường + GRU học chuỗi thời gian,          │
    │    tích hợp đặc trưng viễn thám NASA GPM, SMAP và chỉ số trũng địa hình TWI.    │
    └─────────────────────────────────────────┬───────────────────────────────────────┘
                                              │
                                              ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                                GIAO DIỆN WEB                                    │
    │   • Bản đồ cảnh báo thời gian thực        • Điều hướng né ngập thông minh       │
    │   • Biểu đồ dự báo 30-60 phút             • Tiếp nhận và duyệt phản ánh         │
    └─────────────────────────────────────────────────────────────────────────────────┘
```

Chi tiết các lớp, luồng dữ liệu và quyết định thiết kế: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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
cd backend && python3 -m unittest discover -s tests -t .   # 51 test backend
npm install && npm run test:frontend                       # 34 kiểm tra giao diện (cần Node 20+)
```

Tình trạng hiện tại của các lệnh kiểm thử và công cụ format/lint: xem [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md#8-vấn-đề-đã-biết).

---

## 📄 Bản quyền và Tác giả

- Phát triển bởi Đội ngũ **VietSafe AI** cho cuộc thi **Data for Life 2026**.
- Mã nguồn phát hành theo giấy phép [MIT License](LICENSE).
