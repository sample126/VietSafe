"""Draft map display contracts: canonical geometry, no forecast or route data."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from ..data_pipeline.registry import canonical_bytes, checksum, finite_number
from .errors import IntegrationContractError

SCHEMA = 'vietsafe.map-network.v1'
ROAD_FIELDS = frozenset(('road_id', 'network_version', 'name', 'geometry', 'directionality'))
NETWORK_FIELDS = frozenset(('schema', 'contract_status', 'network_version', 'registry_checksum',
                            'coordinate_order', 'roads'))


def require(condition, path, message='Invalid map contract', code='INVALID_CONTRACT'):
    if not condition:
        raise IntegrationContractError(code, message, path)


def nonempty(value, path):
    require(isinstance(value, str) and bool(value.strip()), path, 'Nonempty string required')


def fields(value, expected, path):
    require(isinstance(value, Mapping) and set(value) == expected, path,
            'Missing or unsupported fields')


def validate_road(road):
    fields(road, ROAD_FIELDS, 'road')
    for key in ('road_id', 'network_version', 'name'):
        nonempty(road[key], key)
    require(road['directionality'] in ('forward', 'reverse', 'both'), 'directionality')
    geometry = road['geometry']
    require(isinstance(geometry, list) and len(geometry) >= 2, 'geometry',
            'Polyline requires at least two coordinates')
    for point in geometry:
        require(isinstance(point, list) and len(point) == 2
                and all(finite_number(v) for v in point)
                and -90 <= point[0] <= 90 and -180 <= point[1] <= 180,
                'geometry', 'Finite [lat, lon] coordinates required')
    require(len({tuple(point) for point in geometry}) >= 2, 'geometry', 'Degenerate geometry')


def validate_network(payload):
    fields(payload, NETWORK_FIELDS, 'network')
    require(payload['schema'] == SCHEMA, 'schema')
    require(payload['contract_status'] == 'draft', 'contract_status')
    require(payload['coordinate_order'] == 'lat_lon', 'coordinate_order')
    nonempty(payload['network_version'], 'network_version')
    sha = payload['registry_checksum']
    require(isinstance(sha, str) and re.fullmatch(r'[0-9a-f]{64}', sha), 'registry_checksum')
    roads = payload['roads']
    require(isinstance(roads, list) and bool(roads), 'roads', 'Nonempty map network required')
    ids = []
    for road in roads:
        validate_road(road)
        require(road['network_version'] == payload['network_version'], 'roads.network_version',
                'Mixed network versions', 'NETWORK_VERSION_MISMATCH')
        ids.append(road['road_id'])
    require(ids == sorted(set(ids)), 'roads', 'Road IDs must be unique and sorted')


@dataclass(frozen=True, init=False)
class MapRoad:
    """Frozen canonical JSON storage; input/output containers are deeply detached."""
    _json: str

    def __init__(self, payload):
        try:
            copied = json.loads(canonical_bytes(payload))
        except (TypeError, ValueError, OverflowError, RecursionError):
            raise IntegrationContractError('INVALID_CONTRACT', 'Expected finite JSON payload') from None
        self._validate(copied)
        object.__setattr__(self, '_json', canonical_bytes(copied).decode('utf-8'))

    _validate = staticmethod(validate_road)

    @classmethod
    def from_dict(cls, payload):
        return cls(payload)

    def to_dict(self):
        return json.loads(self._json)

    def to_json(self):
        return self._json

    def checksum(self):
        return checksum(self.to_dict())


@dataclass(frozen=True, init=False)
class MapNetwork(MapRoad):
    """Canonical road entries only; not a directed arc list or route result."""
    _validate = staticmethod(validate_network)
