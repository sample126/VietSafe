"""OSM ways -> directed registry, with explicit conservative policy and lineage.

No HTTP, file writes, observation generation, or application integration.
"""

import hashlib
import json
import math
from collections import Counter
from dataclasses import dataclass

from ..exceptions import DataValidationError
from ..ingestion.osm import QuarantineIssue, positive_id
from ..registry import RoadRegistry, RoadSegment, canonical_bytes, checksum

PROCESSOR_VERSION = "osm-network-1.0.0"
HIGHWAY_TYPES = frozenset({
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "living_street", "service", "motorway_link", "trunk_link",
    "primary_link", "secondary_link", "tertiary_link",
})
BLOCKED_ACCESS = frozenset({"no", "private"})
ACCESS_KEYS = ("access", "vehicle", "motor_vehicle")


def filter_reason(tags):
    """Conservative motor-road policy; explicit denial wins, no mode-specific overrides."""
    if tags.get("highway") not in HIGHWAY_TYPES:
        return "HIGHWAY_EXCLUDED"
    if tags.get("area", "").lower() == "yes":
        return "AREA_EXCLUDED"
    for key in ACCESS_KEYS:
        if tags.get(key, "").lower() in BLOCKED_ACCESS:
            return key.upper() + "_RESTRICTED"
    return None


def canonical_node_path(nodes):
    nodes = tuple(nodes)
    if len(nodes) < 2 or not all(positive_id(n) for n in nodes):
        raise ValueError("Path requires at least two positive integer node IDs")
    if len(set(nodes)) != len(nodes):
        raise ValueError("Directed segment must be an unambiguous open node path")
    return min(nodes, nodes[::-1])


def road_id_hash_input(way_id, nodes):
    if not positive_id(way_id):
        raise ValueError("Way ID must be a positive integer")
    path = canonical_node_path(nodes)
    return f"way={way_id};nodes=" + ",".join(str(n) for n in path)


def stable_road_id(way_id, nodes, direction):
    if direction not in ("f", "r"):
        raise ValueError("Direction must be f or r relative to canonical path")
    path = canonical_node_path(nodes)
    digest = hashlib.sha256(road_id_hash_input(way_id, path).encode("ascii")).hexdigest()
    return f"osm:v1:{way_id}:{path[0]}:{path[-1]}:{digest}:{direction}"


def way_directions(tags):
    """+1/-1 relative to original OSM sequence, never relative to canonical sequence."""
    relevant = {"oneway", *ACCESS_KEYS}
    if any(k.startswith(tuple(v + ":" for v in relevant)) for k in tags):
        raise ValueError("Conditional/directional/mode-specific restrictions unsupported in v1")
    value = tags.get("oneway", "").strip().lower()
    if value in ("yes", "true", "1"):
        return (1,)
    if value == "-1":
        return (-1,)
    if value in ("no", "false", "0"):
        return (1, -1)
    if value:
        raise ValueError("Unsupported oneway value: " + value)
    if tags.get("junction") == "roundabout" or tags.get("highway") == "motorway":
        return (1,)
    return (1, -1)


def split_way(nodes, junctions):
    """Split at shared IDs; simple rings use shared anchors plus two smallest IDs.

    Internal repeated IDs, self-retracing paths and ambiguous rings are rejected.
    A ring is rotated to its smallest selected anchor while retaining OSM direction.
    """
    nodes = tuple(nodes)
    if len(nodes) < 2:
        raise ValueError("INSUFFICIENT_NODES")
    closed = nodes[0] == nodes[-1]
    core = nodes[:-1] if closed else nodes
    if len(set(core)) != len(core) or (closed and len(core) < 3):
        raise ValueError("AMBIGUOUS_CLOSED_LOOP" if closed else "UNSUPPORTED_TOPOLOGY")
    if closed:
        anchors = set(core) & junctions
        # Two stable distinct anchors ensure no segment is itself a closed ring.
        for node in sorted(core):
            if len(anchors) >= 2:
                break
            anchors.add(node)
        start = core.index(min(anchors))
        cycle = core[start:] + core[:start]
        nodes = cycle + (cycle[0],)
    else:
        anchors = {nodes[0], nodes[-1]} | (set(nodes) & junctions)
    cuts = [i for i, n in enumerate(nodes) if n in anchors]
    return tuple(nodes[a:b + 1] for a, b in zip(cuts, cuts[1:]))


def length_km(coordinates):
    """Spherical haversine, fixed mean Earth radius; not an external routing distance."""
    lengths = []
    for (lat1, lon1), (lat2, lon2) in zip(coordinates, coordinates[1:]):
        p1, p2 = math.radians(lat1), math.radians(lat2)
        dp, dl = p2 - p1, math.radians(lon2 - lon1)
        a = math.sin(dp / 2)**2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2)**2
        lengths.append(6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a)))))
    return round(math.fsum(lengths), 9)


