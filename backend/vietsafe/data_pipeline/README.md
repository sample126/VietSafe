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

## DATA-04 Environmental Data

Environmental data hiện được chuẩn hóa **offline** theo luồng file → metadata →
validation → `EnvironmentalGrid` → SHA-256. Chỉ dùng Python standard library.
Không sửa Data Contract/RoadObservation, runtime network hoặc các module khác.

### Model và provenance

`environment.py` định nghĩa immutable `EnvironmentalGrid`, `to_dict()`,
`to_json()`, `from_dict()` và `checksum()`. Grid dùng WGS84/EPSG:4326, hàng 0 ở
phía Bắc, cột 0 ở phía Tây, `lat_step < 0`, `lon_step > 0`. Origin là tọa độ
sample/cell center [0,0]; `cell_center(row, col)` trả `(latitude, longitude)`.
Metadata `grid_registration` phân biệt `cell_center` với `point` (HGT). Chưa
hỗ trợ projected grid, wrap qua đường đổi ngày hay reproject/resample.

Dimensions/shape, extent, finite coordinates/resolution/values, units, source,
metadata, timestamp và SHA-256 được kiểm tra trước khi tạo grid. Bool/string
không được dùng như numeric value. Nodata normalized luôn là `None`/JSON `null`,
**không chuyển thành zero**. Zero là dữ liệu hợp lệ. Không nhận NaN/Infinity.
Không đoán unit hay tự chuyển unit; input phải dùng canonical unit.
Grid được giới hạn tối đa 3601 × 3601 samples; JSON interchange tối đa 8 MiB.

Provenance gồm source type, product/version, URI/reference, SHA-256 raw bytes,
observed/available time, processing version, original variable/units. URI phải
là reference ổn định do caller/input cung cấp (ví dụ `urn:...`); không tự lấy
absolute path thư mục tạm. Không cung cấp URL chứa credential/token. Metadata
không được chứa secrets, thời gian chạy, UUID hoặc temporary path. Input thời
gian phải có timezone và được chuẩn hóa UTC `Z`; không tự tạo `available_at`.
DEM dùng `temporal_semantics=static` và có thể giữ timestamps `null`. GPM giữ
interval_start/end với start < end; observed_at nằm trong interval (gồm hai
đầu mút), available_at không sớm hơn interval_end. SMAP giữ thời điểm nguồn.

Canonical JSON UTF-8 dùng sorted keys, compact separators, một newline cuối;
checksum grid là SHA-256 các bytes này. Không thêm current time/random ID/local
input path. Cùng bytes nguồn và metadata cho cùng output/checksum. Raw checksum
nhạy với thay đổi whitespace JSON; đây là checksum **file đầu vào**, không phải
claim đã xác thực NASA granule gốc hoặc xác thực nhà cung cấp.

### DEM: SRTM/HGT

`ingestion/dem.py` đọc HGT không nén: signed int16 big-endian, row-major từ Bắc
xuống Nam, filename chuẩn `N21E105.hgt` xác định góc Tây Nam của tile 1 độ.
Hỗ trợ hemisphere N/S/E/W; production chỉ nhận square 1201 hoặc 3601 samples.
Sample spacing = `1 / (n - 1)`; HGT là point samples có chung biên giữa tile,
**không cộng half-cell offset**. Elevation dùng `m`; -32768 → null. Product
version và stable source URI phải được truyền rõ; parser dành cho SRTM HGT
(EGM96), không suy diễn metadata acquisition/release từ ngày chạy hoặc tên file.

