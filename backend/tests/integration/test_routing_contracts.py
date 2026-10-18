"""Contract structure, immutability and internal-index invariants."""

import copy
import hashlib
import unittest
from dataclasses import FrozenInstanceError

from vietsafe.integration.errors import IntegrationContractError
from vietsafe.integration.routing_contracts import RoutingArc, RoutingNetwork, ROUTING_POLICY, SCHEMA


def payload():
    return dict(schema=SCHEMA, contract_status='draft', network_version='test-v1', registry_checksum='a' * 64,
                nodes=['A', 'B'], arcs=[dict(road_id='opaque:no-topology-here', network_version='test-v1',
                travel_from='A', travel_to='B', length_km=1.234567,
                travel_geometry=[[21, 105], [21.1, 105.2], [21.2, 105.3]], source_directionality='forward')],
                outgoing={'A': [0], 'B': []}, routing_policy=ROUTING_POLICY)


class RoutingContractTests(unittest.TestCase):
    def test_valid_network_schema(self):
        result = RoutingNetwork(payload()).to_dict()
        self.assertEqual(result['schema'], 'vietsafe.routing-network.v1')
        self.assertEqual(result['contract_status'], 'draft')
        self.assertEqual(result['nodes'], ['A', 'B'])

    def test_schema_draft_policy_and_extra_fields(self):
        for field, value in [('schema', 'wrong'), ('contract_status', 'approved'),
                             ('routing_policy', 'risk-based'), ('risk', 0)]:
            p = payload()
            p[field] = value
            with self.subTest(field=field), self.assertRaises(IntegrationContractError):
                RoutingNetwork(p)

    def test_nodes_sorted_unique_nonempty_exact(self):
        for nodes in ([], ['B', 'A'], ['A', 'A', 'B'], ['A', 'B', 'C'], ['A', 1]):
            p = payload()
            p['nodes'] = nodes
            with self.subTest(nodes=nodes), self.assertRaises(IntegrationContractError):
                RoutingNetwork(p)

    def test_arc_duplicate_rejected(self):
        p = payload()
        p['arcs'] *= 2
        with self.assertRaises(IntegrationContractError):
            RoutingNetwork(p)

    def test_arc_network_mismatch(self):
        p = payload()
        p['arcs'][0]['network_version'] = 'other'
        with self.assertRaises(IntegrationContractError) as caught:
            RoutingNetwork(p)
        self.assertEqual(caught.exception.code, 'NETWORK_VERSION_MISMATCH')

    def test_arc_self_loop(self):
        p = payload()['arcs'][0]
        p['travel_to'] = 'A'
        with self.assertRaises(IntegrationContractError):
            RoutingArc(p)

    def test_arc_length(self):
        for value in (0, -1, True, '1', None, float('nan'), float('inf'), -float('inf')):
            p = payload()['arcs'][0]
            p['length_km'] = value
            with self.subTest(value=value), self.assertRaises(IntegrationContractError):
                RoutingArc(p)

    def test_geometry(self):
        for geometry in ([], [[21, 105]], [[21, 105], [21, 105]], [[91, 105], [21, 105]],
                         [[21, 181], [21, 105]], [[True, 105], [21, 105]], [[21], [21, 105]],
                         [[21, float('inf')], [21, 105]]):
            p = payload()['arcs'][0]
            p['travel_geometry'] = geometry
            with self.subTest(geometry=geometry), self.assertRaises(IntegrationContractError):
                RoutingArc(p)

    def test_outgoing_exact_and_integer(self):
        for outgoing in ({'A': [], 'B': [0]}, {'A': [True], 'B': []}, {'A': [1], 'B': []},
                         {'A': [0, 0], 'B': []}, {'A': [0]}):
            p = payload()
            p['outgoing'] = outgoing
            with self.subTest(outgoing=outgoing), self.assertRaises(IntegrationContractError):
                RoutingNetwork(p)

    def test_both_requires_opposite_pair(self):
        p = payload()
        a = p['arcs'][0]
        a['source_directionality'] = 'both'
        with self.assertRaises(IntegrationContractError):
            RoutingNetwork(p)
        b = dict(a, travel_from='B', travel_to='A', travel_geometry=list(reversed(a['travel_geometry'])))
        p['arcs'].append(b)
        p['outgoing']['B'] = [1]
        RoutingNetwork(p)
        b['travel_geometry'] = a['travel_geometry']
        with self.assertRaises(IntegrationContractError):
            RoutingNetwork(p)

    def test_directed_road_cannot_gain_reverse(self):
        p = payload()
        a = p['arcs'][0]
        p['arcs'].append(dict(a, travel_from='B', travel_to='A', travel_geometry=list(reversed(a['travel_geometry']))))
        p['outgoing']['B'] = [1]
        with self.assertRaises(IntegrationContractError):
            RoutingNetwork(p)

    def test_no_routing_metrics(self):
        for field in ('risk', 'speed', 'forecast', 'closure'):
            p = payload()['arcs'][0]
            p[field] = 0
            with self.subTest(field=field), self.assertRaises(IntegrationContractError):
                RoutingArc(p)

    def test_checksum_immutable_and_deterministic(self):
        p = payload()
        before = copy.deepcopy(p)
        result = RoutingNetwork(p)
        same = RoutingNetwork.from_dict(dict(reversed(list(p.items()))))
        self.assertEqual(result.to_json(), same.to_json())
        self.assertEqual(result.checksum(), hashlib.sha256(result.to_json().encode()).hexdigest())
        p['arcs'][0]['travel_geometry'][0][0] = 0
        result.to_dict()['outgoing']['A'].append(4)
        self.assertEqual(result.to_dict(), before)
        with self.assertRaises(FrozenInstanceError):
            result.extra = 1

    def test_malformed_json_objects(self):
        for p in (None, [], 'abc', {'arcs': []}):
            with self.assertRaises(IntegrationContractError):
                RoutingNetwork(p)