@dataclass(frozen=True)
class OSMNetworkResult:
    registry: RoadRegistry | None
    _metadata_json: str

    def to_dict(self):
        return {"registry": self.registry.to_dict() if self.registry else None,
                **json.loads(self._metadata_json)}

    def to_json(self):
        return canonical_bytes(self.to_dict()).decode("utf-8")

    def registry_json(self):
        if self.registry is None:
            raise ValueError("No valid roads; inspect quarantine/filter report")
        return canonical_bytes(self.registry.to_dict()).decode("utf-8")

    def summary(self):
        data = json.loads(self._metadata_json)
        return {"network_version": data["network_version"],
                "raw_sha256": data["provenance"]["raw_sha256"],
                "processor_version": PROCESSOR_VERSION, **data["statistics"]}


def build_road_network(data):
    policy = {"version": PROCESSOR_VERSION, "highways": sorted(HIGHWAY_TYPES),
              "access_denials": sorted(BLOCKED_ACCESS), "access_keys": list(ACCESS_KEYS),
              "ring_anchors": "shared-plus-smallest-two-v1", "length": "haversine-6371.0088-km"}
    version = "osm-v1-" + checksum({"raw_sha256": data.raw_checksum, "policy": policy})[:24]
    quarantine = list(data.quarantine)
    filtered, accepted = [], {}
    for identity, way in sorted(data.ways.items()):
        reason = filter_reason(way.tags)
        if reason:
            filtered.append({"way_id": identity, "reason": reason})
            continue
        missing = sorted(set(way.nodes) - data.nodes.keys())
        if missing:
            quarantine.append(QuarantineIssue("way", str(identity), "MISSING_REFERENCED_NODE",
                                              "Missing/invalid node IDs: " + ",".join(map(str, missing))))
            continue
        try:
            directions = way_directions(way.tags)
            split_way(way.nodes, set())  # Preflight topology before computing shared nodes.
        except ValueError as error:
            code = str(error) if str(error) in {"AMBIGUOUS_CLOSED_LOOP", "UNSUPPORTED_TOPOLOGY",
                                                "INSUFFICIENT_NODES"} else "UNSUPPORTED_TOPOLOGY"
            quarantine.append(QuarantineIssue("way", str(identity), code, str(error)))
            continue
        accepted[identity] = (way, directions)
    counts = Counter(n for way, _ in accepted.values() for n in set(way.nodes))
    junctions = {n for n, count in counts.items() if count > 1}
    candidates = {}
    for identity, (way, directions) in sorted(accepted.items()):
        for segment in split_way(way.nodes, junctions):
            canonical = canonical_node_path(segment)
            coords = tuple((data.nodes[n].latitude, data.nodes[n].longitude) for n in canonical)
            length = length_km(coords)
            if length <= 0 or len(set(coords)) < 2:
                quarantine.append(QuarantineIssue("way", str(identity), "INVALID_GEOMETRY",
                                                  "Degenerate segment: " + str(segment)))
                continue
            for travel in directions:
                directed = segment if travel == 1 else segment[::-1]
                direction = "f" if directed == canonical else "r"
                road_id = stable_road_id(identity, canonical, direction)
                road = RoadSegment(
                    road_id, version, "osm", str(identity),
                    way.tags.get("name", "").strip() or f"OSM way {identity}",
                    coords, str(canonical[0]), str(canonical[-1]), length,
                    "forward" if direction == "f" else "reverse",
                )
                lineage = {
                    "osm_way_id": identity, "source_node_ids": list(way.nodes),
                    "segment_source_node_ids": list(segment),
                    "canonical_node_ids": list(canonical), "travel_node_ids": list(directed),
                    "raw_sha256": data.raw_checksum, "processor_version": PROCESSOR_VERSION,
                    "way_metadata": json.loads(way.metadata_json),
                    "node_metadata": [json.loads(data.nodes[n].metadata_json) for n in canonical],
                }
                candidates.setdefault(road_id, []).append((road, lineage))
    roads, lineage = [], {}
    for road_id, entries in sorted(candidates.items()):
        if len(entries) != 1:
            quarantine.append(QuarantineIssue("road", road_id, "ID_COLLISION",
                                              "All colliding segments excluded; no synthetic suffix"))
            continue
        road, origin = entries[0]
        try:
            RoadRegistry(version, [road])
        except DataValidationError as error:
            quarantine.append(QuarantineIssue("road", road_id, "INVALID_GEOMETRY", str(error)))
            continue
        roads.append(road)
        lineage[road_id] = origin
    registry = RoadRegistry(version, roads) if roads else None
    quarantine.sort(key=lambda q: (q.entity, q.source_id, q.code, q.detail))
    metadata = {
        "network_version": version, "processor_version": PROCESSOR_VERSION,
        "policy": policy, "provenance": data.provenance, "lineage": lineage,
        "quarantine": [q.to_dict() for q in quarantine], "filtered": filtered,
        "statistics": {"parsed_nodes": len(data.nodes), "parsed_ways": len(data.ways),
                       "eligible_ways": len(accepted), "emitted_ways": len({r.source_id for r in roads}),
                       "directed_roads": len(roads), "filtered_ways": len(filtered),
                       "quarantine_count": len(quarantine)},
    }
    return OSMNetworkResult(registry, canonical_bytes(metadata).decode("utf-8"))
