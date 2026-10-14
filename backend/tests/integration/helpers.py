"""Synthetic contract examples only, not predictions or accuracy evidence."""

from vietsafe.data_pipeline.features.engineering import FEATURE_NAMES, FEATURE_UNITS, FEATURE_VERSION
from vietsafe.data_pipeline.registry import checksum
from vietsafe.integration.contracts import INPUT_SCHEMA, OUTPUT_SCHEMA, SOURCE_SCHEMA


def input_payload():
    roads = ['fixture-forward', 'fixture-reverse']  # IDs deliberately opaque.
    graph = dict(graph_version='road-connectivity-v1', network_version='fixture-v1',
                 registry_checksum='a' * 64, road_ids=roads.copy(),
                 directed_edges=[[0, 1], [1, 0]], adjacency=[[0, 1], [1, 0]],
                 policy='raw-travel-continuity-no-self-loops-uturns-allowed-v1')
    return dict(schema=INPUT_SCHEMA, source_schema=SOURCE_SCHEMA, contract_status='draft',
                mode='artifact', feature_version=FEATURE_VERSION, network_version='fixture-v1',
                graph_checksum=checksum(graph), graph=graph, road_ids=roads,
                feature_names=list(FEATURE_NAMES), feature_units=list(FEATURE_UNITS),
                timestep_minutes=30, lookback_steps=2, issue_time='2026-10-08T02:30:00Z',
                history_timestamps=['2026-10-08T02:00:00Z', '2026-10-08T02:30:00Z'],
                horizon_steps=1, horizon_minutes=30,
                X=[[[0, None, 1, 2, .4, 8] for _ in roads] for _ in range(2)],
                X_mask=[[[True, False, True, True, True, True] for _ in roads] for _ in range(2)],
                feature_as_of=[['2026-10-08T02:30:00Z'] * 2 for _ in range(2)],
                feature_row_checksums=[['b' * 64] * 2 for _ in range(2)])


def output_metadata():
    return dict(schema=OUTPUT_SCHEMA, contract_status='draft', mode='artifact',
                network_version='fixture-v1', model_version='synthetic-contract-test-only',
                issue_time='2026-10-08T02:30:00Z', issued_at='2026-10-08T02:31:00Z',
                horizon_minutes=30, forecast_time='2026-10-08T03:00:00Z',
                output_fields=['risk', 'speed_km_h'])


def output_payload():
    return dict(output_metadata(), roads=[dict(road_id='fixture-forward', status='OK',
                                               risk=0, speed_km_h=20)],
                coverage=dict(total=1, predicted=1, missing_input=0, unavailable=0, stale=0))
