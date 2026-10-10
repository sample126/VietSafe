"""Chronological target-time blocks, optional event preservation and boundary purge."""

import json
import math
from dataclasses import dataclass

from ..registry import canonical_bytes, checksum, finite_number
from .dataset import ForecastDataset
from .engineering import dt, require


@dataclass(frozen=True)
class DatasetSplit:
    _json: str

    def to_dict(self):
        return json.loads(self._json)

    def checksum(self):
        return checksum(self.to_dict())


def chronological_split(dataset, *, train_ratio=.7, validation_ratio=.15, test_ratio=.15,
                        preserve_events=True, purge_overlap=True):
    """Target-time ties/event spans never cross boundaries. Ratios are approximate.

    Purge later-partition samples whose history touches any earlier target time.
    Event spans crossing many dates may force empty partitions; never randomize.
    """
    require(isinstance(dataset, ForecastDataset), 'Expected ForecastDataset')
    ratios = (train_ratio, validation_ratio, test_ratio)
    require(all(finite_number(value) and 0 <= value <= 1 for value in ratios) and
            math.isclose(sum(ratios), 1, rel_tol=0, abs_tol=1e-9), 'Ratios must sum to 1')
    require(type(preserve_events) is bool and type(purge_overlap) is bool, 'Split options must be bool')
    unique = {sample.checksum(): sample for sample in dataset.samples}
    samples = sorted(unique.values(), key=lambda sample: (dt(sample.target_time), dt(sample.issue_time), sample.checksum()))
    identities = [(sample.issue_time, sample.target_time) for sample in samples]
    require(len(identities) == len(set(identities)), 'Conflicting duplicate sample identity')
    count = len(samples)
    boundaries = {0, count}
    boundaries.update(i for i in range(1, count) if samples[i-1].target_time != samples[i].target_time)
    if preserve_events:
        positions = {}
        for i, sample in enumerate(samples):
            for event in sample.event_ids:
                positions.setdefault(event, []).append(i)
        for indexes in positions.values():
            boundaries = {cut for cut in boundaries if not min(indexes) < cut <= max(indexes)}
    first = min(boundaries, key=lambda cut: (abs(cut - train_ratio * count), cut))
    second = min((cut for cut in boundaries if cut >= first),
                 key=lambda cut: (abs(cut - (train_ratio + validation_ratio) * count), cut))
    parts = [samples[:first], samples[first:second], samples[second:]]
    kept, purged, prior_target = [], [], None
    for name, part in zip(('train', 'validation', 'test'), parts):
        retained = []
        for sample in part:
            if purge_overlap and prior_target is not None and dt(sample.history_timestamps[0]) <= prior_target:
                purged.append(dict(partition=name, sample_checksum=sample.checksum(), reason='HISTORY_OVERLAPS_PRIOR_TARGET'))
            else:
                retained.append(sample)
        kept.append(retained)
        if part:
            # Even purged samples reserve the original chronological block boundary.
            prior_target = max(dt(sample.target_time) for sample in part)
    result = dict(split_version='chronological-target-blocks-v1', dataset_checksum=dataset.checksum(),
                  requested_ratios=dict(zip(('train','validation','test'),ratios)),
                  preserve_events=preserve_events, purge_overlap=purge_overlap,
                  boundary_policy='target-ties-and-event-spans-atomic; later-history-after-prior-target',
                  purged=purged)
    for name, part in zip(('train', 'validation', 'test'), kept):
        result[name] = [dict(sample_checksum=sample.checksum(), issue_time=sample.issue_time,
                            target_time=sample.target_time, event_ids=list(sample.event_ids)) for sample in part]
    return DatasetSplit(canonical_bytes(result).decode('utf-8'))
