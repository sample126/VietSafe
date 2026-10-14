"""Offline v0.1.0 boundary and semantic checks, with structured errors.

This explicitly implements the current contract, not a general JSON Schema engine.
Lineage refs must resolve in the caller's pinned catalog; no network requests occur.
"""

import re
from dataclasses import fields
from datetime import datetime, timezone

from .exceptions import DataValidationError, ValidationIssue
from .models import QualityFlag, RoadObservation, SourceMetadata
from .quality import (
    FEATURE_FIELDS,
    METHOD_WEIGHTS,
    NULL_REASONS,
    PROVIDERS,
    SCHEMA_VERSION,
    SOURCE_FIELDS,
    STATIC_FIELDS,
    FlagCode,
    quality_score,
)
from .registry import ROAD_PATTERN, VERSION_PATTERN, checksum, finite_number

UTC_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def parse_utc(value):
    if not isinstance(value, str) or not UTC_PATTERN.fullmatch(value):
        raise ValueError("Expected canonical UTC YYYY-MM-DDTHH:MM:SSZ, no naive datetime")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def validate_structure(payload):
    issues = []

    def add(field, code, message):
        issues.append(ValidationIssue(field, code, message))

    def shape(value, names, prefix):
        names = set(names)
        if not isinstance(value, dict):
            add(prefix, "INVALID_TYPE", "Expected object")
            return False
        for name in sorted(set(names) - value.keys()):
            add(f"{prefix}.{name}", "REQUIRED_FIELD", "Field must be present, even when null")
        for name in sorted(value.keys() - set(names), key=str):
            add(f"{prefix}.{name}", "UNKNOWN_FIELD", "Field is not part of schema v0.1.0")
        return set(value) == set(names)

    def text(value, prefix, maximum):
        if not isinstance(value, str) or not 1 <= len(value) <= maximum:
            add(prefix, "INVALID_STRING", f"Expected string of length 1..{maximum}")
            return False
        return True

    def timestamp(value, prefix):
        try:
            parse_utc(value)
        except ValueError as error:
            add(prefix, "INVALID_TIMESTAMP", str(error))

    if not shape(payload, (f.name for f in fields(RoadObservation)), "observation"):
        return issues
    for key in ("dataset_version", "network_version"):
        if not isinstance(payload[key], str) or not VERSION_PATTERN.fullmatch(payload[key]):
            add(key, "INVALID_VERSION", "Nonempty portable version required")
    if payload["schema_version"] != SCHEMA_VERSION:
        add("schema_version", "UNSUPPORTED_SCHEMA", "Only v0.1.0 is supported")
    if not isinstance(payload["road_id"], str) or not ROAD_PATTERN.fullmatch(payload["road_id"]):
        add("road_id", "INVALID_ID", "Invalid road ID format")
    if payload["data_mode"] not in ("demo", "observed"):
        add("data_mode", "INVALID_MODE", "Expected demo or observed")
    for name in ("timestamp", "as_of"):
        timestamp(payload[name], name)
    for name in SOURCE_FIELDS + ("quality_score",):
        value = payload[name]
        if value is None and name in FEATURE_FIELDS:
            continue
        if name == "flood_status":
            if type(value) is not bool:
                add(name, "INVALID_TYPE", "Expected boolean or null")
            continue
        if type(value) not in (int, float):
            add(name, "INVALID_TYPE", "Expected number (boolean is not a number)")
        elif not finite_number(value):
            add(name, "NON_FINITE", "NaN, Infinity and unrepresentable numbers are forbidden")
        elif name == "historical_flood_count" and int(value) != value:
            add(name, "INVALID_TYPE", "Expected nonnegative integer")
        elif (
            name
            in (
                "rainfall_30m",
                "rainfall_1h",
                "rainfall_3h",
                "traffic_speed",
                "current_flood_depth",
                "historical_flood_count",
            )
            and value < 0
        ):
            add(name, "NEGATIVE_VALUE", f"{name} must be >= 0")
        elif name == "free_flow_speed" and value <= 0:
            add(name, "OUT_OF_RANGE", "free_flow_speed must be > 0")
        elif name in ("soil_moisture", "quality_score") and not 0 <= value <= 1:
            add(name, "OUT_OF_RANGE", f"{name} must be in [0,1]")
        elif name == "slope" and not 0 <= value < 90:
            add(name, "OUT_OF_RANGE", "slope must be in [0,90) degrees")
        elif name == "latitude" and not -90 <= value <= 90:
            add(name, "OUT_OF_RANGE", "latitude must be in [-90,90]")
        elif name == "longitude" and not -180 <= value <= 180:
            add(name, "OUT_OF_RANGE", "longitude must be in [-180,180]")
    sources = payload["source"]
    if not isinstance(sources, list) or not sources:
        add("source", "INVALID_TYPE", "Expected nonempty source array")
        sources = []
    for index, src in enumerate(sources):
        prefix = f"source[{index}]"
        if not shape(src, (f.name for f in fields(SourceMetadata)), prefix):
            continue
        if (
            not isinstance(src["fields"], list)
            or not src["fields"]
            or any(not isinstance(f, str) or f not in SOURCE_FIELDS for f in src["fields"])
        ):
            add(prefix + ".fields", "INVALID_FIELDS", "Expected nonempty array of feature names")
        elif len(src["fields"]) != len(set(src["fields"])):
            add(prefix + ".fields", "DUPLICATE_FIELD", "Duplicate source feature")
        if not isinstance(src["provider"], str) or src["provider"] not in PROVIDERS:
            add(prefix + ".provider", "INVALID_PROVIDER", "Unknown provider namespace")
        if not isinstance(src["method"], str) or src["method"] not in METHOD_WEIGHTS:
            add(prefix + ".method", "INVALID_METHOD", "Unknown processing method")
        for name, limit in (("product", 256), ("version", 128), ("record_ref", 2048)):
            text(src[name], prefix + "." + name, limit)
        for name in ("observed_at", "available_at"):
            timestamp(src[name], prefix + "." + name)
        if src["valid_until"] is not None:
            timestamp(src["valid_until"], prefix + ".valid_until")
    flags = payload["quality_flags"]
    if not isinstance(flags, list):
        add("quality_flags", "INVALID_TYPE", "Expected array")
        flags = []
    for index, flag in enumerate(flags):
        prefix = f"quality_flags[{index}]"
        if not shape(flag, (f.name for f in fields(QualityFlag)), prefix):
            continue
        if flag in flags[:index]:
            add(prefix, "DUPLICATE_FLAG", "Duplicate flag")
        if not isinstance(flag["field"], str) or flag["field"] not in SOURCE_FIELDS:
            add(prefix + ".field", "INVALID_FIELD", "Unknown feature")
        if flag["code"] not in tuple(c.value for c in FlagCode):
            add(prefix + ".code", "INVALID_FLAG", "Unknown v0.1.0 flag code")
        text(flag["detail"], prefix + ".detail", 512)
    return issues


