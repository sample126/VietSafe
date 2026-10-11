"""Draft context summary contract; no predictions, costs or runtime IO."""

from dataclasses import dataclass
from datetime import timedelta

from .contracts import (_Contract, OUTPUT_SCHEMA, digest, integer, keys, names,
                        require, sequence, text, timestamp, validate_network_match)
from .map_contracts import SCHEMA as MAP_SCHEMA
from .routing_contracts import SCHEMA as ROUTING_SCHEMA

SCHEMA = 'vietsafe.integration-context.v1'
CONTEXT_FIELDS = frozenset(('schema contract_status mode network_version road_ids artifacts '
                            'available_horizons_minutes').split())
NETWORK_SUMMARY_FIELDS = frozenset('schema checksum registry_checksum'.split())
FORECAST_SUMMARY_FIELDS = frozenset(('schema checksum mode network_version model_version issue_time '
                                    'issued_at horizon_minutes forecast_time road_ids coverage').split())
COVERAGE_FIELDS = frozenset('total predicted missing_input unavailable stale'.split())


def sorted_ids(value, path, allow_empty=False):
    names(value, path, allow_empty=allow_empty)
    require(value == sorted(value), path, 'Road IDs must be sorted')


def validate_context(p):
    keys(p, CONTEXT_FIELDS, 'context')
    require(p['schema'] == SCHEMA and p['contract_status'] == 'draft', 'schema')
    require(p['mode'] in ('demo', 'artifact'), 'mode')
    text(p['network_version'], 'network_version')
    sorted_ids(p['road_ids'], 'road_ids')
    artifacts = p['artifacts']
    keys(artifacts, {'map_network', 'routing_network', 'forecasts'}, 'artifacts')
    for key, schema in [('map_network', MAP_SCHEMA), ('routing_network', ROUTING_SCHEMA)]:
        summary = artifacts[key]
        keys(summary, NETWORK_SUMMARY_FIELDS, key)
        require(summary['schema'] == schema, key + '.schema')
        digest(summary['checksum'], key + '.checksum')
        digest(summary['registry_checksum'], key + '.registry_checksum')
    require(artifacts['map_network']['registry_checksum'] == artifacts['routing_network']['registry_checksum'],
            'registry_checksum', 'Map and Routing must describe the same registry snapshot')
    sequence(artifacts['forecasts'], 'forecasts')
    horizons, forecast_set = [], None
    for f in artifacts['forecasts']:
        keys(f, FORECAST_SUMMARY_FIELDS, 'forecasts')
        require(f['schema'] == OUTPUT_SCHEMA, 'forecasts.schema')
        digest(f['checksum'], 'forecasts.checksum')
        validate_network_match(p['network_version'], f['network_version'])
        require(f['mode'] == p['mode'], 'forecasts.mode', 'Forecast mode differs from context')
        text(f['model_version'], 'forecasts.model_version')
        issue = timestamp(f['issue_time'], 'forecasts.issue_time', p['mode'] == 'artifact')
        timestamp(f['issued_at'], 'forecasts.issued_at')
        target = timestamp(f['forecast_time'], 'forecasts.forecast_time')
        h = f['horizon_minutes']
        allowed = (30, 60) if p['mode'] == 'artifact' else (0, 15, 30, 45, 60)
        require(type(h) is int and h in allowed, 'forecasts.horizon_minutes',
                'Unsupported horizon', 'UNSUPPORTED_HORIZON')
        require(target - issue == timedelta(minutes=h), 'forecasts.forecast_time')
        identity = (f['issue_time'], f['model_version'])
        require(forecast_set is None or forecast_set == identity, 'forecasts',
                'Forecast set must share issue_time and model_version')
        forecast_set = identity
        sorted_ids(f['road_ids'], 'forecasts.road_ids', allow_empty=True)
        require(set(f['road_ids']) <= set(p['road_ids']), 'forecasts.road_ids',
                'Forecast contains unknown road', 'UNKNOWN_ROAD')
        keys(f['coverage'], COVERAGE_FIELDS, 'forecasts.coverage')
        for value in f['coverage'].values():
            integer(value, 'forecasts.coverage')
        require(f['coverage']['total'] == len(f['road_ids'])
                and sum(v for k, v in f['coverage'].items() if k != 'total') == len(f['road_ids']),
                'forecasts.coverage', 'Coverage must match explicit forecast scope')
        horizons.append(h)
    require(horizons == sorted(set(horizons)), 'forecasts', 'Horizons must be unique and sorted')
    sequence(p['available_horizons_minutes'], 'available_horizons_minutes')
    require(all(type(h) is int for h in p['available_horizons_minutes'])
            and p['available_horizons_minutes'] == horizons, 'available_horizons_minutes')


@dataclass(frozen=True, init=False)
class IntegrationContext(_Contract):
    """Detached summary; artifact hashes are verified when built from artifacts.

    Deserializing a summary validates its structure, not possession/authenticity
    of the source artifacts. Use build_integration_context to bind actual inputs.
    """
    _validate = staticmethod(validate_context)
