# VietSafe Data Module — DATA-02

Nền tảng Data chạy offline bằng Python standard library. Module biểu diễn road
observation, quản lý registry, kiểm tra provenance/chất lượng và tạo release demo
có manifest. Chưa được gọi từ application service hoặc HTTP API.

## Data Contract

Tuân theo draft v0.1.0 trong [DATA.md](../../../docs/DATA.md),
[dictionary](../../../docs/DATA_DICTIONARY.md) và
[JSON Schema](../../../docs/schemas/road-observation.schema.json):
một road segment + một timestamp = một observation trong mỗi dataset release.
Timestamp canonical là UTC `Z`, cuối bin 30 phút; `as_of` là cutoff kiến thức.
`None` giữ thành `null`; không đổi thiếu dữ liệu thành 0. NaN/Infinity bị từ chối.
`quality_score` là coverage của 12 feature, không phải xác suất đúng/an toàn.

## Package

| File/package | Trách nhiệm |
| --- | --- |
| `config.py` | `DataPaths`, đường dẫn và tạo thư mục theo yêu cầu |
| `exceptions.py` | Lỗi validation có cấu trúc, release đã tồn tại |
| `models.py` | Observation, source metadata, quality flag, JSON boundary |
| `registry.py` | Registry, geometry, hướng, lookup và fingerprint |
| `quality.py` | Vocabulary và policy coverage-v0.1 |
| `validation.py` | Kiểm tra cấu trúc, ngữ nghĩa, lineage và dataset |
| `manifest.py` | Manifest xác định được và xuất release không ghi đè |
| `pipeline.py` | Registry → observations → validation/quality → manifest → optional write |
| `adapters/demo.py` | Đọc mạng demo, tạo dữ liệu mô phỏng có provenance |
| `__main__.py` | CLI offline |
| `ingestion/`, `processing/`, `features/` | Chỉ là extension boundary cho DATA-03+ |

Validator triển khai contract hiện tại, không phải JSON Schema engine tổng quát.
Import config/package không tạo thư mục. `ensure_directories()` và chế độ write
là các thao tác tạo thư mục tường minh.

## Data directory

Mặc định dùng `data/` ở root repository; ghi đè bằng `VIETSAFE_DATA_ROOT` hoặc
CLI `--data-root`. Các thư mục: `raw/`, `interim/`, `processed/`, `manifests/`,
`registry/`, `fixtures/`. Fixture `demo-request.json` chỉ chứa tham số chạy demo.

Khi ghi thành công, release chứa:

- `processed/<dataset-version>/observations.jsonl`
- `processed/<dataset-version>/registry.json`
- `manifests/<dataset-version>.json` (marker hoàn tất)

Không ghi đè release/version cũ. Lock theo version ngăn các writer cùng cơ chế
ghi đồng thời; lock còn lại sau crash cần được kiểm tra thủ công, không tự xóa.
Thư mục `registry/` hiện chỉ là placeholder; snapshot registry của release nằm
cùng observations để giữ nhất quán phiên bản.

## Demo adapter

Chỉ đọc `vietsafe.core.network.ROADS`, không sửa core. Tạo 36 observation từ
mạng đường dựng tay: speed mô phỏng bằng 80% free speed, depth/status khô giả lập
cho đường có trạng thái biết; đường unknown giữ các trường này là null.
Mưa, SMAP, DEM và lịch sử chưa thu thập giữ null kèm lý do. Mọi giá trị có nguồn
được gắn `demo`/`simulated`; quality score bằng 0. Đây không phải dữ liệu NASA/OSM
thật hay ground truth huấn luyện. Điểm giữa polyline chỉ phục vụ registry demo.

## CLI và dry-run

Chạy từ thư mục `backend`, với Python 3.10 trở lên:

```bash
python -m vietsafe.data_pipeline --help
python -m vietsafe.data_pipeline --dataset-version vietsafe-data-0.1.0-demo --timestamp 2026-10-08T02:30:00Z --as-of 2026-10-08T02:30:00Z --created-at 2026-10-08T02:30:00Z --code-commit <FULL_40_HEX_GIT_SHA>
```

Thay `<FULL_40_HEX_GIT_SHA>` bằng kết quả `git rev-parse HEAD`. Các timestamp và
commit là input tường minh để cùng input/code/config tạo cùng checksum. CLI không
tự đọc fixture; truyền các trường trong fixture qua tham số như ví dụ trên.

Mặc định chỉ in summary JSON, không tạo release hay data directory. Chỉ thêm
`--write --data-root <OUTPUT_DIRECTORY>` khi muốn xuất release. Chọn version mới
cho lần xuất khác; không dùng SHA giả của test cho release thực.

## Test

Từ `backend`:

```bash
python -m unittest discover -s tests/data -t . -v
```

Test dùng output tạm, kiểm tra offline, checksum, không ghi đè, CLI dry-run,
validation và runtime không bị thay đổi. Không cần thêm dependency. Test đọc
schema Data-01; test bảo toàn runtime đọc network và so sánh simulation trước/sau.
Không commit output sinh ra. `.gitignore` của repository được giữ nguyên; khi
stage placeholder/fixture bị ignore, chỉ dùng `git add -f` với từng đường dẫn
được duyệt, không stage toàn bộ thư mục data.

## Giới hạn hiện tại

DATA-02 chưa triển khai OpenStreetMap thật, DEM, NASA GPM, NASA SMAP,
spatial alignment thật, temporal alignment thật, feature engineering thật,
T-GCN dataset hoặc kết nối Forecast, Routing, Map. Các tên provider và quy tắc
kiểm tra nguồn chỉ định nghĩa contract; không chứng minh đã có collector.
Không gọi HTTP, tải mạng, huấn luyện ML hoặc thay thế snapshot/API hiện tại.