def validate_observation(observation, registry, *, source_catalog=None):
    """Return all safely checkable errors; malformed structure stops semantic checks."""
    payload = observation.to_dict() if isinstance(observation, RoadObservation) else observation
    issues = validate_structure(payload)
    if issues:
        return issues

    def add(field, code, message):
        issues.append(ValidationIssue(field, code, message))

    t, cutoff = parse_utc(payload["timestamp"]), parse_utc(payload["as_of"])
    if t.minute not in (0, 30) or t.second:
        add(
            "timestamp",
            "OFF_GRID",
            "v0.1.0 requires a 30-minute grid; other timesteps need a new approved contract",
        )
    if cutoff < t:
        add("as_of", "AS_OF_BEFORE_TIMESTAMP", "as_of must be >= timestamp")
    road = registry.get(payload["road_id"])
    if road is None:
        add("road_id", "UNKNOWN_ROAD", "Road is not in registry")
    if payload["network_version"] != registry.network_version:
        add("network_version", "NETWORK_MISMATCH", "Observation and registry versions differ")
    if road:
        point = road.representative_point()
        for name, expected in zip(("latitude", "longitude"), point, strict=True):
            if abs(payload[name] - expected) > 1e-6:
                add(name, "SPATIAL_MISMATCH", "Point differs from registry length midpoint")
        if payload["data_mode"] == "observed" and road.source_type == "demo":
            add(
                "data_mode",
                "DEMO_REGISTRY",
                "Observed releases cannot claim a demo registry is real",
            )
    rain = [
        payload[f] for f in ("rainfall_30m", "rainfall_1h", "rainfall_3h") if payload[f] is not None
    ]
    if rain != sorted(rain):
        add(
            "rainfall_30m",
            "RAINFALL_ORDER",
            "Known accumulations must be nondecreasing with window length",
        )
    depth = payload["current_flood_depth"]
    if depth is not None and payload["flood_status"] is not (depth > 0):
        add(
            "flood_status",
            "FLOOD_INCONSISTENT",
            "Positive depth requires true; zero depth requires false",
        )
    coverage = {}
    for index, src in enumerate(payload["source"]):
        prefix = f"source[{index}]"
        observed, available = parse_utc(src["observed_at"]), parse_utc(src["available_at"])
        if observed > t:
            add(prefix + ".observed_at", "FUTURE_OBSERVATION", "Observation time exceeds timestamp")
        if available < observed or available > cutoff:
            add(
                prefix + ".available_at",
                "SOURCE_NOT_AVAILABLE",
                "Require observed_at <= available_at <= as_of",
            )
        if src["valid_until"] is not None and parse_utc(src["valid_until"]) <= t:
            add(prefix + ".valid_until", "STALE_SOURCE", "Source expired at observation timestamp")
        if src["valid_until"] is None and any(f not in STATIC_FIELDS for f in src["fields"]):
            add(
                prefix + ".valid_until",
                "TTL_REQUIRED",
                "Dynamic features require explicit valid_until",
            )
        if src["version"].lower() == "latest":
            add(prefix + ".version", "UNPINNED_SOURCE", "Pin a source/recipe version")
        if payload["data_mode"] == "demo" and (
            src["provider"] != "demo" or src["method"] != "simulated"
        ):
            add(prefix, "DEMO_SOURCE_REQUIRED", "Demo values must use demo/simulated provenance")
        if payload["data_mode"] == "observed" and (
            src["provider"] == "demo" or src["method"] == "simulated"
        ):
            add(prefix, "SIMULATED_OBSERVED", "Observed mode forbids simulated inputs")
        ref = (source_catalog or {}).get(src["record_ref"])
        if not isinstance(ref, dict):
            add(
                prefix + ".record_ref",
                "UNRESOLVED_SOURCE",
                "Source ref must resolve in the pinned offline catalog",
            )
        else:
            for name in (
                "provider",
                "product",
                "version",
                "method",
                "observed_at",
                "available_at",
                "valid_until",
            ):
                if ref.get(name) != src[name]:
                    add(
                        prefix + "." + name,
                        "LINEAGE_MISMATCH",
                        "Source metadata differs from pinned catalog",
                    )
            catalog_fields = ref.get("fields")
            if (
                not isinstance(catalog_fields, list)
                or any(not isinstance(f, str) for f in catalog_fields)
                or set(catalog_fields) != set(src["fields"])
            ):
                add(prefix + ".fields", "LINEAGE_MISMATCH", "Catalog field coverage differs")
            digest = ref.get("checksum")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                add(
                    prefix + ".record_ref",
                    "CHECKSUM_REQUIRED",
                    "Catalog requires a SHA-256 input checksum",
                )
            raw_input = ref.get("input")
            if not isinstance(raw_input, dict):
                add(
                    prefix + ".record_ref",
                    "LINEAGE_INPUT_REQUIRED",
                    "Catalog must retain the input recipe/value payload",
                )
            else:
                try:
                    digest_matches = checksum(raw_input) == digest
                except (ValueError, TypeError, OverflowError):
                    digest_matches = False
                if not digest_matches:
                    add(
                        prefix + ".record_ref", "CHECKSUM_MISMATCH", "Catalog input content changed"
                    )
                values = raw_input.get("values", {})
                if not isinstance(values, dict) or any(
                    values.get(f) != payload[f] for f in src["fields"]
                ):
                    add(
                        prefix + ".record_ref",
                        "LINEAGE_VALUE_MISMATCH",
                        "Input lineage does not support these values",
                    )
                if raw_input.get("registry_checksum") != registry.checksum:
                    add(
                        prefix + ".record_ref",
                        "LINEAGE_NETWORK_MISMATCH",
                        "Lineage references another registry",
                    )
        for field in src["fields"]:
            if field in coverage:
                add(field, "DUPLICATE_SOURCE", "Feature has more than one provenance entry")
            coverage[field] = src
            if payload[field] is None:
                add(field, "NULL_WITH_SOURCE", "Null feature cannot claim eligible provenance")
    flags = payload["quality_flags"]
    for field in SOURCE_FIELDS:
        reasons = {f["code"] for f in flags if f["field"] == field}
        if payload[field] is None:
            if not reasons.intersection(NULL_REASONS):
                add(
                    field,
                    "MISSING_REASON",
                    "Null feature needs missing/stale/rejected/conflict flag",
                )
        elif field not in coverage:
            add(field, "MISSING_SOURCE", "Non-null value needs provenance")
        else:
            if reasons.intersection(NULL_REASONS):
                add(field, "FLAG_VALUE_CONFLICT", "Invalid/missing value must be null")
            method = coverage[field]["method"]
            required = {
                "simulated": FlagCode.SIMULATED,
                "carry_forward": FlagCode.CARRIED_FORWARD,
                "imputed": FlagCode.IMPUTED,
            }.get(method)
            if required is not None and required not in reasons:
                add(
                    field, "METHOD_FLAG_REQUIRED", f"Method {method} requires {required.value} flag"
                )
    if all(payload[f] is None or f in coverage for f in FEATURE_FIELDS):
        expected_score = quality_score(payload, payload["source"])
        if abs(payload["quality_score"] - expected_score) > 1e-8:
            add(
                "quality_score",
                "QUALITY_SCORE_MISMATCH",
                f"coverage-v0.1 requires {expected_score}",
            )
    return issues


