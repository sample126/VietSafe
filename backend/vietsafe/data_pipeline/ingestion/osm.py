"""Bounded, explicit Overpass ingestion; imports and offline parsing never use HTTP."""

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

DEFAULT_ENDPOINT = "https://overpass-api.de/api/interpreter"
USER_AGENT = "VietSafe-Data03/1.0 (+https://github.com/sample126/VietSafe)"
MAX_BYTES = 10 * 1024 * 1024
MAX_BBOX_SPAN = 0.05
MAX_BBOX_KM2 = 25.0


class OSMInputError(ValueError):
    """Invalid, incomplete or oversized OSM input; no usable snapshot returned."""


@dataclass(frozen=True)
class QuarantineIssue:
    entity: str
    source_id: str
    code: str
    detail: str

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class OSMNode:
    node_id: int
    latitude: float
    longitude: float
    metadata_json: str


@dataclass(frozen=True)
class OSMWay:
    way_id: int
    nodes: tuple[int, ...]
    tags: object
    metadata_json: str


@dataclass(frozen=True)
class ParsedOSM:
    nodes: object
    ways: object
    quarantine: tuple[QuarantineIssue, ...]
    raw_payload: bytes
    provenance_json: str

    @property
    def provenance(self):
        return json.loads(self.provenance_json)

    @property
    def raw_checksum(self):
        return hashlib.sha256(self.raw_payload).hexdigest()


def positive_id(value):
    return type(value) is int and value > 0


def finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate_bbox(bbox):
    """south,west,north,east; no antimeridian crossing, <=0.05 deg/axis, <=25 km²."""
    if not isinstance(bbox, (tuple, list)) or len(bbox) != 4:
        raise OSMInputError("bbox requires south,west,north,east")
    if not all(finite(v) for v in bbox):
        raise OSMInputError("bbox coordinates must be finite numbers")
    south, west, north, east = map(float, bbox)
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise OSMInputError("Invalid bbox coordinate order/range")
    dy, dx = north - south, east - west
    area = dy * dx * 111.32**2 * math.cos(math.radians((south + north) / 2))
    if max(dx, dy) > MAX_BBOX_SPAN + 1e-12 or area > MAX_BBOX_KM2:
        raise OSMInputError("bbox exceeds small-area policy (0.05 deg/axis, 25 km²)")
    return south, west, north, east


def validate_timeout(timeout):
    if type(timeout) is not int or not 1 <= timeout <= 60:
        raise OSMInputError("timeout must be an integer in 1..60 seconds")
    return timeout


def build_query(bbox, timeout=25):
    values = validate_bbox(bbox)
    timeout = validate_timeout(timeout)
    bounds = ",".join(repr(v) for v in values)
    return f'[out:json][timeout:{timeout}];way["highway"]({bounds});(._;>;);out meta;'


def _strict_json(raw):
    def reject_constant(value):
        raise ValueError(f"Nonfinite JSON constant: {value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("JSON number overflows finite float range")
        return number

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8"), parse_constant=reject_constant, parse_float=finite_float,
                          object_pairs_hook=unique)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise OSMInputError(f"Malformed Overpass JSON: {error}") from error


