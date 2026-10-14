# VietSafe Data Module handoff — DATA-01 → DATA-07

Data Module là **offline, model-neutral foundation**. Nó cung cấp registry,
normalized grids, alignment, feature rows, graph, supervised-label interface,
forecast dataset, split và quality report. Đây là tài liệu bàn giao API;
**Integration chưa thực hiện** và không có model được train trong Data Module.

## Entry points

Các imports đều bắt đầu bằng `vietsafe.data_pipeline`:

| Module/API | Input → output |
| --- | --- |
| `ingestion.osm.read_overpass(path)` | Offline Overpass JSON → parsed data |
| `processing.osm_network.build_road_network(data)` | Parsed OSM → result.registry + lineage/quarantine |
| `ingestion.dem.read_hgt(...)` | HGT → EnvironmentalGrid; version/source URI explicit |
| `ingestion.gpm.read_gpm(path)`, `ingestion.smap.read_smap(path)` | Normalized interchange JSON → grid |
| `processing.alignment.align_environment(...)` | Registry/grids/targets → AlignmentResult |
| `features.engineering.build_features(registry, aligned, as_of=...)` | Alignment snapshot → tuple RoadFeatureRow |
| `features.graph.build_graph(registry)` | Registry → GraphTopology |
| `features.labels.RoadTarget` | Generic numeric supervised target, no automatic ground truth |
| `features.dataset.build_dataset(...)` | Registry/rows/labels → ForecastDataset |
| `features.split.chronological_split(dataset, ...)` | Dataset → checksum-referenced partitions/report |
| `audit.audit_artifacts(...)` | Artifacts + source evidence → QualityReport, read-only |
| `end_to_end.run_fixture_pipeline()` | Existing fixtures → deterministic smoke summary/report |

Contract draft v0.1.0 vẫn nằm ở [DATA.md](../../../docs/DATA.md),
[dictionary](../../../docs/DATA_DICTIONARY.md),
[schema](../../../docs/schemas/road-observation.schema.json). DATA-07 không sửa
contract. Dataset trung gian dưới đây không phải RoadObservation/API runtime.

## ForecastDataset contract

`dataset.to_dict()` có:

- `schema = vietsafe.forecast-dataset.v1`, `feature_version = features-v1`.
- `network_version`, `graph_checksum`, `graph`, `road_ids`.
- `timestep_minutes = 30`, `feature_names`, `feature_units`.
- `lookback_steps`, `horizon_steps`, `target_name`, `target_units`, `require_targets`.
- `samples`, `excluded`, missing/snapshot policies.

Object hỗ trợ `to_dict()`, `to_json()`, `checksum()`. Checksum là SHA-256 canonical
JSON (sorted keys, compact UTF-8, newline cuối); không tự chứa chính checksum
trong payload, không thêm current time/random/temp path.

Mỗi sample có issue_time, target_time, history_timestamps, X, X_mask, y, y_mask,
y_missing_reasons, label_available_at, label_checksums, event_ids,
feature_as_of và feature_row_checksums.

**X shape: L × N × F; hiện F=6.** X_mask cùng shape; y/y_mask shape N cho một
variable tại một horizon. L=lookback_steps; N theo `dataset.graph.road_ids`
(hoặc serialized `dataset.to_dict()["graph"]["road_ids"]`). Forecast phải lấy
feature order từ `dataset.to_dict()["feature_names"]`, không tự hard-code order.

## Feature order V1

| Index | Feature | Unit | Meaning |
| --- | --- | --- | --- |
| 0 | precipitation_rate_mm_h | mm/h | GPM rate exact bin |
| 1 | rain_30m_mm | mm | rate × 0.5 khi interval đúng 30 phút |
| 2 | rain_1h_mm | mm | đủ 2 bin 30 phút liên tiếp |
| 3 | rain_3h_mm | mm | đủ 6 bin 30 phút liên tiếp |
| 4 | soil_moisture | m3/m3 | SMAP exact time, không carry-forward |
| 5 | elevation_m | m | Static DEM join, provenance vẫn static |

Chưa có slope, TWI, traffic, flood history, drainage hoặc river level. Không
fabricate các feature chưa có source/methodology. Coarse GPM/SMAP cell **không
phải road-level ground truth**, nearest-cell không tăng precision nguồn.

## Time, horizon và leakage

Timestamp canonical UTC `Z`, cuối bin HH:00 hoặc HH:30. History kết thúc đúng
issue_time T; L=6 nghĩa là các bin-end T−150m…T. Horizon_steps integer dương:
1→T+30m, 2→T+60m. **Không giả hỗ trợ +15/+45 phút**. Nếu Forecast cần các horizon
đó, phải thống nhất contract mới; không tự interpolate trong Data Module.

