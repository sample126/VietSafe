# Frontend

Giao diện thuần **HTML + CSS + JavaScript ES modules** — không framework, không bước build. Trình duyệt nạp
trực tiếp file trong `frontend/`. Bản đồ dùng **Leaflet** (đóng gói sẵn ở `frontend/vendor/`, chạy offline).

Tổng quan toàn hệ thống: [ARCHITECTURE.md](ARCHITECTURE.md). Hướng dẫn thêm trang / thành phần ở [mục 6](#6-công-thức-thêm-tính-năng).

## 1. Cách trang được nạp

```
index.html
 ├─ <link> favicon.svg, vendor/leaflet.css, css/*.css (16 file, THEO THỨ TỰ)
 ├─ <script defer> vendor/leaflet.js     → tạo biến toàn cục `L`
 └─ <script type="module"> js/main.js    → nạp mọi module còn lại
```

`main.js` làm 3 việc theo thứ tự:

1. `initListeners()` — gọi các hàm `initXxx()` của từng module để **gắn sự kiện** (click, submit, change...).
2. `initializeMap()` — dựng bản đồ Leaflet.
3. `checkAuth()` + `refresh()` + `setInterval(refresh, 10s)` — khôi phục đăng nhập và bắt đầu vòng cập nhật dữ liệu.

## 2. Bản đồ các module (`frontend/js/`)

| File                                | Vai trò                                                                                                                                                                                     | Export chính                                                                                                                                                                       |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `main.js`                           | Điểm vào, khởi động                                                                                                                                                                         | —                                                                                                                                                                                  |
| `config.js`                         | Hằng số: nhãn loại sự kiện, chu kỳ cập nhật, vùng thử nghiệm, nhà cung cấp bản đồ, `ADMIN_VIEWS` (`sources`, `reports`), đoạn đường chọn mặc định (`HN-019`), khóa `localStorage` của token | `typeNames`, `statuses`, `REFRESH_INTERVAL_MS`, `PILOT_BOUNDS`, `HANOI_BOUNDS`, `ADMIN_VIEWS`, `DEFAULT_SELECTED_ROAD`, `TOKEN_STORAGE_KEY`, `STADIA_API_KEY`, `TILE_PROVIDERS`... |
| `state.js`                          | Trạng thái dùng chung                                                                                                                                                                       | `state` (dữ liệu, trang, bộ lọc, lớp hiển thị...), `authState` (người dùng + token, token đọc từ `localStorage`)                                                                   |
| `utils.js`                          | Tiện ích DOM/định dạng                                                                                                                                                                      | `$`, `$$`, `esc`, `icon`, `timeText`, `ago`, `toast`, `inPilotArea`                                                                                                                |
| `api.js`                            | Gọi API (gắn token, header an ninh, timeout 12s)                                                                                                                                            | `api(path)`, `post(path, body)`                                                                                                                                                    |
| `dashboard.js`                      | **Bộ điều phối** vòng cập nhật (gọi `/api/snapshot`, vẽ lại các thành phần, cập nhật trạng thái kết nối)                                                                                    | `refresh`, `updateDashboard`, `populateControls`                                                                                                                                   |
| `navigation.js`                     | Chuyển trang                                                                                                                                                                                | `setView(name)`                                                                                                                                                                    |
| `map.js`                            | Bản đồ Leaflet: nền, lớp, vẽ đường và marker                                                                                                                                                | `initializeMap`, `renderMap`, `setBaseTiles`, `roadColor`, `map`, `baseTiles`, `roadLayer`, `eventLayer`, `routeLayer`, `selectionLayer`, `placeLayer`                             |
| `map-controls.js`                   | Nút trên bản đồ: lớp hiển thị, nền, thu phóng, vị trí                                                                                                                                       | `initMapControls`                                                                                                                                                                  |
| `dialogs.js`                        | Hành vi chung của `<dialog>`                                                                                                                                                                | `initDialogs`                                                                                                                                                                      |
| `scenario.js`                       | Đổi kịch bản thời tiết (admin)                                                                                                                                                              | `changeScenario`                                                                                                                                                                   |
| `auth.js`                           | Đăng nhập / đăng ký / đăng xuất, ẩn hiện theo vai trò                                                                                                                                       | `checkAuth`, `updateAuthUI`, `doLogin`, `doRegister`, `doLogout`, `initAuth`                                                                                                       |
| `views/events-panel.js`             | Danh sách sự kiện + bộ lọc (bên phải bản đồ)                                                                                                                                                | `renderEvents`, `showEvent`                                                                                                                                                        |
| `views/insight.js`                  | Thẻ "Nhìn trước hành trình"                                                                                                                                                                 | `renderInsight`                                                                                                                                                                    |
| `views/road-details.js`             | Chọn đoạn đường, hộp chi tiết                                                                                                                                                               | `selectRoad`, `showRoadDetails`                                                                                                                                                    |
| `views/search.js`                   | Tìm địa điểm                                                                                                                                                                                | `searchLocation`                                                                                                                                                                   |
| `views/routing.js`                  | Tìm tuyến thay thế                                                                                                                                                                          | `openRoute`, `findRoutes`, `renderRoutes`, `clearRoutes`                                                                                                                           |
| `views/forecast.js`                 | Trang Dự báo (chọn đoạn đường, đổi kịch bản)                                                                                                                                                | `renderForecast`, `initForecast`                                                                                                                                                   |
| `views/sources.js`                  | Trang Nguồn dữ liệu (**chỉ admin**)                                                                                                                                                         | `renderSources`, `initSources`                                                                                                                                                     |
| `views/reports.js`                  | Trang Phản ánh (**chỉ admin**): duyệt                                                                                                                                                       | `loadReports`, `renderReports`, `initReports`                                                                                                                                      |
| `views/report-form.js`              | Hộp thoại gửi phản ánh, GPS, chọn điểm trên bản đồ                                                                                                                                          | `openReport`, `submitReport`, `geolocate`...                                                                                                                                       |
| `views/rescue.js`                   | Trang Ứng cứu (chỉ chạy ở trình duyệt, chưa có API backend)                                                                                                                                 | `initRescue`                                                                                                                                                                       |
| `views/alert-banner.js`             | Banner cảnh báo đường bị chặn                                                                                                                                                               | `updateAlertBanner`, `initAlertBanner`                                                                                                                                             |
| `data/sources.js`, `data/rescue.js` | **Dữ liệu tĩnh** tách khỏi logic                                                                                                                                                            | `DATA_SOURCES`, `rescueServices`                                                                                                                                                   |

Các `*.js` đứng ngoài `views/` là hạ tầng dùng chung; mỗi file trong `views/` là **một khu vực giao diện**.

## 3. Mô hình hoạt động

```
setInterval(refresh, 10s) ──► api("/api/snapshot") ──► state.data = …
                                                       ├► updateDashboard()
                                                       │    ├─ renderMap()
                                                       │    ├─ renderEvents()
                                                       │    ├─ renderInsight()
                                                       │    └─ renderForecast()  (nếu đang ở trang đó)
                                                       ├► updateAlertBanner()
                                                       └► loadReports()          (nếu đang ở trang Phản ánh)
```

- **`state`** là một object duy nhất; các module đọc/ghi thuộc tính trực tiếp (`state.filter = "flood"`).
- Mô hình **không tự phản ứng (không reactive)**: sau khi đổi `state`, bạn phải **tự gọi hàm `renderXxx()`**
  tương ứng. Mỗi hàm render đọc `state` rồi **vẽ lại cả vùng của nó** bằng `innerHTML` — đơn giản và đủ nhanh với dữ liệu này.
- Lần `refresh()` đầu tiên còn gọi `populateControls()` (điền danh sách nút giao và đoạn đường, vẽ nhãn địa danh, dựng trang Nguồn dữ liệu).
- Mỗi module có `initXxx()` để gắn sự kiện; các `initXxx()` được gọi một lần trong `main.js`. Không gắn sự kiện ở top-level
  module (tránh lỗi thứ tự nạp khi các module import vòng tròn nhau).
- **Nút sinh động (tạo bằng `innerHTML`) dùng `data-*` + một trình xử lý click ủy quyền** trên `document`
  (ví dụ `<button data-focus-road="HN-019">`, xem `views/road-details.js`) vì nút chưa tồn tại lúc gắn sự kiện.
  Nút có sẵn trong `index.html` thì gắn trực tiếp `$("#id").addEventListener(...)`.

### Biến Leaflet dùng chung

`map.js` khai báo `export let map, roadLayer, routeLayer, selectionLayer, placeLayer...` và **gán** chúng trong `initializeMap()`.
Module khác chỉ **đọc** (`import { map } from "../map.js"`) — ES module cho phép đọc giá trị mới nhất. **Không** gán lại từ module khác.

### Import vòng tròn

Có các import vòng (ví dụ `road-details.js` ↔ `forecast.js`). Chấp nhận được vì các module chỉ **định nghĩa hàm**
ở top-level và hàm chỉ được gọi sau khi mọi module đã nạp xong. Quy tắc để không gãy: **đừng chạy code phụ thuộc
module khác ngay ở top-level** — đặt vào hàm `initXxx()` hoặc trong thân hàm.

## 4. Quy ước và những điều dễ vấp

1. **Luôn `esc()` mọi dữ liệu động** chèn vào `innerHTML` (tên đường, mô tả phản ánh, thông báo lỗi...). Quên một chỗ là có lỗ hổng XSS.
2. **Không dùng `onclick="..."` hay `<script>` nội tuyến** — CSP `script-src 'self'` sẽ chặn. Gắn sự kiện trong JS.
3. **Gọi API bằng `api()` / `post()`**, đừng `fetch` trần — hai hàm này gắn token phiên, header `X-VietSafe` (không có sẽ bị 403 với POST) và timeout.
4. **Lỗi khi vẽ cũng hiện thành "Mất kết nối".** `refresh()` bọc cả bước vẽ trong `try/catch`; nếu thấy banner mất kết nối
   dù server ổn, mở Console của trình duyệt — lỗi thật được in ở đó (`refresh thất bại: ...`).
5. **Bản đồ trong trang ẩn**: Leaflet cần `map.invalidateSize()` khi trang chứa nó hiện lại (`setView("map")` đã làm). Nếu thêm bản đồ thứ hai, nhớ gọi.
6. **Hằng số trùng với backend**: vùng thử nghiệm (`PILOT_BOUNDS` ↔ `config.py`), tên kịch bản (nhãn trong `dashboard.js` và các `<select>` kịch bản ở `index.html` ↔ `SCENARIOS` trong `core/simulation.py`). Sửa một bên phải sửa bên kia
   (hướng giải quyết triệt để, chưa làm: để backend phát các hằng số này qua một endpoint cấu hình).
7. **Phân quyền ở frontend chỉ là UX** (ẩn nút, `setView` chặn các trang trong `ADMIN_VIEWS`). Quyền thật luôn do backend kiểm tra (`auth="admin"` trên route).
8. Ngôn ngữ giao diện: tiếng Việt; tên hàm/biến: tiếng Anh.

## 5. CSS

16 file trong `frontend/css/`, **nạp theo thứ tự trong `index.html`**. Thứ tự có ý nghĩa vì một số selector được khai báo lại
ở file sau (cascade); đừng đổi thứ tự khi chưa kiểm tra.

| File                                                          | Nội dung                                                              |
| ------------------------------------------------------------- | --------------------------------------------------------------------- |
| `base.css`                                                    | Biến màu (`:root`), reset, kiểu chữ, form cơ bản                      |
| `shell.css`                                                   | Khung ứng dụng: thanh điều hướng trái, topbar, tiêu đề trang, nút bấm |
| `dashboard.css`                                               | Thẻ thống kê, thời tiết, bố cục workspace                             |
| `map.css`                                                     | Bản đồ: thanh công cụ, tìm kiếm, lớp, chú giải, bảng bên phải         |
| `events.css` · `insight.css` · `routing.css`                  | Danh sách sự kiện · thẻ nhìn trước hành trình · tìm tuyến             |
| `forecast.css` · `sources.css` · `reports.css` · `rescue.css` | Từng trang tương ứng                                                  |
| `dialogs.css`                                                 | Hộp thoại, form phản ánh, banner chọn vị trí, toast                   |
| `overlays.css`                                                | Marker trên bản đồ, hộp chi tiết, các chỉnh sửa bổ sung               |
| `auth-alert.css`                                              | Nút/menu tài khoản, banner cảnh báo                                   |
| `map-overrides.css`                                           | Chỉnh Leaflet / nhãn hồ nước                                          |
| `responsive.css`                                              | **Mọi media query** (màn rộng, tablet, điện thoại, giảm chuyển động)  |

Màu và khoảng cách dùng biến CSS ở `:root` trong `base.css` — đổi giao diện từ đây trước khi sửa từng chỗ. Dùng lại class có sẵn
(`section-card`, `section-title`, `button primary`, `button secondary`, `tag tag-teal`, `empty-state`...) để trang mới trông đồng nhất.
Thêm file CSS mới: tạo file, thêm `<link>` vào `index.html` (đặt trước `responsive.css`), thêm dòng vào bảng trên.

## 6. Công thức thêm tính năng

### 6.1. Thêm một trang mới

Ví dụ trang **"Thống kê"** hiển thị số điểm ngập / ùn tắc / sự cố từ `state.data.counts`.

**Bước 1 — Nút menu** trong `<nav>` của `index.html` (sao chép một `nav-item` có sẵn):

```html
<button class="nav-item" data-view="stats" title="Thống kê">
  <svg><use href="#i-chart" /></svg><span>Thống kê</span>
</button>
```

**Bước 2 — Vùng nội dung.** Quy tắc cứng: `id` phải là **`<tên>-view`** và có class `view` + thuộc tính `hidden`:

```html
<section id="stats-view" class="view" hidden>
  <div class="section-card">
    <div class="section-title">
      <div><h2>Thống kê</h2></div>
    </div>
    <div id="stats-content"></div>
  </div>
</section>
```

**Bước 3 — Module vẽ trang**: `frontend/js/views/stats.js`

```js
import { state } from "../state.js";
import { $ } from "../utils.js";

export function renderStats() {
  if (!state.data) return;
  const c = state.data.counts;
  $("#stats-content").innerHTML = `
    <p>Điểm ngập: <strong>${c.flood}</strong></p>
    <p>Ùn tắc: <strong>${c.traffic}</strong></p>
    <p>Sự cố: <strong>${c.incident}</strong></p>`;
}
```

**Bước 4 — Nối vào hai chỗ có sẵn** để trang vẽ khi mở và tự cập nhật mỗi 10 giây:

```js
// js/navigation.js  → trong setView(), cạnh các dòng `if (view === "forecast" ...)`
import { renderStats } from "./views/stats.js";
if (view === "stats" && state.data) renderStats();

// js/dashboard.js   → trong updateDashboard(), cạnh `if (state.view === "forecast") ...`
import { renderStats } from "./views/stats.js";
if (state.view === "stats") renderStats();
```

Nút menu `data-view="stats"` tự hoạt động nhờ trình xử lý click trong `initNavigation()` — không cần gắn sự kiện.

- **Trang chỉ dành cho admin:** thêm `admin-only` vào class nút menu và thêm `"stats"` vào `ADMIN_VIEWS` trong `config.js`
  (một nơi duy nhất). Đồng thời bảo vệ API tương ứng ở backend bằng `auth="admin"`.
- **Trang cần dữ liệu riêng:** viết `async function loadStats() { const d = await api("/api/stats"); ... }` (mẫu: `loadReports`
  trong `views/reports.js`) và gọi nó trong `setView()`.

### 6.2. Thêm một thành phần vào trang có sẵn

Ví dụ thêm ô "Số đoạn đường bị chặn" cạnh các thẻ thống kê ở đầu trang Bản đồ.

1. Thêm HTML có `id` vào `index.html` (sao chép một `.stat-card` có sẵn).
2. Điền giá trị trong `updateDashboard()` (`dashboard.js`):

   ```js
   $("#stat-blocked").textContent = String(
     d.roads.filter((r) => r.blocked).length,
   );
   ```

`updateDashboard()` chạy mỗi 10 giây nên thành phần tự cập nhật. Cần dữ liệu **mới** từ server: thêm trường vào kết quả
`build_snapshot()` (backend, `core/simulation.py`) rồi đọc ở `state.data.<tên>`.

Thành phần phức tạp hơn (có logic riêng): tạo `views/<ten>.js` với `renderXxx()` + `initXxx()`, rồi gọi `initXxx()` trong
`initListeners()` của `main.js` và `renderXxx()` trong `updateDashboard()`.

### 6.3. Thêm hộp thoại (dialog)

```html
<dialog id="my-dialog">
  <div class="dialog-heading">
    <h2>Tiêu đề</h2>
    <button class="icon-button close-dialog" type="button">×</button>
  </div>
  …nội dung…
</dialog>
```

```js
$("#my-dialog").showModal(); // mở
```

Nút có class `close-dialog` và việc bấm ra ngoài hộp thoại để đóng đã được `dialogs.js` xử lý cho **mọi** `<dialog>`.

### 6.4. Thêm lớp vẽ lên bản đồ

1. Trong `map.js`: khai báo thêm `myLayer` vào dòng `export let map, ...` và tạo trong `initializeMap()`:
   `myLayer = L.layerGroup().addTo(map);`
2. Trong `renderMap()`: `myLayer.clearLayers();` rồi vẽ lại: `L.circleMarker([lat, lng], {...}).addTo(myLayer);`
3. Muốn có công tắc bật/tắt: thêm checkbox `data-layer="my"` trong menu lớp ở `index.html`, thêm `my: true` vào `state.layers`
   (`state.js`), và chỉ vẽ khi `state.layers.my` đúng.

### 6.5. Gọi một API mới

```js
import { api, post } from "../api.js";
const data = await api("/api/stats"); // GET
const res = await post("/api/reports/R-1234", { status: "verified" }); // POST
```

Cả hai ném `Error` có thông báo tiếng Việt khi lỗi — bọc `try { … } catch (e) { toast(e.message) }`.
Tương ứng backend: [BACKEND.md → Cách thêm một endpoint](BACKEND.md#cách-thêm-một-endpoint).

### 6.6. Thêm biểu tượng

Thêm `<symbol id="i-ten" viewBox="…">…</symbol>` vào khối SVG ở đầu `index.html`, rồi dùng `icon("ten")` trong template.

## 7. Kiểm thử frontend

`frontend/tests/smoke.mjs` nạp **các module thật** trong jsdom, nối vào **backend Python thật** (DB tạm) và thao tác như người dùng:
xem bản đồ, mở dự báo, tìm tuyến, đăng nhập sai/đúng, trang admin, đổi kịch bản, gửi và duyệt phản ánh, cứu hộ, đăng xuất.

```bash
npm install            # lần đầu
npm run test:frontend  # 34 kiểm tra (cần Python 3.10+; nếu lệnh Python không phải `python3`, đặt biến PYTHON)
```

Nó bắt được: import thiếu/sai tên, vòng phụ thuộc gãy, id/selector bị đổi, API đổi hình dạng. Nó **không** kiểm tra giao diện
nhìn thế nào (pixel/CSS) — vẫn cần mở trình duyệt xem sau thay đổi về style. Khi thêm trang/chức năng, thêm một đoạn vào file này
(mẫu: các khối `console.log("\n[n] ...")`; helper `click`, `submit`, `change`, `waitFor`, `check`).
