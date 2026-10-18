"""Draft API presentation JSON; no endpoint, model or route execution."""

from dataclasses import dataclass

from .contracts import (_Contract, ForecastOutput, digest, keys, names, require,
                        sequence, text, timestamp, validate_network_match)
from .map_contracts import MapRoad, SCHEMA as MAP_SCHEMA

SCHEMA = 'vietsafe.artifact-api-bundle.v1'
BUNDLE_FIELDS = frozenset(('schema contract_status mode network_version generated_at '
                           'available_horizons_minutes network forecasts source_checksums').split())
NETWORK_FIELDS = frozenset('schema network_version coordinate_order roads'.split())
ROAD_FIELDS = frozenset('road_id name geometry directionality'.split())


def validate_bundle(p):
    keys(p, BUNDLE_FIELDS, 'bundle')
    require(p['schema'] == SCHEMA and p['contract_status'] == 'draft', 'schema')
    require(p['mode'] in ('demo', 'artifact'), 'mode')
    text(p['network_version'], 'network_version')
    timestamp(p['generated_at'], 'generated_at')
    network = p['network']
    keys(network, NETWORK_FIELDS, 'network')
    require(network['schema'] == MAP_SCHEMA, 'network.schema')
    validate_network_match(p['network_version'], network['network_version'])
    require(network['coordinate_order'] == 'lat_lon', 'network.coordinate_order')
    sequence(network['roads'], 'network.roads')
    ids = []
    for road in network['roads']:
        keys(road, ROAD_FIELDS, 'network.roads')
        MapRoad(dict(road, network_version=network['network_version']))
        ids.append(road['road_id'])
    names(ids, 'network.roads')
    require(ids == sorted(ids), 'network.roads', 'Roads must be sorted by road_id')
    sources = p['source_checksums']
    keys(sources, {'integration_context', 'map_network', 'forecasts'}, 'source_checksums')
    for key in ('integration_context', 'map_network'):
        digest(sources[key], 'source_checksums.' + key)
    sequence(p['forecasts'], 'forecasts')
    horizons, actual_checksums, forecast_set = [], {}, None
    for raw in p['forecasts']:
        artifact = ForecastOutput(raw)
        f = artifact.to_dict()
        validate_network_match(p['network_version'], f['network_version'])
        require(f['mode'] == p['mode'], 'forecasts.mode', 'Forecast mode differs from bundle')
        require({r['road_id'] for r in f['roads']} <= set(ids), 'forecasts.roads',
                'Forecast contains unknown road', 'UNKNOWN_ROAD')
        identity = (f['issue_time'], f['model_version'])
        require(forecast_set is None or forecast_set == identity, 'forecasts',
                'Forecast set must share issue_time and model_version')
        forecast_set = identity
        h = f['horizon_minutes']
        horizons.append(h)
        actual_checksums[str(h)] = artifact.checksum()
    require(horizons == sorted(set(horizons)), 'forecasts', 'Horizons must be unique and sorted')
    sequence(p['available_horizons_minutes'], 'available_horizons_minutes')
    require(all(type(h) is int for h in p['available_horizons_minutes'])
            and p['available_horizons_minutes'] == horizons, 'available_horizons_minutes')
    keys(sources['forecasts'], set(actual_checksums), 'source_checksums.forecasts')
    for h, sha in sources['forecasts'].items():
        digest(sha, 'source_checksums.forecasts.' + h)
    require(sources['forecasts'] == actual_checksums, 'source_checksums.forecasts',
            'Forecast checksums differ from payloads')


@dataclass(frozen=True, init=False)
class ArtifactApiBundle(_Contract):
    """Immutable presentation boundary, not a runtime response or authenticity proof."""
    _validate = staticmethod(validate_bundle)
