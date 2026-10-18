"""Draft immutable JSON contracts. No model, provider registration or runtime IO."""

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from ..data_pipeline.features.engineering import FEATURE_NAMES, FEATURE_UNITS, FEATURE_VERSION
from ..data_pipeline.features.graph import GRAPH_VERSION
from ..data_pipeline.registry import canonical_bytes, checksum
from .errors import IntegrationContractError

INPUT_SCHEMA = "vietsafe.data-forecast-input.v1"
SOURCE_SCHEMA = "vietsafe.forecast-dataset.v1"
OUTPUT_SCHEMA = "vietsafe.forecast-output.v1"
STATUSES = ("OK", "MISSING_INPUT", "UNAVAILABLE", "STALE")
METRICS = ("flood_risk", "speed_km_h", "risk", "label")
INPUT_FIELDS = frozenset((
    "schema source_schema contract_status mode feature_version network_version "
    "graph_checksum graph road_ids feature_names feature_units timestep_minutes "
    "lookback_steps issue_time history_timestamps horizon_steps horizon_minutes "
    "X X_mask feature_as_of feature_row_checksums"
).split())
GRAPH_FIELDS = frozenset((
    "graph_version network_version registry_checksum road_ids directed_edges adjacency policy"
).split())
OUTPUT_FIELDS = frozenset((
    "schema contract_status mode network_version model_version issue_time issued_at "
    "horizon_minutes forecast_time output_fields roads coverage"
).split())


def require(condition, path, message="Invalid contract", code="INVALID_CONTRACT"):
    if not condition:
        raise IntegrationContractError(code, message, path)


def text(value, path):
    require(isinstance(value, str) and bool(value.strip()), path, "Nonempty string required")


def sequence(value, path):
    require(isinstance(value, (list, tuple)), path, "Array required")
    return value


def integer(value, path, minimum=0):
    require(type(value) is int and value >= minimum, path, "Integer out of range")


def keys(value, required, path, optional=()):
    require(isinstance(value, Mapping), path, "Object required")
    require(required <= value.keys() and value.keys() <= required | set(optional), path,
            "Missing or unsupported fields")


def names(value, path, allow_empty=False):
    sequence(value, path)
    require(allow_empty or len(value) > 0, path, "Nonempty array required")
    for item in value:
        text(item, path)
    require(len(set(value)) == len(value), path, "Duplicate names or IDs")
    return value


def finite(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def timestamp(value, path, bin_end=False):
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value),
            path, "Canonical UTC seconds with Z required")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise IntegrationContractError("INVALID_CONTRACT", "Invalid UTC timestamp", path) from None
    if bin_end:
        require(parsed.minute in (0, 30) and parsed.second == 0, path, "30-minute bin required")
    return parsed


def digest(value, path):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value), path,
            "SHA-256 lowercase hex required")


def validate_network_match(expected, actual):
    text(expected, "network_version")
    text(actual, "network_version")
    require(expected == actual, "network_version", "Network versions differ",
            "NETWORK_VERSION_MISMATCH")


def matrix(value, rows, cols, path):
    sequence(value, path)
    require(len(value) == rows, path, "Wrong row count")
    for row in value:
        sequence(row, path)
        require(len(row) == cols, path, "Wrong column count")


def validate_graph(graph, road_ids, network):
    keys(graph, GRAPH_FIELDS, "graph")
    require(graph["graph_version"] == GRAPH_VERSION, "graph.graph_version")
    validate_network_match(network, graph["network_version"])
    require(graph["road_ids"] == road_ids, "graph.road_ids", "Graph road order differs")
    digest(graph["registry_checksum"], "graph.registry_checksum")
    require(graph["policy"] == "raw-travel-continuity-no-self-loops-uturns-allowed-v1", "graph.policy")
    n = len(road_ids)
    matrix(graph["adjacency"], n, n, "graph.adjacency")
    expected = []
    for i, row in enumerate(graph["adjacency"]):
        for j, value in enumerate(row):
            require(type(value) is int and value in (0, 1) and (i != j or value == 0),
                    "graph.adjacency", "Raw binary adjacency without self loops required")
            if value:
                expected.append([i, j])
    sequence(graph["directed_edges"], "graph.directed_edges")
    for edge in graph["directed_edges"]:
        sequence(edge, "graph.directed_edges")
        require(len(edge) == 2 and all(type(i) is int and 0 <= i < n for i in edge),
                "graph.directed_edges", "Integer node indices required")
    require(graph["directed_edges"] == expected, "graph.directed_edges", "Edges disagree with adjacency")


