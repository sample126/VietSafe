# Backend

Máy chủ Python 3.10+ chỉ dùng thư viện chuẩn. Package nằm ở `backend/vietsafe/`.
Bức tranh tổng thể và luồng dữ liệu: [ARCHITECTURE.md](ARCHITECTURE.md).

## Chạy

```bash
cd backend
python3 -m vietsafe                       # http://localhost:8765
python3 -m vietsafe --port 9000 --host 127.0.0.1
```

Lần chạy đầu tạo `data/vietsafe.sqlite3` (ở thư mục gốc repo) và 2 tài khoản demo. Mặc định máy chủ chỉ lắng nghe ở `localhost`.

## Cấu hình

Mọi hằng số nằm ở [`config.py`](../backend/vietsafe/config.py). Các giá trị có thể ghi đè bằng **biến môi trường**:

| Biến                        | Mặc định                       | Ý nghĩa                                                   |
| --------------------------- | ------------------------------ | --------------------------------------------------------- |
| `HOST`                      | `localhost`                    | Địa chỉ lắng nghe (có thể ghi đè bằng `--host`)           |
| `PORT`                      | `8765`                         | Cổng (có thể ghi đè bằng `--port`; Render đặt sẵn `PORT`) |
| `VIETSAFE_DB`               | `<repo>/data/vietsafe.sqlite3` | Đường dẫn file SQLite                                     |
| `VIETSAFE_FRONTEND_DIR`     | `<repo>/frontend`              | Thư mục file tĩnh                                         |
| `VIETSAFE_ADMIN_PASSWORD`   | `vietsafe2026`                 | Mật khẩu tài khoản `admin` **khi tạo DB lần đầu**         |
| `VIETSAFE_CITIZEN_PASSWORD` | `matkhau123`                   | Mật khẩu tài khoản `nguoidan` khi tạo DB lần đầu          |

> Mật khẩu chỉ được áp dụng lúc **tạo** tài khoản (`INSERT OR IGNORE`). Với DB đã tồn tại, xóa
> `data/vietsafe.sqlite3` rồi chạy lại, hoặc đổi trực tiếp trong bảng `users` (cột `password_hash` là SHA-256 của mật khẩu).

Hằng số khác trong `config.py` (không có biến môi trường):

| Hằng số                              | Giá trị                                                                           | Ý nghĩa                                                                      |
| ------------------------------------ | --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `SESSION_TTL_SECONDS`                | 24 giờ                                                                            | Hạn phiên đăng nhập                                                          |
| `REPORT_TTL_SECONDS`                 | 2 giờ                                                                             | Hạn phản ánh (quá hạn tự chuyển `expired`)                                   |
| `REPORT_DUPLICATE_WINDOW_SECONDS`    | 5 phút                                                                            | Cửa sổ chặn gửi trùng nội dung                                               |
| `REPORT_RATE_LIMIT_PER_MINUTE`       | 10                                                                                | Số phản ánh tối đa mỗi phút theo IP                                          |
| `REPORT_MAX_IMAGE_BYTES`             | 1.500.000                                                                         | Kích thước ảnh tối đa                                                        |
| `REPORT_MAX_DISTANCE_KM`             | 1                                                                                 | Vị trí phản ánh phải gần một đoạn đường trong mạng thử nghiệm                |
| `MAX_BODY_BYTES`                     | 2.200.000                                                                         | Kích thước body POST tối đa                                                  |
| `PILOT_LAT_RANGE`, `PILOT_LNG_RANGE` | `(20.98, 21.065)`, `(105.77, 105.88)`                                             | Vùng thử nghiệm — **phải khớp** `PILOT_BOUNDS` trong `frontend/js/config.js` |
| `ALLOWED_HOST_SUFFIXES`              | `.trycloudflare.com`, `.loca.lt`, `.ngrok.io`, `.ngrok-free.app`, `.onrender.com` | Hậu tố Host được phép ngoài localhost                                        |
| `PREDICTION_LOG_RETENTION_TICKS`     | 8640 (24 giờ)                                                                     | Thời gian giữ nhật ký dự báo (1 tick = 10 giây)                              |
| `PREDICTION_LOG_EXPORT_LIMIT`        | 500                                                                               | Số bản ghi tối đa khi xuất nhật ký dự báo                                    |

