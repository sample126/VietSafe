"""Endpoint/directionality projection with actual offline OSM fixture."""

import copy
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from vietsafe.data_pipeline.registry import RoadSegment, RoadRegistry
from vietsafe.data_pipeline.ingestion.osm import read_overpass
from vietsafe.data_pipeline.processing.osm_network import build_road_network
from vietsafe.integration.registry_routing import build_routing_network
from vietsafe.integration.errors import IntegrationContractError

COORDS = ((21., 105.), (21.1, 105.2), (21.2, 105.3), (21.3, 105.4))
FIXTURE = Path(__file__).resolve().parents[3] / 'data/fixtures/osm/overpass-small.json'


def road(direction='forward', rid='HN-001', a='A', b='B'):
    return RoadSegment(rid, 'test-v1', 'demo', 'synthetic', 'Test', COORDS, a, b, 1.234567, direction)


def registry(*roads):
    return RoadRegistry('test-v1', roads or [road()])


class RegistryRoutingTests(unittest.TestCase):
    def test_forward(self):
        source = registry(road())
        p = build_routing_network(source).to_dict()
        self.assertEqual(len(p['arcs']), 1)
        a = p['arcs'][0]
        self.assertEqual((a['travel_from'], a['travel_to']), ('A', 'B'))
        self.assertEqual(a['travel_geometry'], [list(c) for c in COORDS])
        self.assertEqual(a['length_km'], 1.234567)
        self.assertEqual(p['registry_checksum'], source.checksum)

    def test_reverse_full_polyline(self):
        p = build_routing_network(registry(road('reverse'))).to_dict()
        self.assertEqual(len(p['arcs']), 1)
        a = p['arcs'][0]
        self.assertEqual((a['travel_from'], a['travel_to']), ('B', 'A'))
        self.assertEqual(a['travel_geometry'], [list(c) for c in reversed(COORDS)])
        self.assertEqual(p['outgoing'], {'A': [], 'B': [0]})

    def test_both_same_road_id(self):
        p = build_routing_network(registry(road('both'))).to_dict()
        self.assertEqual(len(p['arcs']), 2)
        self.assertEqual([a['road_id'] for a in p['arcs']], ['HN-001', 'HN-001'])
        self.assertEqual([(a['travel_from'], a['travel_to']) for a in p['arcs']], [('A', 'B'), ('B', 'A')])
        self.assertEqual(p['arcs'][0]['travel_geometry'], list(reversed(p['arcs'][1]['travel_geometry'])))

    def test_parallel_roads_preserved(self):
        p = build_routing_network(registry(road(), road(rid='HN-002'))).to_dict()
        self.assertEqual([a['road_id'] for a in p['arcs']], ['HN-001', 'HN-002'])
        self.assertEqual(p['outgoing']['A'], [0, 1])

    def test_outgoing_branch_without_reverse(self):
        p = build_routing_network(registry(road(), road(rid='HN-002', b='C'))).to_dict()
        self.assertEqual(p['outgoing'], {'A': [0, 1], 'B': [], 'C': []})

    def test_order_independent_object_dict(self):
        source = registry(road('both'), road('reverse', 'HN-002', 'B', 'C'))
        raw = source.to_dict()
        raw['roads'].reverse()
        before = copy.deepcopy(raw)
        a = build_routing_network(source)
        b = build_routing_network(raw)
        self.assertEqual(a.to_json(), b.to_json())
        self.assertEqual(a.checksum(), b.checksum())
        self.assertEqual(raw, before)
        self.assertEqual(source.to_dict()['roads'][0]['coordinates'], [list(c) for c in COORDS])

    def test_expected_checksum(self):
        source = registry()
        raw = dict(source.to_dict(), registry_checksum=source.checksum)
        build_routing_network(raw, expected_registry_checksum=source.checksum)
        for bad in ('b' * 64, '', True):
            with self.assertRaises(IntegrationContractError):
                build_routing_network(source, expected_registry_checksum=bad)
        raw['registry_checksum'] = 'c' * 64
        with self.assertRaises(IntegrationContractError):
            build_routing_network(raw)

    def test_self_loop_rejected_not_dropped(self):
        source = registry(road(a='A', b='A'))
        with self.assertRaises(IntegrationContractError) as caught:
            build_routing_network(source)
        self.assertEqual(caught.exception.code, 'INVALID_CONTRACT')

    def test_mixed_network(self):
        raw = registry().to_dict()
        raw['roads'][0]['network_version'] = 'other'
        with self.assertRaises(IntegrationContractError) as caught:
            build_routing_network(raw)
        self.assertEqual(caught.exception.code, 'NETWORK_VERSION_MISMATCH')

    def test_invalid_direction(self):
        raw = registry().to_dict()
        raw['roads'][0]['directionality'] = 'sideways'
        with self.assertRaises(IntegrationContractError) as caught:
            build_routing_network(raw)
        self.assertEqual(caught.exception.code, 'INVALID_CONTRACT')

    def test_data_validation_translated(self):
        for field, value in [('length_km', 0), ('length_km', float('nan')),
                             ('coordinates', [[21, 105]]), ('coordinates', [[{}, 0], [21, 105]]),
                             ('road_id', 'bad'), ('endpoint_a', None)]:
            raw = registry().to_dict()
            raw['roads'][0][field] = value
            with self.subTest(field=field), self.assertRaises(IntegrationContractError) as caught:
                build_routing_network(raw)
            self.assertEqual(caught.exception.code, 'INVALID_CONTRACT')
            self.assertNotIn('Traceback', str(caught.exception.to_dict()))

    def test_empty_duplicate_missing_and_wrong_type(self):
        for raw in [None, [], {'network_version': 'test-v1', 'roads': []},
                    {'network_version': 'test-v1', 'roads': [road().to_dict()] * 2},
                    {'network_version': 'test-v1', 'roads': [{'road_id': 'HN-001'}]}]:
            with self.assertRaises(IntegrationContractError):
                build_routing_network(raw)

    def test_osm_fixture_directions_and_checksum_offline(self):
        with patch('socket.socket', side_effect=AssertionError('network')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('HTTP')):
            source = build_road_network(read_overpass(FIXTURE)).registry
            self.assertIsNotNone(source)
            before = source.to_dict()
            result = build_routing_network(source)
            p = result.to_dict()
            self.assertEqual(p['network_version'], source.network_version)
            self.assertEqual(p['registry_checksum'], source.checksum)
            self.assertEqual(len(p['arcs']), len(source))  # no extra reverse arcs
            self.assertEqual({a['road_id'] for a in p['arcs']}, {r.road_id for r in source})
            for arc in p['arcs']:
                r = source.get(arc['road_id'])
                reverse = r.directionality == 'reverse'
                self.assertEqual((arc['travel_from'], arc['travel_to']),
                                 (r.endpoint_b, r.endpoint_a) if reverse else (r.endpoint_a, r.endpoint_b))
                self.assertEqual(arc['travel_geometry'], [list(c) for c in
                                 (reversed(r.coordinates) if reverse else r.coordinates)])
            raw = source.to_dict()
            raw['roads'].reverse()
            self.assertEqual(result.checksum(), build_routing_network(raw).checksum())
            self.assertEqual(source.to_dict(), before)

    def test_demo_both_registry(self):
        from vietsafe.data_pipeline.adapters.demo import load_demo_registry
        source = load_demo_registry()
        result = build_routing_network(source).to_dict()
        self.assertEqual(len(result['arcs']), 2 * len(source))
        self.assertEqual({a['road_id'] for a in result['arcs']}, {r.road_id for r in source})

    def test_no_forecast_graph_or_solver_calls(self):
        with patch('vietsafe.data_pipeline.features.graph.build_graph', side_effect=AssertionError('Forecast graph')), \
             patch('vietsafe.core.routing.calculate_routes', side_effect=AssertionError('Routing')), \
             patch('vietsafe.core.forecast.forecast', side_effect=AssertionError('Forecast')), \
             patch('socket.socket', side_effect=AssertionError('network')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('HTTP')):
            build_routing_network(registry())

    def test_import_safety(self):
        script = '''
import sys, socket, urllib.request
from unittest.mock import patch

def audit(event, args):
    if event == 'open':
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & 3):
            raise AssertionError('write')
    if event in ('os.mkdir', 'sqlite3.connect', 'socket.connect', 'socket.__new__'):
        raise AssertionError(event)
sys.addaudithook(audit)
with patch.object(socket, 'socket', side_effect=AssertionError('socket')), patch.object(urllib.request, 'urlopen', side_effect=AssertionError('HTTP')):
    import vietsafe.integration.routing_contracts
    import vietsafe.integration.registry_routing
assert not any(m in sys.modules for m in ['vietsafe.integration.contracts', 'vietsafe.data_pipeline.features.graph', 'vietsafe.core.routing', 'vietsafe.core.forecast', 'vietsafe.db'])
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True,
                                cwd=Path(__file__).resolve().parents[2], env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
