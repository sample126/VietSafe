# Chạy và phát triển module AI nghiên cứu

Đây là **suy luận bằng checkpoint đã huấn luyện trên dữ liệu lịch sử**, không phải dịch vụ dự báo thời tiết/giao thông trực tuyến. Không có huấn luyện hoặc tải dữ liệu trong quá trình khởi động web.

## Chạy tại máy hiện tại

Từ checkout `vietsafe-ai-integration`, dùng Python đang chứa đúng các thư viện của nghiên cứu:

```powershell
.\scripts\start-ai.ps1 -ResearchRoot 'F:\Data for Life' -Python 'C:\Users\DELL\anaconda3\python.exe' -Port 8790
```

Mở `http://127.0.0.1:8790/forecast-lab.html`, hoặc vào web chính → **Dự báo → Mở mô hình AI**. Nếu cổng bận, chọn cổng khác. Dừng bằng Ctrl+C. Lần mở mô hình đầu tiên cần đọc dữ liệu, kiểm tra mã băm và nạp checkpoint; những lần sau dùng lại bộ nhớ đệm. Khởi động lại server khi thay đổi cấu hình/artifact.

Các đường dẫn minh họa ở trên thuộc máy phát triển; **backend không hard-code các đường dẫn đó**. Trên máy khác, chỉ cần truyền `-ResearchRoot` và `-Python` phù hợp. Script chỉ lắng nghe `127.0.0.1` và không cài thư viện tự động.

Máy chưa có thư viện: tạo môi trường Python 3.11–3.13 riêng rồi cài `python -m pip install -r requirements-ai.txt`. Bản đã kiểm tra dùng Python 3.13.5, scikit-learn 1.6.1. Các phiên bản đóng băng tránh đọc checkpoint bằng phiên bản sklearn khác. Không cần Torch cho lần tích hợp HGB này.

Ứng dụng cơ sở vẫn chạy theo `docs/DEVELOPMENT.md`. Khi chưa đặt biến môi trường AI, danh mục trả `not_configured`, trang hiển thị hướng dẫn và không tự giả lập kết quả.

## Cấu trúc artifact cục bộ

`VIETSAFE_AI_RESEARCH_ROOT` trỏ đến thư mục cha của các thư mục nghiên cứu:

```text
<research-root>/
  vietsafe-model-comparison-20261007/
    prepared/{depth,rain}.parquet
    results/HGB_all_nodes_leaves31_iter240.joblib
    results/test_predictions.npz
  vietsafe-traffic-tgcn-20261007/
    source/data__sz_speed.csv
    source/data__sz_adj.csv
    results/HGB_neighbours_l31_i240.joblib
  vietsafe-floodnet/early_warning/
    data/processed/{sites,quality,features}.json
    data/processed/<site-id>.parquet
    artifacts/{warning_30,warning_60}.joblib
    artifacts/shadow_policy.json
```

`artifact_manifest.json` ghi SHA-256 của 25 tệp cần cho runtime. Bellinge chỉ đọc trường `timestamps` trong NPZ để giữ nguyên tập cửa sổ minh họa; không đọc `truth` hay dự báo lưu sẵn làm kết quả. Runtime gọi `predict`/`predict_proba` của checkpoint thật.

Chỉ dùng artifact tin cậy của nghiên cứu này: định dạng joblib có thể thực thi mã khi giải tuần tự. Backend xác minh hash trước khi nạp. Không nhận file/path/model tùy ý từ HTTP, không tải checkpoint từ URL. Muốn đổi artifact phải review nguồn, cập nhật manifest và chạy lại kiểm tra parity; không đổi hash để bỏ qua lỗi một cách máy móc.

Các tệp thí nghiệm và dữ liệu thuộc nguồn riêng; giấy phép MIT của web **không tự động cấp quyền phân phối lại chúng**. Bellinge có dữ liệu cảm biến/mạng theo CC BY 4.0, còn dữ liệu mưa có điều kiện nghiên cứu/giáo dục, phi thương mại được ghi trong hồ sơ; không áp một giấy phép chung cho mọi thành phần. FloodNet và SZ-Taxi cần giữ và rà soát điều kiện nguồn tương ứng khi chia sẻ. Nhánh này chỉ đưa mã adapter và hash lên Git. Chưa tự động cấp artifact cho máy đồng đội/Render/Docker.

## API và hợp đồng

| Method | Đường dẫn | Đầu vào | Kết quả |
|---|---|---|---|
| GET | `/api/ai/catalog` | — | Các task và trạng thái cấu hình; chưa nạp mô hình |
| GET | `/api/ai/sites` | `task` | Các điểm, ngày hợp lệ và lựa chọn mặc định |
| GET | `/api/ai/times` | `task`, `site_id`, `day` | Các origin hợp lệ |
| POST | `/api/ai/predict` | JSON chỉ gồm `task`, `site_id`, `origin` | Dự báo theo từng chân trời + lịch sử đến thời điểm phát |

Ví dụ yêu cầu (dùng header `X-VietSafe: local` và quy tắc Origin sẵn có của ứng dụng):

```json
{"task":"floodnet","site_id":"ugliest_cyan_elephant","origin":"2023-08-10T19:45:00+00:00"}
```

Các trường luôn có trong dự báo: `schema_version`, `task`, `mode`, `dataset`, `model`, `model_version`, `quantity`, `unit`, `time_basis`, `origin_kind`, `public_alert_allowed=false`, `hanoi_calibrated=false`, `future_observations_used_as_input=false`. Mỗi phần tử `horizons` có `minutes` và `value`; `unit` của dự báo nằm ở cấp ngoài. `current.unit` có thể khác: với FloodNet, quan trắc hiện tại là mét còn dự báo là xác suất 0–1.

