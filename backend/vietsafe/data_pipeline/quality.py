"""Internal reason names map to the unchanged v0.1.0 wire flag vocabulary."""

from enum import Enum

SCHEMA_VERSION = "0.1.0"
FEATURE_FIELDS = (
    "rainfall_30m",
    "rainfall_1h",
    "rainfall_3h",
    "soil_moisture",
    "elevation",
    "slope",
    "twi",
    "traffic_speed",
    "free_flow_speed",
    "historical_flood_count",
    "current_flood_depth",
    "flood_status",
)
SPATIAL_FIELDS = ("latitude", "longitude")
SOURCE_FIELDS = SPATIAL_FIELDS + FEATURE_FIELDS
STATIC_FIELDS = frozenset((*SPATIAL_FIELDS, "elevation", "slope", "twi", "free_flow_speed"))
PROVIDERS = frozenset(
    (
        "nasa_gpm",
        "nasa_smap",
        "nasadem",
        "srtm",
        "openstreetmap",
        "traffic_provider",
        "verified_community_report",
        "derived",
        "demo",
    )
)
METHOD_WEIGHTS = {
    "measurement": 1.0,
    "aggregate": 1.0,
    "derived": 1.0,
    "carry_forward": 0.5,
    "imputed": 0.5,
    "simulated": 0.0,
}


class FlagCode(str, Enum):
    MISSING = "missing"
    STALE = "stale"
    REJECTED = "rejected"
    CONFLICT = "conflict"
    CARRIED_FORWARD = "carried_forward"
    IMPUTED = "imputed"
    PROXY = "proxy"
    SIMULATED = "simulated"


class QualityReason(str, Enum):
    MISSING_GPM = "MISSING_GPM"
    MISSING_SMAP = "MISSING_SMAP"
    MISSING_TRAFFIC = "MISSING_TRAFFIC"
    MISSING_FEATURE = "MISSING_FEATURE"
    STALE_SOURCE = "STALE_SOURCE"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    INTERPOLATED = "INTERPOLATED"
    LOW_SPATIAL_COVERAGE = "LOW_SPATIAL_COVERAGE"
    DEMO_VALUE = "DEMO_VALUE"


REASON_CODES = {
    QualityReason.MISSING_GPM: FlagCode.MISSING,
    QualityReason.MISSING_SMAP: FlagCode.MISSING,
    QualityReason.MISSING_TRAFFIC: FlagCode.MISSING,
    QualityReason.MISSING_FEATURE: FlagCode.MISSING,
    QualityReason.STALE_SOURCE: FlagCode.STALE,
    QualityReason.OUT_OF_RANGE: FlagCode.REJECTED,
    QualityReason.INTERPOLATED: FlagCode.IMPUTED,
    QualityReason.LOW_SPATIAL_COVERAGE: FlagCode.PROXY,
    QualityReason.DEMO_VALUE: FlagCode.SIMULATED,
}
NULL_REASONS = frozenset((FlagCode.MISSING, FlagCode.STALE, FlagCode.REJECTED, FlagCode.CONFLICT))


def quality_score(values, sources):
    """coverage-v0.1; call only after source coverage and eligibility validation."""
    methods = {field: src["method"] for src in sources for field in src["fields"]}
    return round(
        sum(METHOD_WEIGHTS[methods[f]] if values[f] is not None else 0 for f in FEATURE_FIELDS)
        / len(FEATURE_FIELDS),
        4,
    )
