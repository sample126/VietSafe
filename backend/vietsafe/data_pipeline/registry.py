"""Immutable registry snapshot with indexed lookup; no HTTP/DB dependencies."""

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from types import MappingProxyType

from .exceptions import DataValidationError, ValidationIssue

VERSION_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{0,127}", re.ASCII)
ROAD_PATTERN = re.compile(
    r"(?:HN-(?:00[1-9]|0[12][0-9]|03[0-6])|osm:v1:[1-9][0-9]*:[1-9][0-9]*:[1-9][0-9]*:[0-9a-f]{64}:[fr])",
    re.ASCII,
)


def finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def canonical_bytes(value):
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def checksum(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class RoadSegment:
    road_id: str
    network_version: str
    source_type: str
    source_id: str
    name: str
    coordinates: tuple[tuple[float, float], ...]
    endpoint_a: str
    endpoint_b: str
    length_km: float
    directionality: str

    def __post_init__(self):
        # Copy caller-owned coordinates; never expose mutable runtime network lists.
        try:
            object.__setattr__(self, "coordinates", tuple(tuple(c) for c in self.coordinates))
        except TypeError as error:
            raise DataValidationError(
                [ValidationIssue("coordinates", "INVALID_GEOMETRY", "Expected coordinate pairs")]
            ) from error

    def representative_point(self):
        """Length midpoint along a short WGS84 polyline (local equirectangular metric)."""
        lengths = []
        for (lat1, lon1), (lat2, lon2) in zip(self.coordinates, self.coordinates[1:], strict=False):
            lengths.append(
                math.hypot(lat2 - lat1, (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2)))
            )
        half = sum(lengths) / 2
        for index, length in enumerate(lengths):
            if length and half <= length:
                a, b = self.coordinates[index : index + 2]
                ratio = half / length
                return tuple(a[j] + ratio * (b[j] - a[j]) for j in (0, 1))
            half -= length
        return self.coordinates[-1]

    def to_dict(self):
        return dict(asdict(self), coordinates=[list(c) for c in self.coordinates])


class RoadRegistry:
    def __init__(self, network_version, roads):
        issues = []
        if not isinstance(network_version, str) or not VERSION_PATTERN.fullmatch(network_version):
            issues.append(
                ValidationIssue("network_version", "INVALID_VERSION", "Invalid registry version")
            )
        entries = {}
        for index, road in enumerate(roads):
            prefix = f"roads[{index}]"
            if not isinstance(road, RoadSegment):
                issues.append(ValidationIssue(prefix, "INVALID_TYPE", "Expected RoadSegment"))
                continue
            if not isinstance(road.road_id, str) or not ROAD_PATTERN.fullmatch(road.road_id):
                issues.append(ValidationIssue(prefix + ".road_id", "INVALID_ID", "Invalid road ID"))
            elif road.road_id in entries:
                issues.append(
                    ValidationIssue(prefix + ".road_id", "DUPLICATE_ROAD_ID", road.road_id)
                )
            else:
                entries[road.road_id] = road
            if road.network_version != network_version:
                issues.append(
                    ValidationIssue(
                        prefix + ".network_version", "NETWORK_MISMATCH", "Mixed registry versions"
                    )
                )
            for field in ("source_type", "source_id", "name", "endpoint_a", "endpoint_b"):
                value = getattr(road, field)
                if not isinstance(value, str) or not value.strip():
                    issues.append(
                        ValidationIssue(
                            prefix + "." + field, "EMPTY_FIELD", "Nonempty string required"
                        )
                    )
            if road.directionality not in ("both", "forward", "reverse"):
                issues.append(
                    ValidationIssue(
                        prefix + ".directionality",
                        "INVALID_DIRECTION",
                        "Expected both/forward/reverse",
                    )
                )
            if not finite_number(road.length_km) or road.length_km <= 0:
                issues.append(
                    ValidationIssue(
                        prefix + ".length_km", "INVALID_LENGTH", "Finite positive length required"
                    )
                )
            coords_valid = len(road.coordinates) >= 2 and all(
                len(c) == 2
                and all(finite_number(v) for v in c)
                and -90 <= c[0] <= 90
                and -180 <= c[1] <= 180
                for c in road.coordinates
            )
            if not coords_valid or len(set(road.coordinates)) < 2:
                issues.append(
                    ValidationIssue(
                        prefix + ".coordinates",
                        "INVALID_GEOMETRY",
                        "Nondegenerate lat/lon polyline required",
                    )
                )
        if not entries:
            issues.append(ValidationIssue("roads", "EMPTY_REGISTRY", "At least one road required"))
        if issues:
            raise DataValidationError(issues)
        self._network_version = network_version
        self._roads = MappingProxyType(dict(sorted(entries.items())))

    @property
    def network_version(self):
        return self._network_version

    def get(self, road_id):
        return self._roads.get(road_id)

    def __iter__(self):
        return iter(self._roads.values())

    def __len__(self):
        return len(self._roads)

    def to_dict(self):
        return {"network_version": self.network_version, "roads": [r.to_dict() for r in self]}

    @property
    def checksum(self):
        return checksum(self.to_dict())