Fixture `N21E105-mini.hgt` là 18 bytes, 3x3, chỉ đọc khi opt-in
`--fixture-tile N21E105.hgt`. **TEST FIXTURE — NOT A REAL SRTM TILE**.
Fixture mang product `SYNTHETIC-HGT`, không claim vertical datum thực.
Không commit/tải tile SRTM production. Format reference:
[SRTM User Guide](https://lpdaac.usgs.gov/documents/179/SRTM_User_Guide_V3.pdf).

### GPM và SMAP: normalized interchange boundary

- `ingestion/gpm.py`: `precipitation_rate`, `mm/h`, giá trị >= 0.
- `ingestion/smap.py`: `soil_moisture`, `m3/m3`, giá trị trong [0,1].
- `ingestion/environment_json.py`: loader chung, giới hạn 8 MiB, strict JSON,
  reject duplicate keys (kể cả metadata), nonfinite, schema/version sai,
  missing/unknown top-level fields và provenance không đủ.

Input JSON có `schema=vietsafe.environment-grid.v1` và tất cả trường của model,
**trừ `raw_checksum`**. Loader tính raw_checksum từ đúng bytes file đã đọc;
không nhận checksum tự khai báo của chính file để tránh checksum tự tham chiếu.
Metadata bắt buộc: `processing_version=environment-1`, `original_variable`,
`original_units`, `reference`, `crs=EPSG:4326`, `grid_registration`.
Original variable/unit phải bằng canonical variable/unit vì loader không làm
conversion. GPM còn bắt buộc `interval_start` và `interval_end` trong metadata.
Các fixture JSON là ví dụ đầy đủ của interchange contract.

Output `to_dict()/to_json()` thêm raw_checksum; dùng `EnvironmentalGrid.from_dict`
để deserialize output. Output này không được đưa lại vào raw interchange loader.
Nếu sau này thêm converter native, phải giữ lineage/checksum granule riêng,
không thay checksum interchange bằng checksum chưa kiểm chứng.

**Normalized GPM/SMAP JSON là interchange/test boundary, KHÔNG phải native NASA
granule format.** Chưa decode HDF5/NetCDF, không viết parser giả và không thêm
h5py/netCDF4. NASA native grid cần converter được kiểm chứng riêng, đặc biệt
projected SMAP grid không được tự gắn nhãn WGS84. Fixtures 3x3 là synthetic test
values, không phải NASA production observations.

### Offline CLI và tests

Chạy từ `backend`:

```bash
python -m vietsafe.data_pipeline.ingestion.dem --help
python -m vietsafe.data_pipeline.ingestion.gpm --help
python -m vietsafe.data_pipeline.ingestion.smap --help
python -m vietsafe.data_pipeline.ingestion.dem --input ../data/fixtures/environment/dem/N21E105-mini.hgt --fixture-tile N21E105.hgt --product-version fixture-v1 --source-uri urn:vietsafe:fixture:dem
python -m vietsafe.data_pipeline.ingestion.gpm --input ../data/fixtures/environment/gpm/gpm-grid.json
python -m vietsafe.data_pipeline.ingestion.smap --input ../data/fixtures/environment/smap/smap-grid.json
python -m unittest tests.data.test_environment tests.data.test_dem_ingestion tests.data.test_gpm_ingestion tests.data.test_smap_ingestion -v
python -m unittest discover -s tests/data -t . -v
```

Không `--output`: chỉ in summary/checksum, không tạo file. Có `--output <path>`:
ghi canonical JSON bằng exclusive create, không overwrite, không tạo thư mục
cha. Dùng path mới; input lỗi hoặc output đã tồn tại trả exit 2. Tests ghi vào
thư mục tạm và chặn/mock network; không gọi NASA live.

### Giới hạn DATA-04

Không tạo `nasa.py` downloader: offline foundation chưa cần auth/network layer;
đưa downloader vào lúc này sẽ thêm xử lý credential/redirect mà task không cần.
Không có download khi import/chạy CLI. Không thay package entrypoint DATA-02.

DATA-04 **CHƯA map environmental grid vào road**; việc đó thuộc DATA-05.
Chưa có road sampling/spatial join, temporal aggregation, rainfall windows,
elevation enrichment, slope/TWI, feature engineering, training dataset,
Forecast/Routing/Map integration. Các giới hạn DATA-03 phía trên mô tả giai đoạn
DATA-03; DATA-04 chỉ bổ sung foundation offline nêu tại section này.

## DATA-05 Spatial + Temporal Alignment

`processing.alignment.align_environment(registry, dem=None, gpm=(), smap=(),
targets=())` nhận RoadRegistry và EnvironmentalGrid đã ingestion/validation.
`targets` là danh sách `(timestamp, as_of)`; cặp trùng deduplicate sau UTC
normalization. Hàm chỉ chạy offline trong bộ nhớ, không HTTP/ghi file. Output
`AlignmentResult` tách `static`, `dynamic`, `issues`, `summary`, giữ network
version/registry checksum. Đây là **dữ liệu trung gian**, chưa phải
RoadObservation hoàn chỉnh hoặc feature rows cho Forecast.

### Spatial V1

`processing/spatial_alignment.py` dùng `RoadSegment.representative_point()`
(length midpoint đã có) → nearest cell center trong hệ tọa độ grid.
Method: `representative-point-nearest-cell-v1`. Chỉ EPSG:4326; CRS khác trả
`UNSUPPORTED_CRS`, không transform. Origin/hướng grid giữ nguyên DATA-04;
HGT vẫn là point samples, không cộng half-cell offset vào origin.

Coverage inclusive tại center extent ± nửa spacing mỗi trục, point phải có
tọa độ WGS84 hợp lệ. Ngoài coverage trả `OUTSIDE_GRID`, không clamp vào cạnh.
Nearest index tính riêng từng trục, so sánh rational từ decimal representation
để tránh banker rounding. Tie chọn row/col nhỏ hơn (Bắc/Tây). Điểm đúng outer
half-cell boundary chọn edge cell trong coverage. Không geodesic nearest,
line/raster intersection, spatial interpolation hoặc thay geometry road.

Output giữ road point, row/col, cell center, method và grid checksum. Null giữ
null với `GRID_NODATA`, không chọn cell bên cạnh để lấp; zero hợp lệ. Directed
f/r giữ ID riêng dù cùng representative point và sample value.

### Static và temporal V1

DEM optional chỉ spatial align một lần/road; record timestamp/as_of=null, giữ
observed/available time nguồn (có thể null). Không giả time hoặc nhân bản DEM.
Dynamic timestep cố định 30 phút, timestamp là **BIN END**, HH:00:00Z hoặc
HH:30:00Z. Offset-aware normalize UTC Z; reject naive, :15, giây/phần lẻ giây
khác zero. `as_of >= timestamp`; as_of không cần khớp bin.

Temporal gates theo thứ tự: observed_at > target → `FUTURE_OBSERVATION`;
available_at > as_of → `NOT_AVAILABLE_AS_OF`; sau đó kiểm tra exact match:

- GPM: interval_end == target và observed_at == interval_end. Giữ nguyên
  interval_start/end và precipitation_rate `mm/h`; không overlap-weight,
  resample, carry-forward hoặc tạo rainfall windows.
- SMAP: observed_at == target; khác trả `NO_EXACT_TEMPORAL_MATCH`.
- Không nearest-time, forward/backward fill, averaging, interpolation hay
  missing→zero; không giả soil moisture không đổi.

Ví dụ GPM observed 02:30, available 04:00: target/as_of=02:30 bị chặn;
backfill target=02:30, as_of=04:00 có thể dùng, nhưng output vẫn giữ
source_available_at=04:00 và as_of=04:00, không claim realtime tại 02:30.

### Determinism, candidates và conflicts

Version `alignment-v1` có trong result/records. Dynamic sort theo timestamp,
road_id, variable, source_type; tie dùng full canonical record. Static sort theo
road_id/variable; issues theo canonical JSON. Checksum SHA-256 canonical UTF-8
JSON sorted keys, compact, newline cuối. Không thêm current time, random UUID
hoặc temporary path; caller phải cung cấp provenance ổn định.

Identity nguồn: `(source_type, variable, observed_at, product, product_version)`.
Checksum toàn EnvironmentalGrid gồm raw checksum/provenance giống nhau thì
deduplicate; khác checksum cùng identity thì quarantine mọi variant, không chọn
grid cuối. Variant vượt temporal gates trả `SOURCE_CONFLICT`; variant bị gate
chặn giữ reason temporal; tất cả variant xung đột đều value=null.

Khác product/version là candidate riêng, không ưu tiên ngầm. Output giữ
**mỗi candidate/road/target**, kể cả candidate không khớp (value=null + reason).
Consumer chỉ dùng record missing_reason=null; DATA-05 không collapse candidates
thành một feature. GPM/SMAP rỗng tạo `NO_SOURCE_GRID` từng road/target/source;
DEM optional vắng thì static=[]. Input sai trả `AlignmentInputError`.

Provenance giữ product/version, URI, raw/grid checksums, metadata/intervals,
observed/available times, spatial lineage, target/as_of. Chỉ copy metadata,
không copy toàn raster mỗi road. Không sửa road/network IDs hoặc input objects.

### Fixtures, tests và giới hạn

`data/fixtures/alignment/{gpm,smap}-alignment-grid.json` là **TEST FIXTURE**,
synthetic 3×3 grids phủ bbox nhỏ của OSM fixture, có zero/positive/null.
DEM tái dùng mini HGT DATA-04. Không phải NASA production observations.
Chạy từ `backend`:

```bash
python -m unittest tests.data.test_spatial_alignment tests.data.test_temporal_alignment tests.data.test_alignment -v
python -m unittest discover -s tests/data -t . -v
```

End-to-end: OSM fixture → registry; DEM/GPM/SMAP fixtures → grids → alignment.
Tests kiểm tra identity, provenance, deterministic ordering/checksum,
duplicates/conflicts, as_of và no HTTP. Không thêm CLI; function/tests đáp ứng
bước offline này.

**Coarse GPM/SMAP cell ≠ road-level ground truth.** V1 không thể hiện intersection
hoặc độ phủ toàn tuyến, không có precision cao hơn nguồn. Chưa hỗ trợ projection,
antimeridian/wrapping, DEM mosaics hoặc ưu tiên giữa product. Candidate per
target có thể tạo output lớn; chưa phải engine tối ưu production datasets.

DATA-06 có thể xây policy features/imputation riêng sau này. DATA-05 không tạo
rainfall windows, slope/TWI, traffic/history features, labels, adjacency matrix,
training tensors/splits; không tích hợp Forecast/Routing/Map, API/database.
Giới hạn DATA-03/04 phía trên mô tả giai đoạn tương ứng; section này chỉ bổ sung
alignment offline của DATA-05.
