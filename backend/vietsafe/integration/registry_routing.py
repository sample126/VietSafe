"""RoadRegistry → directed network, without Forecast graph or runtime imports."""

from collections.abc import Mapping
from dataclasses import fields

from ..data_pipeline.exceptions import DataValidationError
from ..data_pipeline.registry import RoadRegistry, RoadSegment
from .errors import IntegrationContractError
from .routing_contracts import ROUTING_POLICY, SCHEMA, RoutingNetwork, arc_identity, require


def _registry(source):
    """Revalidate with public Data models; translate errors at the boundary."""
    embedded_checksum = None
    try:
        if isinstance(source, RoadRegistry):
            registry = RoadRegistry(source.network_version, list(source))
        else:
            require(isinstance(source, Mapping), 'registry', "RoadRegistry or registry dict required")
            require({'network_version', 'roads'} <= set(source)
                    and set(source) <= {'network_version', 'roads', 'registry_checksum'}, 'registry')
            if 'registry_checksum' in source:
                embedded_checksum = source['registry_checksum']
                require(isinstance(embedded_checksum, str), 'registry_checksum')
            raw = source['roads']
            require(isinstance(raw, (list, tuple)), 'roads')
            roads = []
            expected = {field.name for field in fields(RoadSegment)}
            for entry in raw:
                require(isinstance(entry, Mapping) and set(entry) == expected, 'roads',
                        "Serialized RoadSegment fields required")
                require(entry['network_version'] == source['network_version'], 'roads.network_version',
                        "Mixed registry versions", 'NETWORK_VERSION_MISMATCH')
                roads.append(RoadSegment(**entry))
            registry = RoadRegistry(source['network_version'], roads)
    except DataValidationError as error:
        mismatch = any(issue.code == 'NETWORK_MISMATCH' for issue in error.issues)
        code = 'NETWORK_VERSION_MISMATCH' if mismatch else 'INVALID_CONTRACT'
        raise IntegrationContractError(code, 'Invalid source registry', 'registry') from None
    except (TypeError, AttributeError, ValueError, OverflowError, RecursionError) as error:
        if isinstance(error, IntegrationContractError):
            raise
        raise IntegrationContractError('INVALID_CONTRACT', 'Malformed source registry', 'registry') from None
    return registry, embedded_checksum


def build_routing_network(registry, *, expected_registry_checksum=None):
    """Pure adapter; accepts Data object or exact public registry serialization.

    Optional expected checksum is of RoadRegistry.to_dict() canonical serialization,
    not raw file bytes. Input road order is canonicalized by RoadRegistry itself.
    """
    source, embedded = _registry(registry)
    actual = source.checksum
    for expected in (expected_registry_checksum, embedded):
        if expected is not None:
            require(isinstance(expected, str) and expected == actual, 'registry_checksum',
                    "Registry checksum mismatch")
    arcs, nodes = [], set()
    for road in source:
        a, b = road.endpoint_a, road.endpoint_b
        require(a != b, 'endpoints', "Self-loop segment is not supported")
        nodes.update((a, b))
        geometry = [list(point) for point in road.coordinates]
        travels = []
        if road.directionality in ('forward', 'both'):
            travels.append((a, b, geometry))
        if road.directionality in ('reverse', 'both'):
            travels.append((b, a, list(reversed(geometry))))
        for start, end, coords in travels:
            arcs.append(dict(road_id=road.road_id, network_version=road.network_version,
                             travel_from=start, travel_to=end, length_km=road.length_km,
                             travel_geometry=coords, source_directionality=road.directionality))
    arcs.sort(key=arc_identity)
    outgoing = {node: [] for node in sorted(nodes)}
    for index, arc in enumerate(arcs):
        outgoing[arc['travel_from']].append(index)
    return RoutingNetwork(dict(schema=SCHEMA, contract_status='draft', network_version=source.network_version,
                               registry_checksum=actual, nodes=sorted(nodes), arcs=arcs,
                               outgoing=outgoing, routing_policy=ROUTING_POLICY))