def validate_dataset(observations, registry, *, source_catalog=None):
    issues, keys, versions, modes = [], set(), set(), set()
    for index, observation in enumerate(observations):
        errors = validate_observation(observation, registry, source_catalog=source_catalog)
        issues.extend(
            ValidationIssue(f"observations[{index}].{e.field}", e.code, e.message) for e in errors
        )
        payload = observation.to_dict() if isinstance(observation, RoadObservation) else observation
        if validate_structure(payload):
            continue
        key = (payload["road_id"], payload["timestamp"])
        if key in keys:
            issues.append(
                ValidationIssue(f"observations[{index}]", "DUPLICATE_OBSERVATION", str(key))
            )
        keys.add(key)
        versions.add(payload["dataset_version"])
        modes.add(payload["data_mode"])
    if not keys:
        issues.append(
            ValidationIssue("observations", "EMPTY_DATASET", "Release must contain records")
        )
    if len(versions) > 1 or len(modes) > 1:
        issues.append(
            ValidationIssue(
                "observations", "MIXED_RELEASE", "One dataset_version/data_mode per release"
            )
        )
    return issues


def require_valid(observations, registry, *, source_catalog=None):
    issues = validate_dataset(observations, registry, source_catalog=source_catalog)
    if issues:
        raise DataValidationError(issues)