def validate_input(p):
    keys(p, INPUT_FIELDS, "input")
    for field, value in (("schema", INPUT_SCHEMA), ("source_schema", SOURCE_SCHEMA),
                         ("contract_status", "draft"), ("mode", "artifact")):
        require(p[field] == value, field)
    require(p["feature_version"] == FEATURE_VERSION, "feature_version",
            "Unsupported features", "FEATURE_SCHEMA_MISMATCH")
    names(p["feature_names"], "feature_names")
    require(p["feature_names"] == list(FEATURE_NAMES) and p["feature_units"] == list(FEATURE_UNITS),
            "feature_names", "Feature order or units differ", "FEATURE_SCHEMA_MISMATCH")
    roads = names(p["road_ids"], "road_ids")
    text(p["network_version"], "network_version")
    validate_graph(p["graph"], roads, p["network_version"])
    digest(p["graph_checksum"], "graph_checksum")
    require(p["graph_checksum"] == checksum(p["graph"]), "graph_checksum", "Graph checksum differs")
    require(type(p["timestep_minutes"]) is int and p["timestep_minutes"] == 30, "timestep_minutes")
    require(type(p["horizon_steps"]) is int and p["horizon_steps"] in (1, 2)
            and type(p["horizon_minutes"]) is int
            and p["horizon_minutes"] == p["horizon_steps"] * 30,
            "horizon_minutes", "Only +30/+60 supported", "UNSUPPORTED_HORIZON")
    integer(p["lookback_steps"], "lookback_steps", 1)
    l, n, f = p["lookback_steps"], len(roads), len(FEATURE_NAMES)
    issue = timestamp(p["issue_time"], "issue_time", True)
    history = sequence(p["history_timestamps"], "history_timestamps")
    require(len(history) == l, "history_timestamps", "Wrong history length")
    for i, value in enumerate(history):
        parsed = timestamp(value, "history_timestamps", True)
        require(issue - parsed == timedelta(minutes=30 * (l - 1 - i)),
                "history_timestamps", "History must be continuous and end at issue_time")
    for field in ("X", "X_mask"):
        sequence(p[field], field)
        require(len(p[field]) == l, field, "Wrong lookback dimension")
        for step in p[field]:
            matrix(step, n, f, field)
    for step, masks in zip(p["X"], p["X_mask"]):
        for row, mask in zip(step, masks):
            for value, valid in zip(row, mask):
                require(type(valid) is bool, "X_mask", "Boolean mask required")
                require(value is None or finite(value), "X", "Finite numeric or null required")
                require(valid == (value is not None), "X_mask", "Null/mask mismatch")
    for field in ("feature_as_of", "feature_row_checksums"):
        matrix(p[field], l, n, field)
        for row in p[field]:
            for value in row:
                if field == "feature_as_of":
                    require(timestamp(value, field) <= issue, field, "Feature snapshot after issue time")
                else:
                    digest(value, field)


def validate_road(p):
    keys(p, {"road_id", "status"}, "road", (*METRICS, "reason_code"))
    text(p["road_id"], "road_id")
    require(p["status"] in STATUSES, "status", "Unsupported road status")
    if p["status"] != "OK":
        text(p.get("reason_code"), "reason_code")
    elif "reason_code" in p:
        text(p["reason_code"], "reason_code")
    for field in METRICS:
        if field in p and p[field] is not None:
            if field == "label":
                text(p[field], field)
            else:
                require(finite(p[field]), field, "Finite numeric metric required")


