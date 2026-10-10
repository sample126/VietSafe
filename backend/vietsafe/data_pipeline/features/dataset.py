"""Model-neutral L x N x F forecast samples; labels are never input features."""

import json
from dataclasses import asdict, dataclass

from ..processing.temporal_alignment import canonical_timestamp
from ..registry import canonical_bytes, checksum
from .engineering import FEATURE_NAMES, FEATURE_UNITS, FEATURE_VERSION, RoadFeatureRow, dt, require, shift
from .graph import GraphTopology, build_graph
from .labels import RoadTarget

DATASET_SCHEMA = 'vietsafe.forecast-dataset.v1'


@dataclass(frozen=True)
class ForecastSample:
    issue_time: str
    target_time: str
    history_timestamps: tuple
    X: tuple
    X_mask: tuple
    y: tuple
    y_mask: tuple
    y_missing_reasons: tuple
    label_available_at: tuple
    label_checksums: tuple
    event_ids: tuple
    feature_as_of: tuple
    feature_row_checksums: tuple

    def to_dict(self):
        return json.loads(canonical_bytes(asdict(self)))

    def checksum(self):
        return checksum(self.to_dict())


@dataclass(frozen=True)
class ForecastDataset:
    graph: GraphTopology
    lookback_steps: int
    horizon_steps: int
    target_name: str
    target_units: str | None
    require_targets: bool
    samples: tuple
    _excluded_json: str

    def __post_init__(self):
        object.__setattr__(self, 'samples', tuple(sorted(
            self.samples, key=lambda sample: (dt(sample.issue_time), dt(sample.target_time), sample.checksum()))))

    def to_dict(self):
        return dict(schema=DATASET_SCHEMA, feature_version=FEATURE_VERSION,
                    network_version=self.graph.network_version, graph_checksum=self.graph.checksum(),
                    graph=self.graph.to_dict(), timestep_minutes=30,
                    feature_names=list(FEATURE_NAMES), feature_units=list(FEATURE_UNITS),
                    road_ids=list(self.graph.road_ids), lookback_steps=self.lookback_steps,
                    horizon_steps=self.horizon_steps, target_name=self.target_name,
                    target_units=self.target_units, require_targets=self.require_targets,
                    samples=[sample.to_dict() for sample in self.samples],
                    excluded=json.loads(self._excluded_json),
                    missing_policy='null-with-mask-no-fill',
                    snapshot_policy='latest-feature-as-of-not-after-issue-time-v1')

    def to_json(self):
        return canonical_bytes(self.to_dict()).decode('utf-8')

    def checksum(self):
        return checksum(self.to_dict())


def build_dataset(registry, rows, labels=(), *, target_name, lookback_steps=6,
                  horizon_steps=1, issue_times=None, require_targets=True):
    require(type(lookback_steps) is int and lookback_steps > 0, 'Positive integer lookback required')
    require(type(horizon_steps) is int and horizon_steps > 0, 'Positive integer horizon required')
    require(type(require_targets) is bool, 'require_targets must be bool')
    require(isinstance(target_name, str) and target_name.strip(), 'target_name required')
    graph = build_graph(registry)
    snapshots = {}
    for row in rows:
        require(isinstance(row, RoadFeatureRow), 'Expected RoadFeatureRow')
        require(row.network_version == registry.network_version and registry.get(row.road_id) is not None,
                'Feature road/network mismatch')
        require(row.provenance.get('registry_checksum') == registry.checksum, 'Feature registry checksum mismatch')
        key = (row.timestamp, row.road_id, row.as_of)
        if key in snapshots:
            require(snapshots[key].checksum() == row.checksum(), 'Conflicting feature snapshot')
        snapshots[key] = row
    by_row = {}
    for (stamp, road, _), row in snapshots.items():
        by_row.setdefault((stamp, road), []).append(row)
    for records in by_row.values():
        records.sort(key=lambda row: dt(row.as_of))
    targets = {}
    units = set()
    for label in labels:
        require(isinstance(label, RoadTarget), 'Expected RoadTarget')
        require(registry.get(label.road_id) is not None, 'Unknown target road')
        if label.target_name == target_name:
            units.add(label.units)
            targets.setdefault((label.observed_at, label.road_id), {})[label.checksum()] = label
    require(len(units) <= 1, 'Mixed target units; no implicit label conversion')
    issues = sorted({canonical_timestamp(time) for time in issue_times}) if issue_times is not None else sorted(
        {stamp for stamp, _, _ in snapshots})
    samples, excluded = [], []
    for issue in issues:
        history = tuple(shift(issue, offset) for offset in range(1 - lookback_steps, 1))
        target_time = shift(issue, horizon_steps)
        chosen, unavailable = [], []
        for stamp in history:
            step = []
            for road in graph.road_ids:
                candidates = [row for row in by_row.get((stamp, road), ()) if dt(row.as_of) <= dt(issue)]
                if not candidates:
                    unavailable.append(dict(timestamp=stamp, road_id=road, reason='NO_ELIGIBLE_HISTORY_ROW'))
                else:
                    step.append(candidates[-1])
            chosen.append(tuple(step))
        if unavailable:
            excluded.append(dict(issue_time=issue, target_time=target_time, reason='INSUFFICIENT_HISTORY',
                                 details=unavailable))
            continue
        y, reasons, availability, label_refs, events = [], [], [], [], set()
        for road in graph.road_ids:
            variants = targets.get((target_time, road), {})
            if len(variants) != 1:
                y.append(None)
                reasons.append('TARGET_CONFLICT' if variants else 'MISSING_TARGET')
                availability.append(None)
                label_refs.append(tuple(sorted(variants)))
            else:
                label = next(iter(variants.values()))
                y.append(label.value)
                reasons.append(None if label.value is not None else 'NULL_TARGET')
                availability.append(label.available_at)
                label_refs.append((label.checksum(),))
                if label.event_id:
                    events.add(label.event_id)
            # Even conflicted targets retain event membership for split grouping.
            events.update(label.event_id for label in variants.values() if label.event_id)
        if require_targets and any(value is None for value in y):
            excluded.append(dict(issue_time=issue, target_time=target_time, reason='TARGETS_REQUIRED',
                                 details=[dict(road_id=road, reason=reason)
                                          for road, reason in zip(graph.road_ids, reasons) if reason]))
            continue
        samples.append(ForecastSample(
            issue, target_time, history,
            tuple(tuple(row.values for row in step) for step in chosen),
            tuple(tuple(row.mask for row in step) for step in chosen),
            tuple(y), tuple(value is not None for value in y), tuple(reasons), tuple(availability),
            tuple(label_refs), tuple(sorted(events)),
            tuple(tuple(row.as_of for row in step) for step in chosen),
            tuple(tuple(row.checksum() for row in step) for step in chosen),
        ))
    return ForecastDataset(graph, lookback_steps, horizon_steps, target_name,
                           next(iter(units)) if units else None, require_targets,
                           tuple(samples), canonical_bytes(excluded).decode('utf-8'))
