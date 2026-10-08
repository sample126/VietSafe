# Data Dictionary — observation v0.1.0 (đề xuất)

Hợp đồng: [DATA.md](DATA.md). Schema: [road-observation.schema.json](schemas/road-observation.schema.json).
Ví dụ: [road-observation.example.json](examples/road-observation.example.json).
Mỗi field top-level bắt buộc xuất hiện; nullable nghĩa là cho phép giá trị JSON `null`,
không phải cho phép bỏ field. Số là hữu hạn, JSON number; boolean không phải number.
Các nguồn dưới đây là **nguồn dự kiến**, chưa được kết nối. Ví dụ chỉ dùng dữ liệu giả.

## Identity và thời gian

| Field name | Data type | Unit | Source | Nullable | Range hợp lệ | Description |
| --- | --- | --- | --- | --- | --- | --- |
| schema_version | string | — | Data contract | Không | `0.1.0` | Phiên bản draft, chưa là runtime API |
| dataset_version | string | — | Data release manifest | Không | `[a-z0-9][a-z0-9._-]*`, 1–128 ký tự | Release bất biến; một network version/release |
| network_version | string | — | Road registry | Không | Cùng cú pháp dataset_version | Pin topology, geometry, segmentation, hướng và lineage |
| road_id | string | — | Registry demo hoặc OSM composite | Không | `HN-001`..`HN-036` hoặc `osm:v1:<way>:<u>:<v>:<64 hex>:<f/r>` | Opaque primary identity; không dùng tên đường |
| timestamp | string (date-time) | UTC | Alignment | Không | ISO 8601 `YYYY-MM-DDTHH:00:00Z` hoặc `...:30:00Z`, lịch hợp lệ | Cuối timestep 30 phút đề xuất; uniqueness theo road trong release |
| as_of | string (date-time) | UTC | Data materialization | Không | ISO 8601 giây nguyên `Z`; >= timestamp | Cutoff kiến thức; khác thời điểm đo; backfill có thể muộn hơn |
| data_mode | string | — | Producer | Không | `observed`, `demo` | Observed có thể gồm derived/imputed có ghi nhận, cấm simulated |
| latitude | number | độ Bắc | Registry geometry | Không | [-90,90] | Vĩ độ điểm giữa theo chiều dài segment, WGS84 |
| longitude | number | độ Đông | Registry geometry | Không | [-180,180] | Kinh độ cùng điểm đại diện; không thay polyline |

Range tọa độ toàn cầu chỉ là hard check; vùng pilot/geometry membership kiểm ở semantic
validator. Không hardcode Hà Nội vào schema để tránh đổi contract khi mở rộng vùng.

## Features

| Field name | Data type | Unit | Source | Nullable | Range hợp lệ | Description |
| --- | --- | --- | --- | --- | --- | --- |
| rainfall_30m | number | mm | NASA GPM IMERG hoặc nguồn mưa được duyệt | Có | >=0 | Lượng tích lũy `(t-30m,t]`; không phải cường độ mm/h |
| rainfall_1h | number | mm | Cùng product/run/alignment mưa | Có | >=0 | Tổng hai bin 30m đầy đủ trong `(t-1h,t]` |
| rainfall_3h | number | mm | Cùng product/run/alignment mưa | Có | >=0 | Tổng sáu bin 30m đầy đủ trong `(t-3h,t]` |
| soil_moisture | number | m³/m³ | NASA SMAP surface soil moisture | Có | [0,1] + product QC | Hàm lượng nước thể tích lớp bề mặt 0–5 cm; không phải % hay tỷ lệ bão hòa; không trộn root-zone |
| elevation | number | m, EGM96 geoid | NASADEM/SRTM sau QC | Có | Hữu hạn, cho phép âm | Cao độ terrain đại diện segment; không phải độ sâu ngập/mặt cầu |
| slope | number | độ | Dẫn xuất DEM | Có | [0,90) | Độ dốc terrain, không phần trăm; phương pháp lấy đại diện phải pin |
| twi | number | không thứ nguyên | Dẫn xuất DEM | Có | Hữu hạn, cho phép âm | `ln((a/1m)/tan(beta))`; flow/epsilon/aggregation theo manifest |
| traffic_speed | number | km/h | Traffic provider; phép đo được duyệt | Có | >=0 | Tốc độ trung bình theo thời gian của segment/hướng trong bin 30m; 0 là đứng yên |
| free_flow_speed | number | km/h | Traffic baseline hoặc giả định registry có gắn nhãn | Có | >0 | Tốc độ tham chiếu thông thoáng, không đồng nhất OSM maxspeed; cách ước lượng/version ở manifest |
| historical_flood_count | integer | đợt ngập/365 ngày | Catalog sự kiện đã xác minh | Có | >=0 | Đếm sự kiện phân biệt trong `(t-365d,t)`, chỉ input biết trước as_of; thiếu coverage -> null |
| current_flood_depth | number | cm trên mặt đường | Đo hiện trường/sensor hoặc report có phép đo xác minh | Có | >=0 | Giá trị hợp lệ tại t, nêu vị trí/độ đại diện/TTL trong lineage; severity không cung cấp depth |
| flood_status | boolean | — | Độ sâu hợp lệ hoặc bằng chứng verified | Có | true/false/null | True: có ngập; false: xác nhận khô; null: chưa biết; không phải risk hay blocked |

