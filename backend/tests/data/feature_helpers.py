"""Synthetic-only fixtures for feature/dataset tests."""

import json
from functools import lru_cache
from pathlib import Path

from vietsafe.data_pipeline.features.engineering import build_features
from vietsafe.data_pipeline.features.dataset import build_dataset
from vietsafe.data_pipeline.features.labels import RoadTarget
from vietsafe.data_pipeline.registry import RoadRegistry,RoadSegment

ROOT = Path(__file__).resolve().parents[3] / 'data/fixtures'
NOTICE = 'SYNTHETIC TEST FIXTURE — NOT PRODUCTION FLOOD GROUND TRUTH'


def fixture():
    source = json.loads((ROOT/'features/aligned-series.json').read_text(encoding='utf-8'))
    raw = source['registry']
    registry = RoadRegistry(raw['network_version'], [RoadSegment(**road) for road in raw['roads']])
    targets = json.loads((ROOT/'features/labels.json').read_text(encoding='utf-8'))
    assert source['fixture_notice'] == targets['fixture_notice'] == NOTICE
    return registry, source['alignment'], tuple(RoadTarget(**label) for label in targets['labels'])


@lru_cache(maxsize=1)
def feature_rows():
    registry, aligned, _ = fixture()
    result = []
    for time in sorted({record['timestamp'] for record in aligned['dynamic']}):
        result.extend(row for row in build_features(registry, aligned, as_of=time) if row.timestamp == time)
    return tuple(result)


def dataset(**options):
    registry, _, labels = fixture()
    return build_dataset(registry, feature_rows(), labels, target_name='flood_depth_cm', **options)