## Các module

| Module                                 | Trách nhiệm                   | Hàm / lớp chính                                                                                   |
| -------------------------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------- |
| `config.py`                            | Cấu hình tập trung            | `DB_PATH`, `FRONTEND_DIR`, các hằng số                                                            |
| `db.py`                                | Kết nối SQLite, schema        | `connect()` (context manager, tự commit), `init_schema()`                                         |
| `app.py`                               | Khởi tạo ứng dụng             | `init_app()`                                                                                      |
| `auth.py`                              | Tài khoản và phiên            | `login`, `register`, `create_session`, `get_user_by_session`, `delete_session`, `seed_demo_users` |
| `reports.py`                           | Phản ánh cộng đồng            | `create_report`, `review_report`, `get_reports`, `get_report_media`, `export_csv`                 |
| `service.py`                           | Ghép DB + core                | `current_snapshot`, `get_scenario`, `set_scenario`, `prediction_logs`                             |
| `core/network.py`                      | Mạng đường                    | `NODES`, `ROADS`, `ROAD_INDEX`, `nearest_road(lat, lng)`                                          |
| `core/simulation.py`                   | Dữ liệu giả lập               | `SCENARIOS`, `build_snapshot(scenario, reports, now)`                                             |
| `core/forecast.py`                     | Dự báo                        | `forecast(...)`, `MODEL_VERSION`                                                                  |
| `core/routing.py`                      | Định tuyến                    | `calculate_routes(snapshot, origin, destination, horizon, vehicle)`                               |
| `core/search.py`                       | Tìm kiếm                      | `search_places(query)`, `normalize(text)`                                                         |
| `web/router.py`                        | Bảng route                    | `Router`, `Request`, `Response`, `authorize`, `router`                                            |
| `web/controllers/__init__.py`          | Nạp controller, xuất `router` | `router`                                                                                          |
| `web/controllers/system_controller.py` | Endpoint hệ thống và bản đồ   | `health`, `snapshot`, `search`, `routes`                                                          |
| `web/controllers/auth_controller.py`   | Endpoint tài khoản            | `login`, `register`, `logout`, `me`                                                               |
| `web/controllers/report_controller.py` | Endpoint phản ánh             | `list_reports`, `create_report`, `review_report`, `report_media`, `report_limiter`                |
| `web/controllers/admin_controller.py`  | Endpoint quản trị             | `set_scenario`, `export_predictions`, `export_reports`                                            |
| `web/server.py`                        | HTTP handler                  | `Handler`, `create_server(host, port)`                                                            |
| `web/ratelimit.py`                     | Giới hạn tốc độ               | `SlidingWindowLimiter`                                                                            |
| `web/static.py`                        | File tĩnh                     | `read_static(url_path)`                                                                           |

## Tham chiếu API

Mọi phản hồi là JSON (trừ ảnh, CSV). Lỗi luôn có dạng `{"error": "thông báo tiếng Việt"}` (riêng lỗi Host sai ở GET trả thông báo tiếng Anh).
**Mọi POST** phải kèm header `X-VietSafe: local` và (nếu có) `Origin` cùng nguồn — client của frontend (`js/api.js`)
đã tự làm. Token đăng nhập gửi qua header `X-VietSafe-Session: <token>`.