def parse_overpass(raw, *, source="memory", bbox=None, query=None, endpoint=None):
    """Keep raw byte checksum; quarantine bad/conflicting elements without guessing IDs."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise OSMInputError("Expected UTF-8 bytes/text of at most 10 MiB")
    document = _strict_json(raw)
    if not isinstance(document, dict) or not isinstance(document.get("elements"), list):
        raise OSMInputError("Overpass response must contain an elements array")
    if document.get("remark"):
        raise OSMInputError("Overpass remark indicates possibly incomplete response")
    groups, quarantine = {}, []
    for item in document["elements"]:
        if not isinstance(item, dict) or item.get("type") not in ("node", "way"):
            quarantine.append(QuarantineIssue("element", "unknown", "UNSUPPORTED_ELEMENT",
                                              "Expected node or way object"))
            continue
        kind, identity = item["type"], item.get("id")
        if not positive_id(identity):
            quarantine.append(QuarantineIssue(kind, str(identity), f"INVALID_{kind.upper()}_ID",
                                              "ID must be a positive JSON integer"))
            continue
        groups.setdefault((kind, identity), []).append(item)
    nodes, ways = {}, {}
    for (kind, identity), entries in sorted(groups.items()):
        serialized = {json.dumps(e, sort_keys=True, ensure_ascii=False, allow_nan=False)
                      for e in entries}
        if len(serialized) != 1:
            quarantine.append(QuarantineIssue(kind, str(identity), "DUPLICATE_PAYLOAD_CONFLICT",
                                              "All payloads for this identity excluded"))
            continue
        item = entries[0]
        tags = item.get("tags", {})
        if not isinstance(tags, dict) or any(not isinstance(v, str) for v in tags.values()):
            quarantine.append(QuarantineIssue(kind, str(identity), "INVALID_TAGS",
                                              "Tags must be string-to-string mapping"))
            continue
        if kind == "node":
            lat, lon = item.get("lat"), item.get("lon")
            if not (finite(lat) and finite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                quarantine.append(QuarantineIssue(kind, str(identity), "INVALID_NODE_COORDINATE",
                                                  "Finite WGS84 latitude/longitude required"))
                continue
            nodes[identity] = OSMNode(identity, float(lat), float(lon), next(iter(serialized)))
        else:
            refs = item.get("nodes")
            if not isinstance(refs, list) or len(refs) < 2:
                quarantine.append(QuarantineIssue(kind, str(identity), "INSUFFICIENT_NODES",
                                                  "Way needs at least two node references"))
                continue
            if not all(positive_id(n) for n in refs):
                quarantine.append(QuarantineIssue(kind, str(identity), "INVALID_NODE_REFERENCE",
                                                  "Node references must be positive integers"))
                continue
            ways[identity] = OSMWay(identity, tuple(refs), MappingProxyType(dict(tags)),
                                    next(iter(serialized)))
    provenance = {
        "source": source, "endpoint": endpoint, "query": query,
        "bbox": list(validate_bbox(bbox)) if bbox is not None else None,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "generator": document.get("generator"), "osm3s": document.get("osm3s"),
        "fixture_notice": document.get("fixture_notice"),
    }
    return ParsedOSM(MappingProxyType(nodes), MappingProxyType(ways), tuple(quarantine), raw,
                     json.dumps(provenance, sort_keys=True, ensure_ascii=False, allow_nan=False))


def read_overpass(path):
    """Offline only; bounded file read and no implicit download."""
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    return parse_overpass(raw, source="file:" + str(Path(path)))


def fetch_overpass(bbox, *, endpoint=DEFAULT_ENDPOINT, timeout=25):
    """Exactly one explicit HTTP request, no application retry loop; no file writes."""
    query = build_query(bbox, timeout)
    parsed = urlsplit(endpoint)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password or parsed.fragment or parsed.query):
        raise OSMInputError("Endpoint must be HTTP(S) without credentials, query or fragment")
    request = Request(endpoint, data=urlencode({"data": query}).encode("ascii"),
                      headers={"User-Agent": USER_AGENT, "Accept": "application/json",
                               "Content-Type": "application/x-www-form-urlencoded"})
    with urlopen(request, timeout=timeout + 5) as response:
        raw = response.read(MAX_BYTES + 1)
        actual_endpoint = response.geturl()
    return parse_overpass(raw, source="overpass", bbox=bbox, query=query,
                          endpoint=actual_endpoint)


def main(argv=None):
    parser = argparse.ArgumentParser(description="VietSafe DATA-03 OSM registry (no integration)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="Offline Overpass JSON; never calls HTTP")
    source.add_argument("--bbox", help="Explicit live fetch: south,west,north,east")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--output", help="Create a new UTF-8 result bundle; never overwrite")
    args = parser.parse_args(argv)
    try:
        if args.output and Path(args.output).exists():
            raise OSMInputError("Output already exists; choose a new path")
        data = (read_overpass(args.input) if args.input else
                fetch_overpass(tuple(float(v) for v in args.bbox.split(",")),
                               endpoint=args.endpoint, timeout=args.timeout))
        from ..processing.osm_network import build_road_network

        result = build_road_network(data)
        if args.output:
            # Serialize first, then exclusive create; do not create parent directories.
            payload = result.to_json()
            with Path(args.output).open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
        print(json.dumps(result.summary(), ensure_ascii=False, sort_keys=True, allow_nan=False))
        return 0 if result.registry is not None else 2
    except (ValueError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