Feature source observed không sau bin; available không sau feature as_of.
Dataset chỉ nhận snapshot as_of <= issue_time; backfill 02:30/as_of04:00 không
được dùng để dự báo tại 02:30. Snapshot mới nhất đủ điều kiện được chọn; snapshot
trùng identity nhưng khác payload bị reject. Không sử dụng target làm X.
Label_available_at sau issue_time là hợp lệ cho y lịch sử, giữ riêng để kiểm tra
cutoff huấn luyện. Chronological split chưa chọn lịch retraining: Forecast phải
xác minh label đã available ở thời điểm fit dự kiến.

## Missing, masks và eligibility

Zero là số đo hợp lệ: mask=true. Null là missing: mask=false. Không zero-fill,
interpolate, forward fill, scale/normalize hoặc impute. Thiếu một rainfall bin
thì window null; không partial sum. Thiếu road/timestep history thì exclude cả
sample và có report; không nhảy qua gap. Feature null trong row vẫn hợp lệ.

`require_targets=True` mặc định yêu cầu đủ target cho mọi road; thiếu/conflict
thì exclude có lý do. False giữ y=null/y_mask=false. Mọi preprocessing learned
về sau thuộc training pipeline; scaler phải fit TRAIN only, không dùng thống kê
validation/test. Data Module chưa normalize adjacency hoặc features.

## Graph và split

Graph version `road-connectivity-v1`, roads là nodes. Road IDs sort ổn định;
features/labels/matrix phải giữ đúng cùng order. Directed f/r giữ riêng. DATA-03
endpoints canonical: forward=a→b, reverse=b→a. Adjacency i→j theo travel continuity;
raw N×N 0/1, không self loops mặc định, không D^-1/2 A D^-1/2 normalization.

Chưa full OSM turn restrictions; raw connectivity có thể chứa U-turn. Adjacency
này phục vụ graph dataset foundation, **không routing-perfect**. Routing vẫn
độc lập. Dense matrix hiện phù hợp fixture/foundation, chưa tối ưu city-scale.

Split chronological theo target_time, rồi issue_time; ratios configurable,
mặc định 70/15/15. Không random row split. Cùng target time giữ cùng block;
event-aware mặc định giữ toàn event span, kể cả events liên thông. Purge-overlap
mặc định loại history của partition sau nếu chạm target block trước. Report
checksum mô tả samples bị purge. Ratios có thể lệch, partition có thể rỗng;
`EMPTY_SPLIT` là WARNING, không tự coi là lỗi integrity.

## Labels và nguồn dữ liệu thực

RoadTarget generic đã có, **repository hiện không có production flood ground
truth** trong fixtures của module. `flood_depth_cm` fixture là
**SYNTHETIC TEST FIXTURE — NOT PRODUCTION FLOOD GROUND TRUTH**.
Không được dùng fixture để báo cáo production accuracy/F1 hay chứng minh model
đã dự báo ngập thật. Runner DATA-07 remap synthetic template sang OSM road IDs
chỉ để test schema/flow; đây không phải nhãn đo đạc spatially matched.

HGT reader hỗ trợ SRTM integer format. GPM/SMAP JSON là interchange boundary;
**native NASA HDF5/NetCDF chưa decode trực tiếp**. Không claim NASA production
ingestion hoàn chỉnh, live OSM guaranteed hoặc production flood prediction.
Cần acquisition policy, licenses/coverage, validated conversions và real labels
được xác minh ở phase riêng; handoff này không tự triển khai các phần đó.

## Quality audit và kiểm chứng

Audit chỉ REPORT, không sửa/remove/fill dữ liệu. ERROR cho integrity/leakage;
WARNING cho missing/synthetic/isolated/empty splits; INFO cho summary. Không
hard-code missing threshold production. Cung cấp source alignment, feature rows
và labels để audit lineage; thiếu evidence trả `LINEAGE_NOT_VERIFIED`. Checksum
xác nhận consistency, không chứng minh source measurements đúng ngoài thực tế.

Chạy từ `backend`:

```bash
python -m vietsafe.data_pipeline.audit --help
python -m vietsafe.data_pipeline.audit --fixture-demo
python -m unittest discover -s tests/data -t . -v
```

Runner một bin dùng delayed GPM/SMAP bị mask tại issue time; có DEM static,
synthetic labels, graph/dataset/split/audit. 12-step feature fixtures kiểm tra
history/rain windows riêng. Hai lần chạy/order đảo ngược phải cho cùng hashes;
import/runner không network hoặc ghi artifacts tự động. Warnings không đồng
nghĩa production acceptance và zero errors không thay thế đánh giá nguồn thật.

## Integration boundary

Chưa kết nối Forecast service, Routing, Map, Reports hoặc database production
API; không adapter ngoài Data Module, migration, model training/evaluation hay
deployment. Integration sẽ là task riêng khi các module ổn định. Team Forecast
nhận model-neutral artifacts và chủ động thống nhất target/horizon/source policy;
không thay Data Contract ngầm để ghép hệ thống.