| Phương thức và đường dẫn                                 | Quyền       | Mô tả                                                                                                        |
| -------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------------------------------------ |
| `GET /api/health`                                        | công khai   | `{ok, mode, model_version}`                                                                                  |
| `GET /api/snapshot`                                      | công khai   | Hiện trạng + dự báo toàn mạng (xem bên dưới)                                                                 |
| `GET /api/search?q=`                                     | công khai   | `{results:[{id,name,lat,lng,kind}]}` — tối đa 12 kết quả, không phân biệt dấu                                |
| `GET /api/routes?origin=&destination=&horizon=&vehicle=` | công khai   | Tuyến thay thế (xem bên dưới). `horizon` ∈ {0,30,60}; `vehicle` ∈ {`motorbike`,`car`}. 400 nếu sai           |
| `POST /api/auth/login`                                   | công khai   | `{username,password}` → `{user, token}`; 401 sai thông tin                                                   |
| `POST /api/auth/register`                                | công khai   | `{username(3-30),password(≥6),display_name(≤50)}` → `{user, token}` (vai trò `citizen`)                      |
| `POST /api/auth/logout`                                  | công khai   | Hủy phiên của token đang gửi → `{ok:true}`                                                                   |
| `GET /api/auth/me`                                       | công khai   | `{user: {username,display_name,role} \| null}`                                                               |
| `GET /api/reports`                                       | công khai ⚠ | `{reports:[...]}` — tối đa 500 phản ánh mới nhất (xem [giới hạn đã biết](ARCHITECTURE.md#5-mô-hình-an-ninh)) |
| `POST /api/reports`                                      | đăng nhập   | Gửi phản ánh → **201** `{id,status,road_id,duplicate}`; 429 nếu quá 10/phút                                  |
| `POST /api/reports/{id}`                                 | admin       | `{status: verified\|rejected\|resolved}` → `{id,status}`; 400 nếu chuyển trạng thái không hợp lệ             |
| `GET /api/report-media/{id}`                             | công khai ⚠ | Ảnh đính kèm (binary); 404 nếu không có                                                                      |
| `POST /api/scenario`                                     | admin       | `{scenario: normal\|rain\|storm}` → `{scenario}`                                                             |
| `GET /api/export/predictions`                            | admin       | Nhật ký dự báo (JSON, tải về `vietsafe-predictions.json`)                                                    |
| `GET /api/export/reports`                                | admin       | Danh sách phản ánh (CSV UTF-8 BOM, tải về `vietsafe-reports.csv`)                                            |

Body của `POST /api/reports`: `type` (`flood`\|`traffic`\|`incident`), `severity` (số nguyên 1–3), `lat`, `lng` (trong vùng thử nghiệm),
`description` (10–1.200 ký tự), `address` (≤ 200 ký tự, tùy chọn), `image` (data URL JPG/PNG/WebP ≤ 1,5 MB, tùy chọn).
Nếu cùng đoạn đường + loại + mô tả đã được gửi trong 5 phút và còn `pending`, trả về phản ánh cũ với `duplicate: true`.

Mã lỗi thường gặp: `400` dữ liệu sai · `401` cần đăng nhập · `403` thiếu quyền / sai Host / thiếu header POST ·
`404` không tồn tại · `413` body trống hoặc quá lớn · `429` gửi quá nhanh · `500` lỗi máy chủ (chi tiết ở console).

### Hình dạng của `/api/snapshot`

```jsonc
{
  "generated_at": 1759650000.1,     // Unix time
  "mode": "demo",
  "scenario": "rain",               // normal | rain | storm
  "rainfall": 28,                   // mm/h (mô phỏng)
  "temperature": 27,                // °C (mô phỏng)
  "model_version": "spatial-rule-demo-1.0",
  "roads": [ {                      // 36 phần tử
      "id": "HN-001", "name": "Cầu Giấy", "a": "caugiay", "b": "buoi",
      "coordinates": [[lat,lng],[lat,lng]], "length_km": 1.232,
      "susceptibility": 0.25, "free_speed": 35, "seed_event": "",   // tham số của bộ mô phỏng
      "known": true,                // false = chưa đủ dữ liệu (xem ghi chú bên dưới)
      "speed": 24.1, "depth": 0, "flood_risk": 12, "risk": 31, "severity": 1,
      "incident": false, "blocked": false, "event_type": null,      // flood | traffic | incident | null
      "origin": "demo",             // demo | local_report (do phản ánh đã xác minh)
      "report_id": null, "updated_at": 1759650000, "sources": ["..."], "evidence": ["..."],
      "forecast": [ {"horizon":0,"flood_risk":12,"speed":24.1,"risk":31,"label":"Thấp"}, /* 15,30,45,60 */ ]
  } ],
  "events": [ {"id","road_id","type":"flood|traffic|incident","severity","lat","lng","status","blocked", "..."} ],
  "nodes":  [ {"id":"caugiay","name":"…","lat":…,"lng":…} ],   // 25 nút giao
  "counts": {"flood":3,"traffic":3,"incident":1},              // chỉ đếm sự kiện đã xác minh
  "pending": 0,                     // số phản ánh đang chờ xác minh (còn hạn)
  "source_notice": "…", "forecast_notice": "…"                // nhãn trung thực hiển thị cho người dùng
}
```

Ghi chú: với đoạn `known: false`, `risk` và mọi giá trị trong `forecast[]` (`flood_risk`, `speed`, `risk`) là `null`, nhãn là
"Chưa đủ dữ liệu". Các trường `speed`, `depth`, `flood_risk` ở cấp đoạn đường vẫn mang số giả lập nhưng không được dùng để dự báo hay
định tuyến, và giao diện nên hiển thị là "chưa rõ".

### Hình dạng của `/api/routes`

```jsonc
{
  "routes": [ {                     // 0–2 phần tử; rỗng nếu không có đường thỏa điều kiện
      "id": "cautious",             // cautious (Ưu tiên ít rủi ro) | fast (Ưu tiên thời gian)
      "title": "Ưu tiên ít rủi ro",
      "road_ids": ["HN-003", "..."], "coordinates": [[lat,lng], "..."],
      "distance_km": 5.1, "eta_minutes": 14.2, "max_risk": 38,
      "steps": ["Kim Mã", "..."],   // tên các đoạn đường đi qua
      "warnings": ["..."]           // đoạn đi qua đang có sự kiện
  } ],
  "calculated_at": 1759650000.1,
  "excluded": 3,                    // số đoạn bị loại vì bị chặn hoặc chưa đủ dữ liệu
  "message": "…"
}
```

### Ví dụ

```bash
curl "http://127.0.0.1:8765/api/routes?origin=caugiay&destination=hoankiem&horizon=30&vehicle=car"

# Đăng nhập admin rồi đổi kịch bản
TOKEN=$(curl -s -X POST localhost:8765/api/auth/login -H 'X-VietSafe: local' \
        -H 'Content-Type: application/json' \
        -d '{"username":"admin","password":"vietsafe2026"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -X POST localhost:8765/api/scenario -H 'X-VietSafe: local' -H "X-VietSafe-Session: $TOKEN" \
     -H 'Content-Type: application/json' -d '{"scenario":"storm"}'
```

## Cơ sở dữ liệu (SQLite)

Schema ở [`db.py`](../backend/vietsafe/db.py), tạo tự động (`CREATE TABLE IF NOT EXISTS`, chế độ WAL).

| Bảng              | Nội dung                                                                                     |
| ----------------- | -------------------------------------------------------------------------------------------- |
| `settings`        | Khóa–giá trị; hiện chỉ có `scenario` (mặc định `rain`)                                       |
| `users`           | `username` (khóa), `password_hash`, `display_name`, `role` (`citizen`\|`admin`)              |
| `sessions`        | `token` (khóa), `username`, `created_at`, `expires_at`                                       |
| `reports`         | Phản ánh: loại, mức độ 1–3, tọa độ, mô tả, `status`, `expires_at`, ảnh (BLOB)                |
| `audit`           | Nhật ký thao tác trên phản ánh (`created`, `verified`, `rejected`, `resolved`)               |
| `prediction_logs` | Mỗi 10 giây một bản ghi dự báo (`tick`), giữ 24 giờ — để sau này đối chiếu với quan sát thật |

Xem dữ liệu: `sqlite3 data/vietsafe.sqlite3 "SELECT id,status,address FROM reports"` (cần cài công cụ dòng lệnh `sqlite3`), hoặc dùng
module `sqlite3` của Python.
Không có hệ thống migration; khi đổi schema cần thêm bước nâng cấp thủ công hoặc xóa DB demo.

## Cách thêm một endpoint

Ví dụ thêm `GET /api/stats` trả số phản ánh theo trạng thái (chỉ admin).

**1. Logic nghiệp vụ** — ở `reports.py` (không đụng HTTP):

```python
def count_by_status():
    with connect() as db:
        rows = db.execute("SELECT status, COUNT(*) AS n FROM reports GROUP BY status").fetchall()
    return {r["status"]: r["n"] for r in rows}
```

**2. Endpoint** — thêm vào controller phù hợp trong `web/controllers/` (ở đây là `admin_controller.py`), khai báo quyền ngay trên decorator:

```python
@router.get("/api/stats", auth="admin", deny="Chỉ quản trị viên mới xem được thống kê.")
def stats(req):
    return {"reports": reports.count_by_status()}
```

Chưa có controller phù hợp thì tạo `web/controllers/<tên>_controller.py` mới (đầu file: `from ... import <module nghiệp vụ>` và
`from ..router import router`), rồi **nạp nó trong `web/controllers/__init__.py`** (thêm vào dòng import và `__all__`). Bước này bắt buộc
vì decorator chỉ đăng ký route khi module được import.

Quy ước cho hàm endpoint `fn(req)`:

- `req.arg("name", default)` đọc query string; `req.body` là dict (POST); `req.params["id"]` cho đường dẫn `/x/{id}`;
  `req.user` là người đăng nhập hoặc `None`; `req.client_ip`.
- Trả về `dict` → HTTP 200 JSON. Cần mã khác / header / kiểu nội dung khác → trả `Response(body, status=…, headers=…, content_type=…)`.
- Báo lỗi người dùng bằng `raise ValueError("thông báo")` → tự thành HTTP 400 (GET chỉ bắt `ValueError`/`TypeError`; `KeyError` ở GET sẽ thành 500).
- Không viết `if user is None` thủ công — dùng `auth="user"` / `auth="admin"`.

**3. Test** — thêm vào `backend/tests/` (xem mục dưới) và **4.** thêm một dòng vào bảng API ở trên và bảng module.

## Thay dữ liệu mô phỏng bằng dữ liệu thật

Điểm cắm duy nhất là `core/simulation.build_snapshot(scenario, reports, now)`, được gọi từ
`service.current_snapshot()`. Hiện lượng mưa lấy từ `SCENARIOS[scenario]` và hiện trạng từng đoạn đường được sinh
từ `seed_event` + dao động theo thời gian. Hướng tiếp cận: tách phần "quan sát" (mưa, tốc độ, mực nước theo
`road_id`) thành một nguồn đọc từ DB / bộ thu thập nền, để `build_snapshot` nhận quan sát thật thay vì tự sinh,
giữ chế độ mô phỏng làm phương án dự phòng và cho kịch bản diễn tập của admin. Các điểm cần giữ nguyên:
hình dạng JSON của snapshot (frontend phụ thuộc), `known=false` khi thiếu dữ liệu, và quy tắc "chỉ phản ánh
`verified` mới ảnh hưởng". Tương tự, thay mô hình dự báo bằng cách thay hàm `core/forecast.forecast` (giữ nguyên chữ ký)
và tăng `MODEL_VERSION`.

## Kiểm thử

```bash
cd backend
python3 -m unittest discover -s tests -t .            # chạy tất cả (51 test)
python3 -m unittest tests.test_core -v                # một file
python3 -m unittest tests.test_http.HTTPTests.test_health   # một test
```

| File               | Phạm vi                                                           | Cần DB/HTTP? |
| ------------------ | ----------------------------------------------------------------- | ------------ |
| `test_core.py`     | định tuyến, dự báo, tìm kiếm, khoảng cách                         | không        |
| `test_router.py`   | khớp route, phân quyền, giới hạn tốc độ                           | không        |
| `test_services.py` | vòng đời phản ánh, validate, chống trùng, hết hạn, CSV, tài khoản | DB tạm       |
| `test_http.py`     | file tĩnh, header an ninh, Host/Origin/traversal, body sai, CSV   | server thật  |
| `test_auth_api.py` | phân quyền khách / người dân / admin qua API, rate limit          | server thật  |

`tests/helpers.py` cung cấp `DatabaseTestCase` (mỗi test một SQLite tạm, **không** đụng `data/`, và đặt lại `report_limiter`) và
`ServerTestCase` (thêm máy chủ HTTP trên cổng ngẫu nhiên, có `self.api(path, body, token)` và `self.login(...)`).
Test mới cần DB → kế thừa `DatabaseTestCase`; cần gọi API → kế thừa `ServerTestCase`.
