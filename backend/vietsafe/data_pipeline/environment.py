"""Validated, immutable environmental grids. No I/O or road alignment."""

import hashlib
import re
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from types import MappingProxyType
from urllib.parse import urlsplit

from .registry import canonical_bytes, finite_number

SCHEMA = "vietsafe.environment-grid.v1"
PROCESSING_VERSION = "environment-1"
VARIABLES = {
    "dem": ("elevation", "m"),
    "gpm": ("precipitation_rate", "mm/h"),
    "smap": ("soil_moisture", "m3/m3"),
}


class EnvironmentInputError(ValueError):
    """Invalid environmental data or unsupported normalization policy."""


def require(condition, message):
    if not condition:
        raise EnvironmentInputError(message)


def utc_timestamp(value):
    """Require an explicit timezone; normalize to UTC without inventing times."""
    require(isinstance(value, str) and re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value
    ), "Expected timezone-aware ISO timestamp")
    if not value.endswith("Z"):
        require(int(value[-5:-3]) <= 23 and int(value[-2:]) <= 59,
                "Invalid timezone offset")
        require(not value.endswith("-00:00"), "Unknown timezone offset is not UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (ValueError, OverflowError) as error:
        raise EnvironmentInputError("Invalid timestamp") from error


def _time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _freeze(value):
    if isinstance(value, dict):
        require(all(isinstance(key, str) for key in value), "Metadata keys must be strings")
        for key in value:
            _utf8(key)
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    require(value is None or type(value) in (str, bool) or finite_number(value),
            "Metadata must contain finite JSON values")
    if isinstance(value, str):
        _utf8(value)
    return value


def _utf8(value):
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise EnvironmentInputError("Text must be valid Unicode for UTF-8 serialization") from error


def _thaw(value):
    if isinstance(value, (dict, MappingProxyType)):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class EnvironmentalGrid:
    source_type: str
    product: str
    product_version: str
    variable: str
    units: str
    rows: int
    cols: int
    origin_lat: float
    origin_lon: float
    lat_step: float
    lon_step: float
    values: tuple
    nodata: object
    observed_at: str | None
    available_at: str | None
    source_uri: str
    raw_checksum: str
    metadata: dict

    def __post_init__(self):
        require(isinstance(self.source_type, str) and self.source_type in VARIABLES,
                "Unsupported source type")
        require((self.variable, self.units) == VARIABLES[self.source_type],
                "Unsupported variable/unit; no unit guessing or implicit conversion")
        for name in ("product", "product_version", "source_uri"):
            require(isinstance(getattr(self, name), str) and getattr(self, name).strip(),
                    f"{name} is required")
            _utf8(getattr(self, name))
        try:
            uri = urlsplit(self.source_uri)
            require(bool(uri.scheme) and not uri.username and not uri.password,
                    "Use a stable source URI/reference without credentials")
        except ValueError as error:
            raise EnvironmentInputError("Invalid source URI") from error
        require(isinstance(self.raw_checksum, str) and re.fullmatch(r"[0-9a-f]{64}", self.raw_checksum),
                "raw_checksum must be a lowercase SHA-256")
        require(type(self.rows) is int and type(self.cols) is int and self.rows > 0 and self.cols > 0,
                "rows/cols must be positive integers")
        require(self.rows * self.cols <= 3601 * 3601, "Grid exceeds supported sample count")
        for name in ("origin_lat", "origin_lon", "lat_step", "lon_step"):
            require(finite_number(getattr(self, name)), f"{name} must be finite")
        require(self.lat_step < 0 and self.lon_step > 0,
                "Rows run north to south; columns run west to east")
        require(-90 <= self.origin_lat <= 90 and -180 <= self.origin_lon <= 180,
                "Origin outside WGS84 bounds")
        require(-90 <= self.origin_lat + (self.rows - 1) * self.lat_step <= 90 and
                -180 <= self.origin_lon + (self.cols - 1) * self.lon_step <= 180,
                "Grid sample extent outside WGS84 bounds; wrapping unsupported")
        require(self.nodata is None, "Normalized nodata must be null")
        require(isinstance(self.values, (list, tuple)) and len(self.values) == self.rows,
                "Row count mismatch")
        normalized = []
        for row in self.values:
            require(isinstance(row, (list, tuple)) and len(row) == self.cols, "Column count mismatch")
            for value in row:
                require(value is None or finite_number(value), "Grid values must be finite numbers or null")
                if value is not None:
                    if self.source_type == "gpm":
                        require(value >= 0, "Precipitation must be non-negative")
                    if self.source_type == "smap":
                        require(0 <= value <= 1, "Soil moisture must be within [0, 1]")
            normalized.append(tuple(row))
        object.__setattr__(self, "values", tuple(normalized))
        require(isinstance(self.metadata, dict), "metadata must be an object")
        try:
            metadata = _thaw(_freeze(self.metadata))
        except RecursionError as error:
            raise EnvironmentInputError("Metadata nesting is too deep") from error
        for name in ("processing_version", "original_variable", "original_units", "reference"):
            require(isinstance(metadata.get(name), str) and metadata[name].strip(),
                    f"metadata.{name} is required")
        require(metadata.get("crs") == "EPSG:4326", "Only EPSG:4326 normalized grids are supported")
        require(metadata.get("grid_registration") in ("point", "cell_center"),
                "Specify point or cell_center grid registration")
        for name in ("observed_at", "available_at"):
            value = getattr(self, name)
            require(value is not None or self.source_type == "dem", f"{name} is required")
            if value is not None:
                object.__setattr__(self, name, utc_timestamp(value))
        if self.observed_at is not None and self.available_at is not None:
            require(_time(self.available_at) >= _time(self.observed_at),
                    "available_at precedes observed_at")
        if self.source_type == "dem":
            require(metadata.get("temporal_semantics") == "static", "DEM requires static time semantics")
        if self.source_type == "gpm":
            for key in ("interval_start", "interval_end"):
                metadata[key] = utc_timestamp(metadata.get(key))
            start, end = _time(metadata["interval_start"]), _time(metadata["interval_end"])
            require(start < end, "GPM interval_start must precede interval_end")
            require(start <= _time(self.observed_at) <= end, "GPM observed_at must lie in its interval")
            require(_time(self.available_at) >= end, "GPM available_at precedes interval_end")
        object.__setattr__(self, "metadata", _freeze(metadata))

    def cell_center(self, row, col):
        """Return (latitude, longitude); for HGT this is the point sample location."""
        require(type(row) is int and type(col) is int and
                0 <= row < self.rows and 0 <= col < self.cols, "Grid index out of bounds")
        return self.origin_lat + row * self.lat_step, self.origin_lon + col * self.lon_step

    def to_dict(self):
        return {"schema": SCHEMA, **{field.name: _thaw(getattr(self, field.name))
                                    for field in fields(self)}}

    def to_json(self):
        return canonical_bytes(self.to_dict()).decode("utf-8")

    def checksum(self):
        return hashlib.sha256(canonical_bytes(self.to_dict())).hexdigest()

    @classmethod
    def from_dict(cls, value):
        require(isinstance(value, dict), "Expected grid object")
        expected = {field.name for field in fields(cls)} | {"schema"}
        require(set(value) == expected and value["schema"] == SCHEMA,
                "Unsupported schema or unexpected/missing grid fields")
        return cls(**{key: item for key, item in value.items() if key != "schema"})
