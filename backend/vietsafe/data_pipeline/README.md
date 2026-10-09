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

## DATA-03 / OpenStreetMap road network

DATA-03 bổ sung `ingestion/osm.py` và `processing/osm_network.py`. Demo DATA-02 và
registry API giữ nguyên. Luồng mới: Overpass JSON → nodes/ways → lọc/split →
directed road IDs → `RoadRegistry` + lineage + quarantine. Không sinh observation,
không kết nối Forecast/Routing/Map và không thay root CLI của DATA-02.

### Nguồn và giới hạn ingestion

OSM data © OpenStreetMap contributors. Production/publication phải tuân thủ
ODbL attribution/licensing: <https://www.openstreetmap.org/copyright>.
Fixture `data/fixtures/osm/overpass-small.json` là **OSM-format test fixture tự tạo**,
không phải dữ liệu quan trắc production hay raw OSM tải về.

`--bbox south,west,north,east` là yêu cầu HTTP tường minh tới Overpass; endpoint
mặc định `https://overpass-api.de/api/interpreter`, có thể override. Query dùng
`way["highway"]` và recurse node liên quan, `out meta`. Node/way metadata giữ trong
lineage. Đây là snapshot của response, không hứa có toàn bộ đường ngoài bbox.
Giữ nguyên way được trả về, không clip geometry tại biên bbox.

Giới hạn bbox: tọa độ hữu hạn đúng thứ tự, không cắt kinh tuyến 180°, tối đa 0.05°
mỗi chiều và diện tích xấp xỉ 25 km². Query timeout 1–60 giây, mặc định 25; HTTP
socket timeout bằng query timeout +5 giây. Mỗi lời gọi fetch gửi một request,
không có vòng retry của ứng dụng. User-Agent: `VietSafe-Data03/1.0` kèm URL repo.
Input/response tối đa 10 MiB, UTF-8 JSON; malformed JSON, key trùng, NaN/Infinity,
overflow số, thiếu `elements` hoặc Overpass `remark` bị từ chối toàn response.
Import module và `--input` không gọi HTTP; không tự lưu raw response.

### Policy đường, segmentation và hướng

- Nhận motorway/trunk/primary/secondary/tertiary và các `_link` tương ứng,
  unclassified/residential/living_street/service. Loại footway/path/pedestrian/
  cycleway/steps, highway không nằm trong allowlist và `area=yes`.
- Policy bảo thủ: `no` hoặc `private` ở access/vehicle/motor_vehicle đều bị loại,
  kể cả có override cụ thể hơn. Chưa diễn giải đầy đủ luật access theo phương tiện.
- Split tại đầu/cuối đường mở và node chung giữa các way hợp lệ. Không gộp way;
  giao nhau theo tọa độ nhưng không chung node ID không tự tạo junction.
- Ring đơn giản dùng các shared anchor; nếu chưa đủ hai anchor, bổ sung node ID
  nhỏ nhất cho đến đủ hai, xoay ring tại anchor nhỏ nhất nhưng giữ hướng OSM gốc.
  Không phát hành segment khép kín chưa tách. Node lặp nội bộ/self-retracing hoặc
  vòng có dưới ba node phân biệt bị quarantine, không gắn suffix giả.
- Hai chiều tạo `f` và `r`; oneway=yes/true/1 đi theo sequence OSM gốc,
  oneway=-1 đi ngược. Roundabout và motorway mặc định một chiều; no/false/0
  ghi rõ sẽ ghi đè mặc định. Giá trị oneway lạ và subkey điều kiện/hướng/phương tiện
  của oneway/access/vehicle/motor_vehicle bị quarantine trong v1.

### ID, geometry và lineage

ID tuân thủ Data-01: `osm:v1:<way_id>:<u>:<v>:<path_sha256>:<f|r>`.
Canonical path là tuple integer nhỏ hơn giữa sequence và sequence đảo.
Hash input ASCII chính xác `way=<way_id>;nodes=<id1>,<id2>,...`, không space/newline;
SHA-256 đủ 64 hex thường. ID không chứa thời gian, random hoặc vị trí hàng.

