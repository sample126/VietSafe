"""RoadRegistry → MapNetwork directly; never reads RoutingNetwork arcs."""

from collections.abc import Mapping
from dataclasses import fields

from ..data_pipeline.exceptions import DataValidationError
from ..data_pipeline.registry import RoadRegistry, RoadSegment
from .errors import IntegrationContractError
from .map_contracts import MapNetwork, SCHEMA, require


def build_map_network(registry, *, expected_registry_checksum=None):
    """Pure projection of public Data registry object or full serialized dict.

    Optional registry_checksum in a dict and the keyword checksum both refer to
    canonical RoadRegistry.to_dict(), not the raw JSON file's bytes.
    """
    embedded = None
    try:
        if isinstance(registry, RoadRegistry):
            source = RoadRegistry(registry.network_version, list(registry))
        else:
            require(isinstance(registry, Mapping), 'registry', 'RoadRegistry or registry dict required')
            require({'network_version', 'roads'} <= set(registry)
                    and set(registry) <= {'network_version', 'roads', 'registry_checksum'}, 'registry')
            if 'registry_checksum' in registry:
                embedded = registry['registry_checksum']
                require(isinstance(embedded, str), 'registry_checksum')
            require(isinstance(registry['roads'], (list, tuple)), 'roads')
            expected_fields = {field.name for field in fields(RoadSegment)}
            roads = []
            for entry in registry['roads']:
                require(isinstance(entry, Mapping) and set(entry) == expected_fields,
                        'roads', 'Serialized RoadSegment fields required')
                require(entry['network_version'] == registry['network_version'], 'roads.network_version',
                        'Mixed registry versions', 'NETWORK_VERSION_MISMATCH')
                roads.append(RoadSegment(**entry))
            source = RoadRegistry(registry['network_version'], roads)
        actual = source.checksum
    except DataValidationError as error:
        code = ('NETWORK_VERSION_MISMATCH' if any(i.code == 'NETWORK_MISMATCH' for i in error.issues)
                else 'INVALID_CONTRACT')
        raise IntegrationContractError(code, 'Invalid source registry', 'registry') from None
    except (TypeError, AttributeError, ValueError, OverflowError, RecursionError) as error:
        if isinstance(error, IntegrationContractError):
            raise
        raise IntegrationContractError('INVALID_CONTRACT', 'Malformed source registry', 'registry') from None
    for expected in (embedded, expected_registry_checksum):
        if expected is not None:
            require(isinstance(expected, str) and expected == actual, 'registry_checksum',
                    'Registry checksum mismatch')
    # Explicit allowlist: no source IDs, provenance, endpoints, features or labels.
    roads = [dict(road_id=r.road_id, network_version=r.network_version, name=r.name,
                  geometry=[list(point) for point in r.coordinates], directionality=r.directionality)
             for r in sorted(source, key=lambda road: road.road_id)]
    return MapNetwork(dict(schema=SCHEMA, contract_status='draft', network_version=source.network_version,
                           registry_checksum=actual, coordinate_order='lat_lon', roads=roads))
