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

## INT-04A Routing Network Contract

**DRAFT / PROVISIONAL.** `RoadRegistry → RoutingNetwork` is a pure structural
adapter for a future Routing consumer. It does not calculate a route or connect
Forecast. There is no Forecast→Routing adapter, risk mapping, stale/unknown policy,
closure policy, vehicle policy, ETA, route solver integration or runtime/API integration.

Public API:

```python
from vietsafe.integration.registry_routing import build_routing_network
network = build_routing_network(registry, expected_registry_checksum=registry.checksum)
payload = network.to_dict()
```

Input accepts a public Data RoadRegistry or its full serialized dict. Dict roads
must contain the existing RoadSegment fields (including source/name metadata);
they are reconstructed through RoadSegment/RoadRegistry validation. Optional
`registry_checksum` in the dict and/or the keyword expected_registry_checksum are
verified against the canonical RoadRegistry checksum, not raw file bytes. Malformed
Data inputs become IntegrationContractError with INVALID_CONTRACT or, when identified,
NETWORK_VERSION_MISMATCH. Error serialization contains no raw Data traceback/message.
No Data validator is changed. Object inputs are also revalidated without mutation.

Output schema: `vietsafe.routing-network.v1`, contract_status=draft. Fields:
network_version, registry_checksum, nodes, arcs, outgoing, routing_policy.
RoutingArc/ RoutingNetwork accept a payload or `.from_dict(payload)`, are frozen
with canonical JSON storage, and offer detached `.to_dict()`, `.to_json()`, `.checksum()`.
Canonical encoding is sorted keys, compact UTF-8, no NaN, trailing newline; checksum
is SHA-256 of those bytes. No self-referential checksum, timestamps or random keys.

Graph semantics are distinct:

- Forecast graph: **road-as-node**, adjacency describes travel continuity between roads.
- Routing network: **junction-as-node, travel arc-as-edge**, built directly from
  registry endpoint_a/endpoint_b and directionality. No feature adjacency is read.

Nodes are nonempty opaque endpoint IDs, unique and sorted. No node coordinate
records are invented. Road IDs are opaque and never parsed to infer connectivity.
Within a network the arc identity is (road_id, travel_from, travel_to); across
networks it additionally requires network_version. Parallel roads remain separate.

| Registry directionality | Travel arcs | Travel geometry |
| --- | --- | --- |
| forward | endpoint_a → endpoint_b | canonical coordinates |
| reverse | endpoint_b → endpoint_a | entire canonical polyline reversed |
| both | both of the above, same road_id | one polyline per travel direction |

The adapter does not infer direction from OSM f/r ID suffixes. DATA-03 has already
produced separate directed RoadSegments; each forward/reverse segment produces
exactly one arc. Demo both produces two arcs without changing/suffixing road_id.
Geometry remains [latitude, longitude], including every intermediate coordinate.
No snapping, GeoJSON conversion or length recomputation occurs. length_km is copied
exactly and must be finite and positive. Self loops reject rather than disappear.

Arcs are sorted by (road_id, travel_from, travel_to). outgoing[node] contains their
indices within THIS same artifact; it is never a cross-artifact identity. Nodes
with no outgoing arcs have an empty list. Validation checks index contents,
composite uniqueness, network consistency and both-direction pair symmetry.
Unknown fields such as risk/speed/closure/forecast reject in this contract.

routing_policy=`registry-endpoints-directionality-v1-no-turn-restrictions` describes
only topology conversion. It is not a routing cost/product policy. The standalone
contract validates structure; without the source registry it cannot prove a digest
refers to actual source contents or independently confirm an endpoint's physical
location. The adapter ensures geometry direction relative to registry semantics.
Full OSM turn restrictions, barriers and vehicle-specific access remain unresolved;
this artifact is not a production navigation network or route recommendation.

Tests cover four-point reversal, both directions sharing identity, parallel roads,
self-loop rejection, checksum verification, input-order independence, outgoing index,
and the existing local OSM fixture through read_overpass/build_road_network. Socket
and HTTP are blocked in key tests. Fresh-process import tests reject writes/mkdir/DB/
network and ensure neither Forecast graph nor runtime Forecast/Routing was imported.

