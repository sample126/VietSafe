"""Offline actual registries, no RoutingNetwork as source and no runtime integration."""

import copy
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from vietsafe.data_pipeline.registry import RoadRegistry
from vietsafe.data_pipeline.ingestion.osm import read_overpass
from vietsafe.data_pipeline.processing.osm_network import build_road_network
from vietsafe.integration.errors import IntegrationContractError
from vietsafe.integration.registry_map import build_map_network
from .test_registry_routing import road, registry, COORDS, FIXTURE


class RegistryMapTests(unittest.TestCase):
    def test_forward_canonical(self):
        p = build_map_network(registry(road('forward'))).to_dict()
        self.assertEqual(len(p['roads']), 1)
        self.assertEqual(p['roads'][0]['geometry'], [list(c) for c in COORDS])
        self.assertEqual(p['roads'][0]['directionality'], 'forward')

    def test_reverse_still_canonical(self):
        p = build_map_network(registry(road('reverse'))).to_dict()
        self.assertEqual(p['roads'][0]['geometry'], [list(c) for c in COORDS])
        self.assertNotEqual(p['roads'][0]['geometry'], [list(c) for c in reversed(COORDS)])
        self.assertEqual(p['roads'][0]['directionality'], 'reverse')

    def test_both_single_entry(self):
        p = build_map_network(registry(road('both'))).to_dict()
        self.assertEqual(len(p['roads']), 1)
        self.assertEqual(p['roads'][0]['road_id'], 'HN-001')
        self.assertEqual(p['roads'][0]['directionality'], 'both')
        self.assertEqual(p['roads'][0]['geometry'], [list(c) for c in COORDS])

    def test_order_independence_dict_object_and_no_mutation(self):
        source = registry(road('both'), road('reverse', 'HN-002'))
        raw = source.to_dict()
        raw['roads'].reverse()
        before = copy.deepcopy(raw)
        a, b = build_map_network(source), build_map_network(raw)
        self.assertEqual(a.to_json(), b.to_json())
        self.assertEqual(a.checksum(), b.checksum())
        self.assertEqual(raw, before)
        self.assertEqual([r['road_id'] for r in a.to_dict()['roads']], ['HN-001', 'HN-002'])
        raw['roads'][0]['coordinates'][0][0] = 0
        self.assertEqual(a.to_json(), b.to_json())
        self.assertEqual(source.get('HN-002').coordinates, COORDS)

    def test_registry_checksum(self):
        source = registry()
        raw = dict(source.to_dict(), registry_checksum=source.checksum)
        p = build_map_network(raw, expected_registry_checksum=source.checksum).to_dict()
        self.assertEqual(p['registry_checksum'], source.checksum)
        for bad in ('c' * 64, '', True):
            with self.assertRaises(IntegrationContractError):
                build_map_network(source, expected_registry_checksum=bad)
        raw['registry_checksum'] = 'd' * 64
        with self.assertRaises(IntegrationContractError):
            build_map_network(raw)

    def test_duplicate_registry_road(self):
        raw = registry().to_dict()
        raw['roads'] *= 2
        with self.assertRaises(IntegrationContractError) as caught:
            build_map_network(raw)
        self.assertEqual(caught.exception.code, 'INVALID_CONTRACT')

    def test_mixed_network(self):
        raw = registry().to_dict()
        raw['roads'][0]['network_version'] = 'other'
        with self.assertRaises(IntegrationContractError) as caught:
            build_map_network(raw)
        self.assertEqual(caught.exception.code, 'NETWORK_VERSION_MISMATCH')

    def test_bad_registry_geometry_translated(self):
        for coords in ([], [[21, 105]], [[21, 105], [21, 105]], [[91, 105], [21, 105]],
                       [[21, 181], [21, 105]], [[True, 105], [21, 105]],
                       [[21, float('nan')], [21, 105]], [[float('inf'), 105], [21, 105]]):
            raw = registry().to_dict()
            raw['roads'][0]['coordinates'] = coords
            with self.subTest(coords=coords), self.assertRaises(IntegrationContractError) as caught:
                build_map_network(raw)
            self.assertEqual(caught.exception.code, 'INVALID_CONTRACT')
            self.assertNotIn('Traceback', str(caught.exception.to_dict()))

    def test_projection_does_not_expose_internal_fields(self):
        p = build_map_network(registry()).to_dict()
        self.assertEqual(set(p['roads'][0]), {'road_id', 'network_version', 'name', 'geometry', 'directionality'})
        self.assertNotIn('synthetic', p['roads'][0].values())  # source_id sentinel from test source

    def test_osm_fixture_offline(self):
        with patch('socket.socket', side_effect=AssertionError('network')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('HTTP')):
            source = build_road_network(read_overpass(FIXTURE)).registry
            before = source.to_dict()
            result = build_map_network(source)
            p = result.to_dict()
            self.assertEqual(len(p['roads']), len(source))
            self.assertEqual(p['network_version'], source.network_version)
            self.assertEqual(p['registry_checksum'], source.checksum)
            self.assertEqual({r['road_id'] for r in p['roads']}, {r.road_id for r in source})
            for entry in p['roads']:
                original = source.get(entry['road_id'])
                self.assertEqual(entry['geometry'], [list(c) for c in original.coordinates])
                self.assertEqual(entry['directionality'], original.directionality)
                self.assertEqual(entry['name'], original.name)
            raw = source.to_dict()
            raw['roads'].reverse()
            self.assertEqual(result.to_json(), build_map_network(raw).to_json())
            self.assertEqual(result.checksum(), build_map_network(raw).checksum())
            self.assertEqual(source.to_dict(), before)

    def test_demo_36_no_simulation(self):
        from vietsafe.data_pipeline.adapters.demo import load_demo_registry
        with patch('vietsafe.core.simulation.build_snapshot', side_effect=AssertionError('simulation')), \
             patch('socket.socket', side_effect=AssertionError('network')):
            source = load_demo_registry()
            p = build_map_network(source).to_dict()
            self.assertEqual(len(p['roads']), 36)
            self.assertEqual([r['road_id'] for r in p['roads']], [f'HN-{i:03}' for i in range(1, 37)])
            for entry in p['roads']:
                self.assertEqual(entry['directionality'], 'both')
                self.assertEqual(entry['geometry'], [list(c) for c in source.get(entry['road_id']).coordinates])

    def test_no_routing_source_forecast_or_api(self):
        with patch('vietsafe.integration.registry_routing.build_routing_network', side_effect=AssertionError('routing network')), \
             patch('vietsafe.core.routing.calculate_routes', side_effect=AssertionError('route')), \
             patch('vietsafe.core.forecast.forecast', side_effect=AssertionError('forecast')), \
             patch('socket.socket', side_effect=AssertionError('network')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('HTTP')):
            build_map_network(registry())
        with self.assertRaises(IntegrationContractError):
            build_map_network({'schema': 'vietsafe.routing-network.v1', 'arcs': []})

    def test_invalid_registry_shape(self):
        for raw in (None, [], {}, {'network_version': 'test-v1', 'roads': []},
                    {'network_version': 'test-v1', 'roads': [{'road_id': 'HN-001'}]}):
            with self.assertRaises(IntegrationContractError):
                build_map_network(raw)

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
with patch.object(socket, 'socket', side_effect=AssertionError('network')), patch.object(urllib.request, 'urlopen', side_effect=AssertionError('HTTP')):
    import vietsafe.integration.map_contracts
    import vietsafe.integration.registry_map
assert not any(m in sys.modules for m in ['vietsafe.integration.registry_routing', 'vietsafe.integration.routing_contracts', 'vietsafe.integration.contracts', 'vietsafe.core.forecast', 'vietsafe.core.routing', 'vietsafe.core.simulation', 'vietsafe.db', 'vietsafe.service', 'vietsafe.web'])
'''
        p = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True,
                           cwd=Path(__file__).resolve().parents[2], env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(p.returncode, 0, p.stderr)