`coordinates` của cả f/r lưu **canonical order (latitude, longitude)**;
`endpoint_a/b` là u/v canonical. `directionality=forward` cho f, `reverse` cho r.
Hướng di chuyển thật được ghi thêm trong `lineage.travel_node_ids`; không được
coi cả hai record đều đi từ endpoint_a tới endpoint_b khi tích hợp về sau.
Length dùng haversine với bán kính cố định 6371.0088 km, làm tròn 9 chữ số thập phân.
Tên thiếu dùng `OSM way <id>`; `source_type=osm`, `source_id` là way ID dạng string.

`network_version=osm-v1-<24 hex>` được tính từ SHA-256 **raw bytes** và processing
policy/version. Cùng raw bytes và policy tạo cùng version/registry checksum.
Thay whitespace/thứ tự element trong raw cũng đổi network version, nhưng không
đổi road ID nếu way/path/hướng không đổi. URL file hay thời điểm chạy không vào
network version; URL/file path vẫn được ghi trong provenance nên đổi source path
có thể đổi bundle JSON. Khi thay thuật toán cần tăng `PROCESSOR_VERSION`.

Metadata riêng giữ way ID, full source node IDs, source segment, canonical/travel
sequence, raw checksum, query/bbox/endpoint, node/way metadata và processor version.
Offline file không kèm query/bbox thì ghi null, không bịa provenance live.
Duplicate payload cùng ID nhưng khác nội dung loại toàn bộ ID đó; payload giống
hệt được deduplicate. Missing node, coordinate sai, way ID sai, thiếu node,
topology mơ hồ, geometry suy biến và ID collision đều có quarantine report.
Policy filtering có report riêng và thống kê, không trộn với dữ liệu hỏng.

`result.registry_json()` serialize đúng `RoadRegistry.to_dict()` với thứ tự ổn
định, số hữu hạn, UTF-8. `result.to_json()` là bundle gồm registry, provenance,
lineage, filtered, quarantine và statistics. Nếu không còn road hợp lệ,
`registry=null`, giữ report; không sửa RoadRegistry để chấp nhận registry rỗng.

### CLI OSM

Chạy từ `backend`:

```bash
python -m vietsafe.data_pipeline.ingestion.osm --help
python -m vietsafe.data_pipeline.ingestion.osm --input ../data/fixtures/osm/overpass-small.json
python -m vietsafe.data_pipeline.ingestion.osm --input ../data/fixtures/osm/overpass-small.json --output /tmp/vietsafe-osm-new.json
```

Hai mode `--input` và `--bbox` loại trừ nhau. Không có `--output` thì chỉ in summary.
Output ghi bundle JSON bằng exclusive create; không ghi đè và không tự tạo thư mục
cha. Chọn path mới nếu đã tồn tại. Không có road hợp lệ hoặc lỗi input trả exit 2;
nếu output được yêu cầu cho kết quả rỗng, bundle vẫn chứa report và registry null.

Live chỉ khi người chạy chủ động yêu cầu, ví dụ bbox nhỏ ở Hà Nội:

```bash
python -m vietsafe.data_pipeline.ingestion.osm --bbox 21.030,105.800,21.032,105.802 --timeout 15
```

Không commit raw live/output. Tests dùng fixture nhỏ, HTTP mock và output tạm:

```bash
python -m unittest tests.data.test_osm_ingestion tests.data.test_osm_network -v
python -m unittest discover -s tests/data -t . -v
```

### Giới hạn DATA-03

Chưa hỗ trợ relation turn restrictions, barrier/node access routing, đầy đủ
access theo phương tiện/điều kiện, PBF, lịch sử OSM, topology repair hoặc routing.
Vì vậy registry không phải chỉ dẫn giao thông đủ điều kiện đưa vào production.
Chưa có DEM/NASA/GPM/SMAP, rainfall, soil moisture, elevation enrichment,
satellite-to-road alignment, temporal alignment, feature engineering, Forecast
dataset/T-GCN, database migration hay integration Forecast/Routing/Map.

Tham khảo quy tắc nguồn:
[Overpass QL](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL),
[OSM oneway](https://wiki.openstreetmap.org/wiki/Key:oneway).
