"""Pure projection of context-bound Map/Forecast artifacts; no runtime IO."""

from .api_contracts import ArtifactApiBundle, ROAD_FIELDS, SCHEMA
from .context_contracts import IntegrationContext
from .contracts import ForecastOutput, require, sequence, validate_network_match
from .map_contracts import MapNetwork


def _validated(value, cls):
    return cls(value.to_dict() if isinstance(value, cls) else value)


def build_artifact_api_bundle(*, context, map_network, forecasts=(), generated_at):
    """Verify supplied context exactly; never rebuild or silently repair it.

    Forecast row order and absent/null metrics are preserved from each producer.
    Map remains full-scope; forecast outputs are sorted only by horizon.
    """
    context_artifact = _validated(context, IntegrationContext)
    map_artifact = _validated(map_network, MapNetwork)
    c, m = context_artifact.to_dict(), map_artifact.to_dict()
    validate_network_match(c['network_version'], m['network_version'])
    require(c['road_ids'] == [r['road_id'] for r in m['roads']], 'context.road_ids',
            'Context scope differs from Map')
    expected_map = dict(schema=m['schema'], checksum=map_artifact.checksum(),
                        registry_checksum=m['registry_checksum'])
    require(c['artifacts']['map_network'] == expected_map, 'context.artifacts.map_network',
            'Context Map summary differs from actual artifact')
    sequence(forecasts, 'forecasts')
    artifacts = [_validated(value, ForecastOutput) for value in forecasts]
    artifacts.sort(key=lambda f: f.to_dict()['horizon_minutes'])
    summaries, payloads, hashes = [], [], {}
    for artifact in artifacts:
        f = artifact.to_dict()
        validate_network_match(c['network_version'], f['network_version'])
        require(f['mode'] == c['mode'], 'forecasts.mode', 'Forecast mode differs from context')
        ids = sorted(r['road_id'] for r in f['roads'])
        require(set(ids) <= set(c['road_ids']), 'forecasts.roads',
                'Forecast contains unknown road', 'UNKNOWN_ROAD')
        summary = {key: f[key] for key in ('schema', 'mode', 'network_version', 'model_version',
                   'issue_time', 'issued_at', 'horizon_minutes', 'forecast_time', 'coverage')}
        summary.update(checksum=artifact.checksum(), road_ids=ids)
        summaries.append(summary)
        payloads.append(f)
        hashes[str(f['horizon_minutes'])] = artifact.checksum()
    require(summaries == c['artifacts']['forecasts'], 'context.artifacts.forecasts',
            'Forecast set/summaries differ from supplied context')
    return ArtifactApiBundle(dict(schema=SCHEMA, contract_status='draft', mode=c['mode'],
        network_version=c['network_version'], generated_at=generated_at,
        available_horizons_minutes=c['available_horizons_minutes'],
        network=dict(schema=m['schema'], network_version=m['network_version'],
                     coordinate_order=m['coordinate_order'],
                     roads=[{key: road[key] for key in ROAD_FIELDS} for road in m['roads']]),
        forecasts=payloads, source_checksums=dict(integration_context=context_artifact.checksum(),
            map_network=map_artifact.checksum(), forecasts=hashes)))
