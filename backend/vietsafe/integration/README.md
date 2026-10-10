# INT-03A — Draft Data / Forecast boundary

**DRAFT / PROVISIONAL — FORECAST OWNER APPROVAL STILL REQUIRED.**
This is a contract skeleton, validator, serializer and offline projection adapter.
It is not a Forecast implementation and does not complete INT-03.

Data ForecastDataset → DataForecastInput → [future ForecastProvider] → ForecastOutput

There is no compatible artifact model/provider, approved production target,
trained T-GCN, runtime/Routing/API/Map integration or prediction generation here.
The existing `core.forecast.forecast(road, current, neighbor_speed, rain, horizon)`
cannot consume this input directly. No runtime module is imported or modified.
Only Python standard library and public Data metadata/serialization are used.

## Public API

- `contracts.DataForecastInput(payload)` / `.from_dict(payload)` validates a draft
  inference request. `ForecastOutput` and `ForecastRoadResult` work the same way.
- `data_forecast.build_forecast_input(dataset, sample_index=0)` accepts the current
  public ForecastDataset object or its serialized dict. Selects one sample within
  that dataset; this is not an index join between independent artifacts.
- `data_forecast.normalize_forecast_output(metadata, road_results, *,
  network_version, road_ids)` wraps caller-supplied results. It checks the explicit
  prediction scope and inserts only UNAVAILABLE status rows for omitted roads.
  It never calculates metrics, chooses a provider, generates timestamps or calls
  a model. Test metric values are synthetic contract examples, not predictions.
- `ForecastOutput.validate_scope(network_version, road_ids)` validates an output
  against an external scope. Standalone serialization cannot know that scope.
- `validate_network_match(expected, actual)` rejects mismatches even when road IDs
  coincide. `ForecastProvider` is a typing Protocol only, not instantiated/registered.

Models store validated canonical JSON in frozen dataclasses: nested caller
containers cannot mutate them. `to_dict()` returns a fresh copy; `to_json()` is
sorted-key, compact UTF-8 JSON with a trailing newline and allow_nan=False.
`checksum()` is SHA-256 of those exact UTF-8 bytes, matching Data canonicalization.
No current time, random ID, file write or path is generated automatically.

## DataForecastInput v1

Schema `vietsafe.data-forecast-input.v1`, source schema
`vietsafe.forecast-dataset.v1`, contract_status=draft, mode=artifact.
Public FEATURE_NAMES/FEATURE_UNITS/FEATURE_VERSION are reused from Data:
precipitation_rate_mm_h, rain_30m_mm, rain_1h_mm, rain_3h_mm, soil_moisture,
elevation_m, in that order. Names and units must match exactly. No silent reorder,
extra speed/traffic/incident/free_speed/susceptibility/slope/TWI features.

X and X_mask: L × N × F. IDs unique, graph.road_ids equals road_ids in order.
Identity is (network_version, road_id); IDs are opaque strings. No ID parsing,
name joins, HN-to-OSM mapping or independent-array index joins.
Null requires false mask, finite numeric including zero requires true mask.
Booleans are invalid X values. No fill, scaling, normalization or imputation.
Forecast owner must decide missing-value handling in the future model.

Timestep is 30 minutes; only horizon_steps 1/2 and horizon_minutes 30/60.
UTC timestamps use exactly YYYY-MM-DDTHH:MM:SSZ. History has L consecutive
30-minute bin ends ending at issue_time. feature_as_of and feature_row_checksums
preserve Data's L × N shape; as_of cannot exceed issue_time. This draft deliberately
rejects fractional timestamp spellings. It does not invent a timestamp.

Graph version/network/registry checksum/order/raw binary adjacency/directed edges
and graph checksum are verified structurally. No self loops or normalization are
added. This is the Forecast road-as-node graph, NOT a Routing graph. Without the
source registry/evidence this boundary does not independently prove topology,
row-checksum contents or source truth; use Data quality audit before integration.

The adapter uses an explicit allowlist. It strips y/y_mask, target_name/values,
labels, label_available_at, label_checksums, event_ids and training split metadata.
Unknown nested graph fields are rejected, not copied into inference metadata.
No arbitrary source metadata is forwarded. For inference use a Data dataset built
with require_targets=False; absent/excluded history samples cannot be resurrected.
Only the selected sample and inference-relevant fields are validated; this is not
an audit of unrelated samples, training labels or splits.

## ForecastOutput v1

Schema `vietsafe.forecast-output.v1`, contract_status=draft. Caller provides mode,
network/model versions, issue_time, issued_at, horizon_minutes, forecast_time,
output_fields, roads and coverage. forecast_time = issue_time + horizon_minutes;
issued_at is publication time and may differ. No time is sampled from the clock.

Supported structural metrics: flood_risk, speed_km_h, risk, label. Only declared
output_fields may appear. An OK row has all declared fields non-null and correctly
typed. Producer-unsupported fields are omitted, not invented. Non-OK fields may
be omitted or null; STALE may retain finite old values for presentation. No risk
range/calibration, speed policy or production target is chosen by this skeleton.
No flood_depth/probability/confidence fields are assumed.

Statuses: OK, MISSING_INPUT, UNAVAILABLE, STALE. Non-OK requires nonempty reason_code.
OK means complete output, NOT safe road. Null is never converted to zero.
Coverage (total/predicted/missing_input/unavailable/stale) must equal actual rows,
not merely have the right sum. Duplicate rows and unknown scoped roads reject.
Normalization preserves the explicit caller scope order and adds status-only
UNAVAILABLE rows for omissions. Empty scope requires empty rows and zero coverage.
Staleness is caller-supplied here: no expiry threshold or runtime stale evaluation.

IntegrationContractError serializes code/message/optional path, never traceback.
Codes: INVALID_CONTRACT, NETWORK_VERSION_MISMATCH, UNKNOWN_ROAD,
FEATURE_SCHEMA_MISMATCH, UNSUPPORTED_HORIZON, MISSING_INPUT, UNAVAILABLE, STALE.

## Modes and unresolved owner decisions

Demo runtime stays HN IDs, rule-based and horizons 0/15/30/45/60. Draft output
validation supports those demo horizons but does not wrap/call the demo runtime.
Artifact input uses Data registry IDs (OSM or other Data registry IDs), +30/+60.
No per-road fallback between modes or networks. Matching schema does not certify
that a model is compatible or prediction is accurate.

Still blocking real Forecast implementation: production target/labels, compatible
model and input signature, missing-value policy, output metrics/units/scale,
requested horizons and approval of issue/publication semantics. Routing policies,
expiry thresholds and runtime mode selection are outside INT-03A.

## Offline validation

From backend, suppress optional Python bytecode writes:

```bash
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests/data -t . -v
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests/integration -t . -v
```

Tests reuse the existing Data fixture helper without changing it, test nested
label stripping with sentinel values, immutable copies, actual Data interoperability,
shape/order/checksums, masks, publication delay, all statuses and partial coverage.
Socket/HTTP are blocked at entrypoints; a fresh interpreter checks imports for
network/filesystem/DB side effects. No live providers or prediction accuracy tests.
