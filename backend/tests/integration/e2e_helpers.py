"""Synthetic CONTRACT fixtures only: no model or real forecast accuracy claim."""

from datetime import datetime, timedelta
from pathlib import Path

from vietsafe.data_pipeline.ingestion.osm import read_overpass
from vietsafe.data_pipeline.processing.osm_network import build_road_network
from vietsafe.integration.contracts import ForecastOutput, OUTPUT_SCHEMA

GENERATED_AT = '2026-10-08T04:12:34Z'
FIXTURE = Path(__file__).resolve().parents[3] / 'data/fixtures/osm/overpass-small.json'


def osm_registry():
    return build_road_network(read_overpass(FIXTURE)).registry


def synthetic_contract_forecast(registry, horizon=30, issue_time='2026-10-08T02:30:00Z'):
    """Four explicit status rows on a subset, not a predictive algorithm."""
    ids = sorted(r.road_id for r in registry)
    assert len(ids) > 4, 'Fixture needs four statuses plus an unforecast road'
    rows = [dict(road_id=ids[0], status='OK', risk=0),
            dict(road_id=ids[1], status='MISSING_INPUT', reason_code='FIXTURE_MISSING', risk=None),
            dict(road_id=ids[2], status='UNAVAILABLE', reason_code='FIXTURE_UNAVAILABLE'),
            dict(road_id=ids[3], status='STALE', reason_code='FIXTURE_STALE', risk=None)]
    target = datetime.strptime(issue_time, '%Y-%m-%dT%H:%M:%SZ') + timedelta(minutes=horizon)
    return ForecastOutput(dict(schema=OUTPUT_SCHEMA, contract_status='draft', mode='artifact',
        network_version=registry.network_version, model_version='SYNTHETIC-CONTRACT-FIXTURE-ONLY',
        issue_time=issue_time, issued_at='2026-10-08T02:31:00Z', horizon_minutes=horizon,
        forecast_time=target.strftime('%Y-%m-%dT%H:%M:%SZ'), output_fields=['risk'], roads=rows,
        coverage=dict(total=4, predicted=1, missing_input=1, unavailable=1, stale=1)))