def validate_output(p):
    keys(p, OUTPUT_FIELDS, "output")
    require(p["schema"] == OUTPUT_SCHEMA and p["contract_status"] == "draft", "schema")
    require(p["mode"] in ("demo", "artifact"), "mode")
    for field in ("network_version", "model_version"):
        text(p[field], field)
    h = p["horizon_minutes"]
    allowed = (30, 60) if p["mode"] == "artifact" else (0, 15, 30, 45, 60)
    require(type(h) is int and h in allowed, "horizon_minutes", "Unsupported horizon", "UNSUPPORTED_HORIZON")
    issue = timestamp(p["issue_time"], "issue_time", p["mode"] == "artifact")
    timestamp(p["issued_at"], "issued_at")
    target = timestamp(p["forecast_time"], "forecast_time")
    require(target - issue == timedelta(minutes=h), "forecast_time", "Target must use issue_time")
    fields = names(p["output_fields"], "output_fields")
    require(set(fields) <= set(METRICS), "output_fields", "Unsupported metric")
    sequence(p["roads"], "roads")
    ids, counts = [], dict.fromkeys(STATUSES, 0)
    for road in p["roads"]:
        validate_road(road)
        ids.append(road["road_id"])
        counts[road["status"]] += 1
        require((set(road) & set(METRICS)) <= set(fields), "output_fields", "Undeclared metric")
        if road["status"] == "OK":
            require(all(field in road and road[field] is not None for field in fields),
                    "roads", "OK requires complete declared outputs")
    names(ids, "roads", allow_empty=True)
    expected = dict(total=len(ids), predicted=counts["OK"], missing_input=counts["MISSING_INPUT"],
                    unavailable=counts["UNAVAILABLE"], stale=counts["STALE"])
    keys(p["coverage"], set(expected), "coverage")
    for key, value in p["coverage"].items():
        integer(value, "coverage." + key)
    require(p["coverage"] == expected, "coverage", "Coverage must match actual road statuses")


@dataclass(frozen=True, init=False)
class _Contract:
    """Stores canonical JSON, so caller mutation cannot affect nested fields."""
    _json: str

    def __init__(self, payload):
        try:
            # JSON copy normalizes tuples without exposing caller-owned containers.
            copied = json.loads(canonical_bytes(payload))
        except (TypeError, ValueError, OverflowError, RecursionError):
            raise IntegrationContractError("INVALID_CONTRACT", "Expected finite JSON payload") from None
        self._validate(copied)
        object.__setattr__(self, "_json", canonical_bytes(copied).decode("utf-8"))

    @classmethod
    def from_dict(cls, payload):
        return cls(payload)

    def to_dict(self):
        return json.loads(self._json)

    def to_json(self):
        return self._json

    def checksum(self):
        return hashlib.sha256(self._json.encode("utf-8")).hexdigest()


@dataclass(frozen=True, init=False)
class DataForecastInput(_Contract):
    _validate = staticmethod(validate_input)


@dataclass(frozen=True, init=False)
class ForecastRoadResult(_Contract):
    _validate = staticmethod(validate_road)


@dataclass(frozen=True, init=False)
class ForecastOutput(_Contract):
    _validate = staticmethod(validate_output)

    def validate_scope(self, network_version, road_ids):
        """Require complete status coverage of an explicit prediction scope."""
        validate_network_match(network_version, self.to_dict()["network_version"])
        expected = set(names(road_ids, "scope", allow_empty=True))
        actual = {road["road_id"] for road in self.to_dict()["roads"]}
        require(actual <= expected, "roads", "Output contains unknown road", "UNKNOWN_ROAD")
        require(actual == expected, "roads", "Missing explicit status rows", "MISSING_INPUT")


class ForecastProvider(Protocol):
    """Future artifact interface only; no implementation or registration."""
    def predict(self, request: DataForecastInput) -> ForecastOutput: ...
