"""Lightweight v0.1.0 models, without ORM, coercion or runtime API integration."""

import json
import math
from dataclasses import asdict, dataclass

from .exceptions import DataValidationError, ValidationIssue
from .quality import REASON_CODES, QualityReason


def reject_nonfinite(value, path="observation"):
    issues = []
    if isinstance(value, float) and not math.isfinite(value):
        issues.append(ValidationIssue(path, "NON_FINITE", "NaN and Infinity are forbidden"))
    elif isinstance(value, dict):
        for key, item in value.items():
            issues.extend(reject_nonfinite(item, f"{path}.{key}"))
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            issues.extend(reject_nonfinite(item, f"{path}[{index}]"))
    return issues


@dataclass(frozen=True)
class QualityFlag:
    field: str
    code: str
    detail: str

    @classmethod
    def for_reason(cls, field, reason: QualityReason, detail):
        return cls(field, REASON_CODES[reason].value, f"{reason.value}: {detail}")


@dataclass(frozen=True)
class SourceMetadata:
    fields: tuple[str, ...]
    provider: str
    product: str
    version: str
    record_ref: str
    observed_at: str
    available_at: str
    valid_until: str | None
    method: str

    def __post_init__(self):
        if not isinstance(self.fields, (tuple, list)):
            raise DataValidationError(
                [ValidationIssue("source.fields", "INVALID_TYPE", "Expected feature sequence")]
            )
        object.__setattr__(self, "fields", tuple(self.fields))


@dataclass(frozen=True)
class RoadObservation:
    schema_version: str
    dataset_version: str
    network_version: str
    road_id: str
    timestamp: str
    as_of: str
    data_mode: str
    latitude: float
    longitude: float
    rainfall_30m: float | None
    rainfall_1h: float | None
    rainfall_3h: float | None
    soil_moisture: float | None
    elevation: float | None
    slope: float | None
    twi: float | None
    traffic_speed: float | None
    free_flow_speed: float | None
    historical_flood_count: int | None
    current_flood_depth: float | None
    flood_status: bool | None
    source: tuple[SourceMetadata, ...]
    quality_score: float
    quality_flags: tuple[QualityFlag, ...]

    def __post_init__(self):
        for name, model_type in (("source", SourceMetadata), ("quality_flags", QualityFlag)):
            value = getattr(self, name)
            if not isinstance(value, (tuple, list)) or any(
                not isinstance(item, model_type) for item in value
            ):
                raise DataValidationError(
                    [
                        ValidationIssue(
                            name, "INVALID_TYPE", f"Expected {model_type.__name__} sequence"
                        )
                    ]
                )
            object.__setattr__(self, name, tuple(value))
        issues = reject_nonfinite(asdict(self))
        if issues:
            raise DataValidationError(issues)

    def to_dict(self):
        result = asdict(self)
        result["source"] = [dict(asdict(s), fields=list(s.fields)) for s in self.source]
        result["quality_flags"] = [asdict(f) for f in self.quality_flags]
        return result

    def to_json(self):
        # Boundary checking is independent from registry/provenance checks in validation.
        from .validation import validate_structure

        payload = self.to_dict()
        issues = validate_structure(payload)
        if issues:
            raise DataValidationError(issues)
        return json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)

    @classmethod
    def from_dict(cls, payload):
        from .validation import validate_structure

        issues = validate_structure(payload)
        if issues:
            raise DataValidationError(issues)
        fields = dict(payload)
        fields["source"] = tuple(
            SourceMetadata(**dict(s, fields=tuple(s["fields"]))) for s in payload["source"]
        )
        fields["quality_flags"] = tuple(QualityFlag(**flag) for flag in payload["quality_flags"])
        return cls(**fields)

    @classmethod
    def from_json(cls, text):
        try:

            def reject_constant(value):
                raise ValueError(f"Invalid JSON constant: {value}")

            def unique_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError(f"Duplicate JSON key: {key}")
                    result[key] = value
                return result

            payload = json.loads(
                text, parse_constant=reject_constant, object_pairs_hook=unique_object
            )
        except (ValueError, TypeError) as error:
            raise DataValidationError(
                [ValidationIssue("observation", "INVALID_JSON", str(error))]
            ) from error
        return cls.from_dict(payload)
