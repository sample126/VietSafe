# VietSafe AI — Bản Đồ Cảnh Báo Ngập, Ùn Tắc & Sự Cố Giao Thông Thời Gian Thực

> **Đề tài dự thi Cuộc thi Dữ liệu vì Cuộc sống — Data for Life 2026**  
> *Bản mẫu thực nghiệm giải pháp (Proof-of-Concept / MVP) hỗ trợ dự báo sớm 30–60 phút và gợi ý tuyến tránh rủi ro.*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-teal.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Web%20%7C%20Mobile%20Responsive-orange.svg)]()
[![Zero Dependency](https://img.shields.io/badge/Dependencies-Zero%20External%20Pip-green.svg)]()

---

## 📌 Bối cảnh vấn đề & Định hướng giải pháp

* **Thực trạng**: Các ứng dụng bản đồ hiện nay (Google Maps, Apple Maps...) thường chỉ thông báo khi tuyến đường đã bị ngập hoặc tắc nghẽn (phản ứng sau sự việc). Người dân chuẩn bị ra đường lúc trời bắt đầu mưa không thể biết trước đoạn nào sẽ ngập sâu trong 30–60 phút tới để chủ động chọn lộ trình phù hợp.
* **Giải pháp VietSafe AI**: Nền tảng tổng hợp dữ liệu thời tiết (lượng mưa), độ trũng địa hình, lịch sử giao thông và phản ánh cộng đồng; ứng dụng mô hình dự báo không-thời gian để đưa ra cảnh báo sớm đón đầu trước 30–60 phút và điều hướng tìm tuyến tránh an toàn theo từng loại phương tiện (xe máy vs ô tô).

---

## ✨ Các tính năng chính (Modules)

1. **Bản đồ trực quan tương tác (Interactive Map)**:
   * Giám sát 36 đoạn đường và 25 nút giao trọng điểm nội thành Hà Nội.
   * Phân cấp trực quan: Xanh (Thông thoáng), Cam (Ùn tắc), Xanh dương (Ngập nước), Đỏ (Sự cố nghiêm trọng / Chặn đường).
   * Tua nhanh thời gian dự báo: **Hiện tại**, **+30 phút**, **+60 phút**.
2. **Dự báo rủi ro chuyên sâu (Forecast Engine)**:
   * Biểu đồ đường kép biến thiên chỉ số nguy cơ ngập (/100) và vận tốc lưu thông (km/h) theo các mốc thời gian (+15, +30, +45, +60 phút).
   * Bảng phân tích chi tiết mức độ rủi ro theo từng cung đường.
3. **Định tuyến thông minh né điểm ngập (Smart Routing)**:
   * Thuật toán Dijkstra trọng số rủi ro.
   * Tự động loại bỏ các đoạn đường ngập sâu (>30cm) hoặc bị phong tỏa.
   * Gợi ý 2 phương án lộ trình: **Tuyến ít rủi ro nhất** (an toàn) và **Tuyến nhanh nhất** (thời gian).
4. **Thu thập phản ánh từ cộng đồng (Crowdsourcing)**:
   * Người dân dễ dàng gửi phản ánh kèm định vị GPS, đặt ghim bản đồ và đính kèm ảnh hiện trường.
   * Bộ lọc chống tin nhắn rác và cơ chế kiểm duyệt đa tầng.
5. **Bàn làm việc Quản trị viên (Admin Review & Scenarios)**:
   * Dành riêng cho tài khoản quản trị: Kiểm duyệt tin báo (*Chờ duyệt → Xác minh → Đã xử lý*).
   * Đổi kịch bản thời tiết tức thì: *Trời khô*, *Mưa lớn (28 mm/h)*, *Mưa rất lớn (55 mm/h)*.
   * Xuất dữ liệu báo cáo dạng CSV và nhật ký dự báo dạng JSON.

---

## 🏛️ Kiến trúc hệ thống & Mô hình dự báo

```
                          ┌────────────────────────────────────────────────────────┐
                          │         Nguồn dữ liệu đa tầng & Viễn thám NASA          │
                          │ • Lượng mưa vệ tinh radar NASA GPM (IMERG 30 phút)     │
                          │ • Độ ẩm đất bão hòa NASA SMAP & Địa hình NASA SRTM DEM │
                          │ • Phản ánh cộng đồng (Ảnh hiện trường) + Trạm quan trắc│
                          │ • Mạng đường bộ (Đồ thị không gian OpenStreetMap)      │
                          └───────────────────────────┬────────────────────────────┘
                                                      │
                                                      ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                           MÔ HÌNH DỰ BÁO 2 TẦNG                                 │
    │                                                                                 │
    │  [Tầng 1 - Bản thử nghiệm Web PoC / MVP]                                        │
    │  • Spatial-Rule Baseline (spatial-rule-demo-1.0):                              │
    │    Mô hình quy tắc không-thời gian giải thích được (Explainable AI),            │
    │    chạy nhẹ trên CPU không đòi hỏi GPU/Kafka.                                   │
    │                                                                                 │
    │  [Tầng 2 - Đề tài Nghiên cứu Khoa học Data for Life]                           │
    │  • T-GCN (Temporal Graph Convolutional Network) + Physics-Informed AI:          │
    │    GCN học tương quan không gian mạng đường + GRU học chuỗi thời gian,          │
    │    tích hợp đặc trưng viễn thám NASA GPM, SMAP và chỉ số trũng địa hình TWI.    │
    └─────────────────────────────────────────┬───────────────────────────────────────┘
                                              │
                                              ▼
    ┌─────────────────────────────────────────────────────────────────────────────────┐
    │                                GIAO DIỆN WEB                                    │
    │   • Bản đồ cảnh báo thời gian thực        • Điều hướng né ngập thông minh       │
    │   • Biểu đồ dự báo 30-60 phút             • Tiếp nhận & duyệt phản ánh          │
    └─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Hướng dẫn cài đặt & Khởi chạy

### Cách 1: Chạy trực tiếp trên Windows (1-Click)
1. Clone hoặc tải mã nguồn về máy:
   ```bash
   git clone https://github.com/your-username/vietsafe-ai.git
   cd vietsafe-ai
   ```
2. Nhấp đúp vào file **`START-VIETSAFE.cmd`**.
3. Mở trình duyệt truy cập: **`http://127.0.0.1:8765`**.

### Cách 2: Chạy bằng lệnh Python (Đa nền tảng: Windows / Linux / macOS)
Yêu cầu Python 3.10 trở lên:
```bash
python server.py --port 8765
```

### Cách 3: Chia sẻ đường link Internet ra ngoài cho mọi người (Cloudflare Tunnel)
Để gửi link cho người khác hoặc Ban giám khảo xem thử trên điện thoại:
1. Nhấp đúp vào **`CHIA-SE-INTERNET.cmd`**.
2. Copy đường link HTTPS xuất hiện trên màn hình (dạng `https://xxxx.trycloudflare.com`) và gửi cho người dùng.

### Cách 4: Chạy bằng Docker
```bash
docker build -t vietsafe-ai .
docker run -p 8765:8765 vietsafe-ai
```

---

## 🔐 Tài khoản minh họa (Demo Accounts)

| Vai trò | Tên đăng nhập | Mật khẩu | Quyền hạn |
|---|---|---|---|
| **Quản trị viên** | `admin` | `vietsafe2026` | Toàn quyền kiểm duyệt phản ánh, đổi kịch bản, xem tab Dữ liệu, xuất báo cáo |
| **Người dân** | `nguoidan` | `matkhau123` | Gửi tin báo ngập/ùn tắc, định vị GPS, đính kèm ảnh |

---

## 📁 Cấu trúc thư mục dự án

```
vietsafe-web/
├── server.py              # HTTP Server, REST APIs, phân quyền & xác thực
├── engine.py              # Thuật toán dự báo quy tắc & định tuyến Dijkstra
├── network.py             # Dữ liệu 25 nút giao & 36 đoạn đường Hà Nội
├── public/                # Giao diện Frontend đơn trang (SPA)
│   ├── index.html         # Cấu trúc HTML giao diện & các dialog modal
│   ├── style.css          # Phong cách thiết kế hiện đại, responsive
│   ├── app.js             # Logic bản đồ, xác thực, API client & xử lý sự kiện
│   └── vendor/            # Thư viện Leaflet.js ngoại tuyến (không phụ thuộc CDN)
├── tests/                 # Bộ kiểm thử tự động (Unit tests & API tests)
│   ├── test_app.py
│   ├── test_http.py
│   └── test_auth.py       # 13 kịch bản kiểm thử bảo mật & phân quyền
├── docs/                  # Tài liệu hướng dẫn & thiết kế chi tiết
│   └── HUONG_DAN_SU_DUNG_VIETSAFE.docx
├── Dockerfile             # Cấu hình container đóng gói
├── render.yaml            # Cấu hình triển khai tự động lên Render.com
├── requirements.txt       # Thông tin thư viện
├── LICENSE                # Giấy phép nguồn mở MIT
└── README.md              # Tài liệu giới thiệu dự án
```

---

## 🧪 Kiểm thử (Testing)

Dự án tích hợp sẵn bộ kiểm thử tự động toàn diện:
```bash
python -m unittest discover tests
```

---

## 📄 Bản quyền & Tác giả

* Phát triển bởi Đội ngũ **VietSafe AI** cho cuộc thi **Data for Life 2026**.
* Mã nguồn phát hành theo giấy phép [MIT License](LICENSE).
