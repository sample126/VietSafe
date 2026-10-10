"""Synthetic alignment fixtures and constructors, isolated within Data tests."""

from pathlib import Path

from vietsafe.data_pipeline.environment import EnvironmentalGrid
from vietsafe.data_pipeline.ingestion.gpm import read_gpm
from vietsafe.data_pipeline.ingestion.smap import read_smap
from vietsafe.data_pipeline.registry import RoadRegistry, RoadSegment

ROOT = Path(__file__).resolve().parents[3] / 'data/fixtures'
T = '2026-10-08T02:30:00Z'
A = '2026-10-08T04:00:00Z'


def grid(source='gpm', **changes):
    loader = read_gpm if source == 'gpm' else read_smap
    original = loader(ROOT / 'alignment' / f'{source}-alignment-grid.json').to_dict()
    original.update(changes)
    return EnvironmentalGrid.from_dict(original)


def road(lat=21.032, lon=105.800, identity='HN-001'):
    return RoadSegment(identity, 'alignment-test-v1', 'demo', identity, 'Synthetic road',
                       ((lat, lon - .0001), (lat, lon + .0001)), 'a', 'b', .02, 'both')


def registry(*roads):
    return RoadRegistry('alignment-test-v1', roads or [road()])