Không đặt trần tùy ý cho rainfall/speed/depth/TWI; QC theo vùng/product phát hiện outlier,
không clip mất dấu vết. Null có lý do; `current_flood_depth > 0` đòi `flood_status=true`,
depth=0 đòi false; status true hoặc false có thể chưa có số đo depth.
Mưa đầy đủ cùng quy trình phải thỏa 30m <= 1h <= 3h. Soil moisture 0.67 là 0.67 m³/m³,
không tự hiểu là 67% saturation; dù đúng range vẫn cần QC product.

## Quality và provenance

| Field name | Data type | Unit | Source | Nullable | Range hợp lệ | Description |
| --- | --- | --- | --- | --- | --- | --- |
| quality_score | number | không thứ nguyên | Data QC `coverage-v0.1` | Không | [0,1] | Tổng trọng số 12 feature /12, round 4 decimals; không phải model confidence |
| quality_flags | array of object | — | Data QC | Không | Có thể [] | Lý do thiếu, cũ, xung đột hoặc proxy; null feature phải có missing/stale/rejected/conflict |
| source | array of object | — | Producer và lineage manifest | Không | >=1 entry | Metadata theo nhóm field cùng nguồn/phương pháp/thời gian; mỗi non-null feature hoặc tọa độ có đúng một entry |

### `source[]`

Mọi field dưới đây bắt buộc trong mỗi entry. Nếu hai feature khác provenance/time/method,
tách entry. Một feature có nhiều raw input dùng manifest lineage, không lặp feature trong
hai entry. Entry chỉ tham chiếu field non-null. `record_ref` chỉ là tham chiếu, không fetch
hay tải nguồn khi validate cấu trúc.

| Field name | Data type | Unit | Source | Nullable | Range hợp lệ | Description |
| --- | --- | --- | --- | --- | --- | --- |
| fields | array of string | — | Data | Không | >=1, unique, chỉ 12 feature + latitude/longitude | Field nhận provenance này; không gồm road_id hoặc score |
| provider | string | — | Raw metadata | Không | nasa_gpm, nasa_smap, nasadem, srtm, openstreetmap, traffic_provider, verified_community_report, derived, demo | Namespace nguồn; tên nhà cung cấp traffic cụ thể ghi trong product/manifest |
| product | string | — | Raw metadata | Không | 1–256 ký tự | Tên product + run, ví dụ IMERG Early; SMAP phải chỉ rõ surface product |
| version | string | — | Product/transform | Không | 1–128 ký tự | Version dữ liệu hoặc recipe; không dùng nhãn latest |
| record_ref | string | — | Lineage registry | Không | 1–2048 ký tự | Ref bất biến đến record hoặc manifest có IDs/checksums của mọi raw input, spatial/temporal bounds, license, retrieval times, transform config/code |
| observed_at | string (date-time) | UTC | Raw event time | Không | ISO 8601 giây nguyên Z; <= timestamp | Thời điểm quan sát cuối cùng đóng góp; từng input/time bounds trong manifest |
| available_at | string (date-time) | UTC | Provider + ingest/audit | Không | ISO 8601 giây nguyên Z; observed_at <= available_at <= as_of | Sớm nhất phiên bản này được hệ thống dùng; community tính cả xác minh, aggregate lấy max availability inputs |
| valid_until | string (date-time) hoặc null | UTC | TTL policy | Có | ISO 8601 giây nguyên Z; > timestamp khi có | Dynamic bắt buộc có TTL theo recipe; static bất biến có thể null |
| method | string | — | Transform | Không | measurement, aggregate, derived, carry_forward, imputed, simulated | Các phương pháp hợp lệ/QC có điểm 1, 1, 1, 0.5, 0.5, 0 tương ứng |

`derived` cần manifest dẫn về NASADEM/SRTM/nguồn gốc, không che lineage bằng nhãn chung.
Source method chỉ mô tả cách sinh, không tự chứng minh số liệu đạt QC.

### `quality_flags[]`

| Field name | Data type | Unit | Source | Nullable | Range hợp lệ | Description |
| --- | --- | --- | --- | --- | --- | --- |
| field | string | — | QC | Không | Một trong 12 feature hoặc latitude/longitude | Trường bị ảnh hưởng |
| code | string | — | QC | Không | missing, stale, rejected, conflict, carried_forward, imputed, proxy, simulated | Mã máy đọc được; không dùng để đổi dữ liệu âm thầm |
| detail | string | — | QC | Không | 1–512 ký tự | Diễn giải và rule ID/căn cứ, không đưa PII vào đây |

## Ví dụ và kiểm tra

File JSON ví dụ có toàn bộ field và provenance, sử dụng `HN-001` trong registry demo,
`data_mode=demo`, source `demo`, method `simulated`; quality_score=0 theo policy.
Số giả lập được viết tay để minh họa contract, **không** lấy từ NASA/OSM, không phải mẫu
training, không khẳng định HN-001 thực sự có cao độ/ngập như ví dụ. Ref `example-only:*`
chỉ dùng trong fixture, chưa có manifest thật; production validator phải từ chối unresolved ref.

JSON Schema Draft 2020-12 cần bật `format` checking để bắt ngày không hợp lệ.
Cross-field checks và dataset checks đã được triển khai offline ở Data-02; xem
[DATA.md mục 12](DATA.md#12-data-02--implementation-offline). Schema và runtime API không đổi.