INT-04B still requires owner decisions on risk semantics, missing/stale behavior
and closure sources/policy. INT-04A does not decide or implement them.

## INT-05A Map Network Contract

**DRAFT / PROVISIONAL.** `RoadRegistry → MapNetwork` projects canonical registry
roads for a future API/Frontend consumer. This is an offline artifact only: no
Forecast→Map, Routing→Map, API endpoint, Frontend integration or runtime mode switch.

Public API:

```python
from vietsafe.integration.registry_map import build_map_network
network = build_map_network(registry, expected_registry_checksum=registry.checksum)
payload = network.to_dict()
```

Accepts RoadRegistry or its full serialized dict; dict roads are reconstructed
through the public Data RoadSegment/RoadRegistry validators. An optional
registry_checksum in the dict and/or expected_registry_checksum argument is checked
against canonical RoadRegistry serialization, not raw file bytes. Invalid Data
inputs become IntegrationContractError (INVALID_CONTRACT, or
NETWORK_VERSION_MISMATCH for mixed network versions). Input is not mutated.

Schema `vietsafe.map-network.v1`, contract_status=draft; required envelope fields:
network_version, registry_checksum, coordinate_order=lat_lon and roads. Each road
has exactly road_id, network_version, name, geometry and directionality. IDs are
opaque; identity is (network_version, road_id). No parsing OSM IDs, name joins,
index joins, renaming or HN→OSM mapping. Roads are unique and sorted by road_id.
The adapter sorts source roads deterministically; a manually constructed contract
with unsorted/duplicate roads rejects rather than silently deduplicating.

Geometry remains canonical [latitude, longitude] from RoadSegment.coordinates.
**Reverse does NOT reverse map geometry.** Forward/reverse/both each produce ONE
map entry per RoadSegment. Both is never expanded into two map entries. Separate
OSM f/r segments keep their original separate road IDs. Travel-direction arrows
would require a future presentation policy, not mutation of this canonical line.

The three structures serve different purposes:

- Forecast graph: road-as-node.
- Routing network: junction-as-node, travel arc-as-edge; reverse geometry is travel ordered.
- Map network: road entries + canonical polylines, independent of travel direction.

MapNetwork is built directly from RoadRegistry, never RoutingNetwork arcs. Using
arcs as its source would duplicate both roads and incorrectly reverse geometry.
RouteOutput travel geometry belongs to a later Routing→Map contract.

No source_id, provenance, labels, tensor, adjacency, grids, feature checksums or
OSM lineage is exposed. No risk/flood_risk/speed/label/forecast/horizon/model_version,
route/ETA/distance/warnings are present; unknown fields reject. The only checksum
in the payload is the source registry checksum; the artifact checksum is a method.

MapRoad and MapNetwork are frozen canonical-JSON models, accepting payloads or
.from_dict(). to_dict() returns a deeply detached copy; to_json()/checksum() use
sorted keys, compact UTF-8, a trailing newline, allow_nan=False and SHA-256. No
current time, random UUID or file path is generated. Finite numeric lat/lon ranges,
at least two points and at least two distinct coordinates are required. Booleans,
NaN/Infinity, empty names/IDs and mixed networks reject. No GeoJSON conversion,
snapping or geometry simplification is performed. Standalone checksum-format
validation does not prove the registry exists; adapter verification requires the
actual source registry or expected checksum. Empty registries remain unsupported.

Tests include four-point forward/reverse/both geometry, order-independent dict and
object inputs, detached state, malformed geometry, duplicate IDs, mixed versions,
the existing offline OSM fixture and 36-road demo registry (not doubled to 72).
Socket/HTTP are blocked at key entrypoints, and a fresh process checks import safety.
No simulation/model/route solver is called. Run the same Data/Integration unittest
commands above; no dependencies or runtime files change.

Forecast→Routing remains blocked on owner risk semantics, missing/stale and closure
policy. Forecast/Map presentation or API contract skeletons may proceed separately
when authorized; this task does not implement them or runtime integration.
