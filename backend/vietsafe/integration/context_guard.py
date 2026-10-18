"""Offline identity/set checks across typed Integration artifacts or their dicts."""

from .contracts import ForecastOutput, require, sequence, validate_network_match
from .context_contracts import IntegrationContext, SCHEMA
from .map_contracts import MapNetwork
from .routing_contracts import RoutingNetwork


def _validated(value, cls):
    # Revalidate even typed objects; never trust a caller-supplied summary hash.
    return cls(value.to_dict() if isinstance(value, cls) else value)


def build_integration_context(*, mode, map_network, routing_network, forecasts=()):
    """Require Map/Routing exact scope; Forecast rows are an explicit subset.

    Mode is supplied by the caller, never inferred from opaque road IDs.
    Missing forecasts remain missing; this function produces no prediction.
    """
    require(mode in ('demo', 'artifact'), 'mode')
    map_artifact = _validated(map_network, MapNetwork)
    routing_artifact = _validated(routing_network, RoutingNetwork)
    m, r = map_artifact.to_dict(), routing_artifact.to_dict()
    network = m['network_version']
    validate_network_match(network, r['network_version'])
    road_ids = sorted(road['road_id'] for road in m['roads'])
    scope = set(road_ids)
    routing_scope = {arc['road_id'] for arc in r['arcs']}
    require(routing_scope <= scope, 'routing_network.arcs', 'Routing contains unknown road', 'UNKNOWN_ROAD')
    require(routing_scope == scope, 'routing_network.arcs', 'Routing road scope differs from Map')
    require(m['registry_checksum'] == r['registry_checksum'], 'registry_checksum',
            'Map and Routing must describe the same registry snapshot')
    sequence(forecasts, 'forecasts')
    summaries = []
    for value in forecasts:
        artifact = _validated(value, ForecastOutput)
        f = artifact.to_dict()
        validate_network_match(network, f['network_version'])
        require(f['mode'] == mode, 'forecasts.mode', 'Forecast mode differs from context')
        ids = sorted(road['road_id'] for road in f['roads'])
        require(set(ids) <= scope, 'forecasts.roads', 'Forecast contains unknown road', 'UNKNOWN_ROAD')
        # Explicit prediction scope, not a claim that all context roads are predicted.
        artifact.validate_scope(network, ids)
        summary = {key: f[key] for key in ('schema', 'mode', 'network_version', 'model_version',
                   'issue_time', 'issued_at', 'horizon_minutes', 'forecast_time', 'coverage')}
        summary.update(checksum=artifact.checksum(), road_ids=ids)
        summaries.append(summary)
    summaries.sort(key=lambda f: f['horizon_minutes'])
    artifacts = {'forecasts': summaries}
    for name, artifact, payload in [('map_network', map_artifact, m),
                                     ('routing_network', routing_artifact, r)]:
        artifacts[name] = dict(schema=payload['schema'], checksum=artifact.checksum(),
                               registry_checksum=payload['registry_checksum'])
    return IntegrationContext(dict(schema=SCHEMA, contract_status='draft', mode=mode,
        network_version=network, road_ids=road_ids, artifacts=artifacts,
        available_horizons_minutes=[f['horizon_minutes'] for f in summaries]))