- HTTP 400: task/điểm/thời điểm/schema sai hoặc đầu vào không đủ chất lượng.
- HTTP 503: chưa cấu hình, thiếu dependency, thiếu artifact hoặc xác minh/nạp thất bại. Không trả giá trị dự báo giả.
- HTTP 500: lỗi ngoài dự kiến, chi tiết chỉ ở nhật ký server theo hạ tầng hiện tại.

Quy ước thời gian:

- FloodNet: timestamp có múi giờ, chuẩn hóa UTC; giao diện ghi UTC.
- Bellinge: bộ dữ liệu đã xử lý dùng datetime không gắn múi giờ; giữ đồng hồ nguồn, **chưa tự nhận đó là UTC hoặc giờ Việt Nam**. `origin_utc=null`.
- SZ-Taxi: chỉ số dòng 2411–2971; chưa gán lịch ngày giờ vì nguồn CSV không chứa thông tin đó. `origin_utc=null`.

Đây là API đọc và chạy thử trên tập dữ liệu cố định, dùng cùng server hiện có; không yêu cầu tài khoản AI riêng. Cấu hình bật AI chỉ dành cho chạy nghiên cứu tại máy trong PR này.

## Tiền xử lý và giới hạn

- **Bellinge:** bốn cảm biến, hai chuỗi mưa; thống kê chuẩn hóa lấy trước 2019. Ffill tối đa hai bước và trung vị train theo benchmark; tại mốc phát cần đủ bốn cảm biến, ít nhất 22/24 quan trắc mỗi cảm biến và mưa không thiếu. HGB dự báo phần chênh so với hiện tại rồi cộng mực nước hiện tại, không clip thành độ ngập.
- **SZ-Taxi:** số không/âm được xử lý là thiếu theo giao thức nghiên cứu hiện tại (không có nghĩa quy tắc này đúng cho mọi nguồn tốc độ). Ffill tối đa bốn bước, tách train/validation/test; sau đó dùng trung vị train. Đưa thêm mask và lịch sử lân cận vào mô hình. UI trả tỷ lệ quan trắc; không gắn km/h.
- **FloodNet:** chỉ cửa sổ split 4, độ ngập hiện tại dưới 5 cm, tuổi mực nước 0–10 phút, phủ dữ liệu ≥ 80%, tuổi mưa 15–105 phút. Danh sách 42 đặc trưng loại hoàn toàn cột nhãn tương lai. Dự báo riêng 30 và 60 phút, hiệu chỉnh sigmoid bằng checkpoint cũ. Nếu xác suất 30 phút cao hơn 60 phút thì báo cờ không nhất quán, không âm thầm đổi số. Ngưỡng “shadow review” chỉ là đề nghị rà soát nghiên cứu; không phát thông báo cho dân.

Các phép điền thiếu/chuẩn hóa ở đây phục vụ **checkpoint cố định và bộ dữ liệu đã kiểm thử**. Adapter cho nguồn trực tuyến cần kiểm tra lại chất lượng, phân phối, thời điểm dữ liệu thực sự đến hệ thống và hiệu chỉnh trước khi dùng.

## Kiểm thử

Tại thư mục `backend`:

```powershell
python -m unittest discover -s tests -t .
```

Kiểm tra parity trên artifact máy nghiên cứu (không train lại):

```powershell
$env:VIETSAFE_AI_VERIFY_ROOT='F:\Data for Life'
$env:OMP_NUM_THREADS='2'
$env:OPENBLAS_NUM_THREADS='2'
python -m unittest tests.test_ai_artifacts -v
```

Tại thư mục gốc, dùng Node đáp ứng `package-lock.json` (đã chạy với Node 24.19.0):

```powershell
npm ci --ignore-scripts
$env:PYTHON='C:\Users\DELL\anaconda3\python.exe'
$env:PYTHONUTF8='1'
node frontend/tests/smoke.mjs
$env:VIETSAFE_AI_VERIFY_ROOT='F:\Data for Life'
node frontend/tests/ai-smoke.mjs
```

Test HTTP dùng DB và cổng tạm; test artifact chỉ đọc nghiên cứu. Nếu không có artifact, tám test parity được đánh dấu skip. Cần ghi rõ đã chạy hay bỏ qua khi gửi PR. Trong môi trường sandbox Windows, nếu thư mục TEMP hoặc loopback bị chặn, dùng thư mục TEMP có quyền ghi và quyền chạy kết nối nội bộ, không sửa logic ứng dụng để né test.

## Nguồn code và phân chia trách nhiệm

- `bellinge.py` chuyển phần inference từ `vietsafe-model-comparison-20261007/benchmark.py:Data`, không import script train.
- `sztaxi.py` chuyển phần inference từ `vietsafe-traffic-tgcn-20261007/benchmark.py:Data`.
- `floodnet.py` chuyển logic từ `vietsafe-floodnet/early_warning/predict_warning.py` và lựa chọn cửa sổ của `demo_local/server.py`.
- `service.py` chỉ quản lý vòng đời; `ai_controller.py` chỉ chuyển HTTP vào nghiệp vụ; UI không tính lại mô hình bằng JavaScript.

Backend gốc chưa có worker nền cho suy luận. Nhánh này serialize inference và giới hạn thread để phù hợp demo tại máy; chưa đo tải nhiều người dùng và chưa cung cấp triển khai production. Kế hoạch nối dữ liệu thật và cách push sau duyệt nằm ở [AI_INTEGRATION_PLAN.md](AI_INTEGRATION_PLAN.md).
