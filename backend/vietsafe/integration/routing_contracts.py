"""Draft directed network artifacts, independent of Forecast and route solvers."""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from ..data_pipeline.registry import canonical_bytes, checksum, finite_number
from .errors import IntegrationContractError

SCHEMA = "vietsafe.routing-network.v1"
ROUTING_POLICY = "registry-endpoints-directionality-v1-no-turn-restrictions"
ARC_FIELDS = frozenset((
    "road_id network_version travel_from travel_to length_km travel_geometry source_directionality"
).split())
NETWORK_FIELDS = frozenset((
    "schema contract_status network_version registry_checksum nodes arcs outgoing routing_policy"
).split())


def require(condition, path, message="Invalid routing network contract", code="INVALID_CONTRACT"):
    if not condition:
        raise IntegrationContractError(code, message, path)


def nonempty(value, path):
    require(isinstance(value, str) and bool(value.strip()), path, "Nonempty string required")


def fields(value, expected, path):
    require(isinstance(value, Mapping) and set(value) == expected, path,
            "Missing or unsupported fields")


def array(value, path):
    require(isinstance(value, list), path, "Array required")


def arc_identity(arc):
    return arc['road_id'], arc['travel_from'], arc['travel_to']


def validate_arc(arc):
    fields(arc, ARC_FIELDS, "arc")
    for key in ('road_id', 'network_version', 'travel_from', 'travel_to'):
        nonempty(arc[key], key)
    require(arc['travel_from'] != arc['travel_to'], 'travel_to', "Self-loop is not supported")
    require(arc['source_directionality'] in ('forward', 'reverse', 'both'), 'source_directionality')
    require(finite_number(arc['length_km']) and arc['length_km'] > 0, 'length_km',
            "Finite positive length required")
    coords = arc['travel_geometry']
    array(coords, 'travel_geometry')
    require(len(coords) >= 2, 'travel_geometry', "Polyline requires at least two coordinates")
    for point in coords:
        array(point, 'travel_geometry')
        require(len(point) == 2 and all(finite_number(v) for v in point)
                and -90 <= point[0] <= 90 and -180 <= point[1] <= 180,
                'travel_geometry', "Finite [lat, lon] coordinates required")
    require(len({tuple(point) for point in coords}) >= 2, 'travel_geometry', "Degenerate geometry")


def validate_network(payload):
    fields(payload, NETWORK_FIELDS, 'network')
    require(payload['schema'] == SCHEMA, 'schema')
    require(payload['contract_status'] == 'draft', 'contract_status')
    require(payload['routing_policy'] == ROUTING_POLICY, 'routing_policy')
    nonempty(payload['network_version'], 'network_version')
    sha = payload['registry_checksum']
    require(isinstance(sha, str) and re.fullmatch(r'[0-9a-f]{64}', sha), 'registry_checksum')
    nodes, arcs = payload['nodes'], payload['arcs']
    array(nodes, 'nodes')
    require(bool(nodes), 'nodes', "Nonempty network required")
    for node in nodes:
        nonempty(node, 'nodes')
    require(nodes == sorted(set(nodes)), 'nodes', "Nodes must be unique and sorted")
    array(arcs, 'arcs')
    require(bool(arcs), 'arcs', "Nonempty arc list required")
    identities, grouped = [], {}
    expected_outgoing = {node: [] for node in nodes}
    used_nodes = set()
    for i, arc in enumerate(arcs):
        validate_arc(arc)
        require(arc['network_version'] == payload['network_version'], 'arcs.network_version',
                "Mixed network versions", 'NETWORK_VERSION_MISMATCH')
        require(arc['travel_from'] in expected_outgoing and arc['travel_to'] in expected_outgoing,
                'arcs', "Arc endpoint not in nodes")
        expected_outgoing[arc['travel_from']].append(i)
        used_nodes.update((arc['travel_from'], arc['travel_to']))
        identities.append(arc_identity(arc))
        grouped.setdefault(arc['road_id'], []).append(arc)
    require(identities == sorted(set(identities)), 'arcs', "Composite arc identities must be unique and sorted")
    require(used_nodes == set(nodes), 'nodes', "Nodes must be exactly registry arc endpoints")
    for rows in grouped.values():
        if rows[0]['source_directionality'] == 'both':
            require(len(rows) == 2, 'arcs', "Both-direction road requires exactly two arcs")
            a, b = rows
            require(b['source_directionality'] == 'both'
                    and a['travel_from'] == b['travel_to'] and a['travel_to'] == b['travel_from']
                    and a['length_km'] == b['length_km']
                    and a['travel_geometry'] == list(reversed(b['travel_geometry'])),
                    'arcs', "Both-direction arcs must be opposite travels of the same road")
        else:
            require(len(rows) == 1, 'arcs', "Directed road must have exactly one arc")
    outgoing = payload['outgoing']
    fields(outgoing, set(nodes), 'outgoing')
    for indices in outgoing.values():
        array(indices, 'outgoing')
        require(all(type(i) is int for i in indices), 'outgoing', "Integer arc indices required")
    require(outgoing == expected_outgoing, 'outgoing', "Outgoing index differs from arc ordering")


@dataclass(frozen=True, init=False)
class RoutingArc:
    """Frozen canonical JSON storage gives deep immutability and detached exports."""
    _json: str

    def __init__(self, payload):
        try:
            copied = json.loads(canonical_bytes(payload))
        except (ValueError, TypeError, OverflowError, RecursionError):
            raise IntegrationContractError('INVALID_CONTRACT', 'Expected finite JSON payload') from None
        self._validate(copied)
        object.__setattr__(self, '_json', canonical_bytes(copied).decode('utf-8'))

    _validate = staticmethod(validate_arc)

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
class RoutingNetwork(RoutingArc):
    """Junction-as-node topology only; no cost, risk, closure or route result."""
    _validate = staticmethod(validate_network)
