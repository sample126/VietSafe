"""Allowlist-only dataset projection; never runs Forecast or changes Data."""

from collections.abc import Mapping

from ..data_pipeline.features.dataset import ForecastDataset
from .contracts import (
    DataForecastInput, ForecastOutput, ForecastRoadResult, INPUT_SCHEMA,
    SOURCE_SCHEMA, names, require, validate_network_match,
)
from .errors import IntegrationContractError


def build_forecast_input(dataset, sample_index=0):
    """Select a sample by index within ONE dataset, never join separate artifacts by index."""
    if isinstance(dataset, ForecastDataset):
        try:
            dataset = dataset.to_dict()
        except (TypeError, ValueError, OverflowError):
            raise IntegrationContractError("INVALID_CONTRACT", "Dataset serialization failed") from None
    require(isinstance(dataset, Mapping), "dataset", "ForecastDataset or serialized dict required")
    require(dataset.get("schema") == SOURCE_SCHEMA, "source_schema", "Unsupported dataset schema")
    samples = dataset.get("samples")
    require(isinstance(samples, (list, tuple)), "samples")
    require(type(sample_index) is int and 0 <= sample_index < len(samples), "sample_index",
            "Inference sample unavailable", "MISSING_INPUT")
    sample = samples[sample_index]
    require(isinstance(sample, Mapping), "sample")
    # Never copy targets, label metadata, arbitrary metadata or the entire sample.
    payload = {"schema": INPUT_SCHEMA, "source_schema": dataset["schema"],
               "contract_status": "draft", "mode": "artifact"}
    dataset_fields = (
        "feature_version", "network_version", "graph_checksum", "graph", "road_ids",
        "feature_names", "feature_units", "timestep_minutes", "lookback_steps", "horizon_steps",
    )
    sample_fields = ("issue_time", "history_timestamps", "X", "X_mask", "feature_as_of",
                     "feature_row_checksums")
    for source, fields in ((dataset, dataset_fields), (sample, sample_fields)):
        for field in fields:
            require(field in source, field, "Required source field missing")
            payload[field] = source[field]
    steps = payload["horizon_steps"]
    require(type(steps) is int and steps in (1, 2), "horizon_steps",
            "Only +30/+60 supported", "UNSUPPORTED_HORIZON")
    payload["horizon_minutes"] = steps * 30
    return DataForecastInput(payload)


def normalize_forecast_output(metadata, road_results, *, network_version, road_ids):
    """Wrap CALLER results and add UNAVAILABLE status for omissions, never predictions.

    Scope order is explicit. Metric values and publication time are never generated.
    """
    require(isinstance(metadata, Mapping), "metadata")
    require("roads" not in metadata and "coverage" not in metadata, "metadata")
    validate_network_match(network_version, metadata.get("network_version"))
    scope = names(road_ids, "scope", allow_empty=True)
    require(isinstance(road_results, (list, tuple)), "roads")
    rows = {}
    for raw in road_results:
        row = (raw if isinstance(raw, ForecastRoadResult) else ForecastRoadResult(raw)).to_dict()
        rid = row["road_id"]
        require(rid in scope, "road_id", "Unknown road", "UNKNOWN_ROAD")
        require(rid not in rows, "road_id", "Duplicate road")
        rows[rid] = row
    ordered = [rows.get(rid, {"road_id": rid, "status": "UNAVAILABLE",
                             "reason_code": "UNAVAILABLE"}) for rid in scope]
    counts = {status: sum(row["status"] == status for row in ordered)
              for status in ("OK", "MISSING_INPUT", "UNAVAILABLE", "STALE")}
    output = ForecastOutput(dict(metadata, roads=ordered, coverage=dict(
        total=len(ordered), predicted=counts["OK"], missing_input=counts["MISSING_INPUT"],
        unavailable=counts["UNAVAILABLE"], stale=counts["STALE"])))
    output.validate_scope(network_version, scope)
    return output
