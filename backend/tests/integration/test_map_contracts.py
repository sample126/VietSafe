"""Map geometry is canonical display geometry, without runtime presentation state."""

import copy
import hashlib
import unittest
from dataclasses import FrozenInstanceError

from vietsafe.integration.errors import IntegrationContractError
from vietsafe.integration.map_contracts import MapNetwork, MapRoad, SCHEMA


def payload():
    return dict(schema=SCHEMA, contract_status='draft', network_version='test-v1',
                registry_checksum='a' * 64, coordinate_order='lat_lon',
                roads=[dict(road_id='opaque-road', network_version='test-v1', name='Đường thử nghiệm',
                            geometry=[[21, 105], [21.1, 105.2], [21.2, 105.3]], directionality='reverse')])


class MapContractTests(unittest.TestCase):
    def test_valid_network(self):
        result = MapNetwork(payload()).to_dict()
        self.assertEqual(result['schema'], 'vietsafe.map-network.v1')
        self.assertEqual(result['contract_status'], 'draft')
        self.assertEqual(result['coordinate_order'], 'lat_lon')
        self.assertEqual(result['network_version'], 'test-v1')
        self.assertEqual(result['registry_checksum'], 'a' * 64)

    def test_envelope_validation(self):
        for key, value in [('schema', 'wrong'), ('contract_status', 'approved'),
                           ('coordinate_order', 'lon_lat'), ('network_version', ''),
                           ('registry_checksum', 'fake'), ('roads', [])]:
            p = payload()
            p[key] = value
            with self.subTest(key=key), self.assertRaises(IntegrationContractError):
                MapNetwork(p)

    def test_road_required_fields(self):
        for key in ('road_id', 'network_version', 'name'):
            for value in ('', ' ', None, 1):
                road = payload()['roads'][0]
                road[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(IntegrationContractError):
                    MapRoad(road)

    def test_directionality(self):
        for direction in ('forward', 'reverse', 'both'):
            road = payload()['roads'][0]
            road['directionality'] = direction
            self.assertEqual(MapRoad(road).to_dict()['geometry'], road['geometry'])
        road['directionality'] = 'unknown'
        with self.assertRaises(IntegrationContractError):
            MapRoad(road)

    def test_geometry_invalid(self):
        for coords in ([], [[21, 105]], [[21, 105], [21, 105]],
                       [[91, 105], [21, 105]], [[-91, 105], [21, 105]],
                       [[21, 181], [21, 105]], [[21, -181], [21, 105]],
                       [[True, 105], [21, 105]], [[21], [21, 105]],
                       [[float('nan'), 105], [21, 105]], [[21, float('inf')], [21, 105]],
                       [[-float('inf'), 105], [21, 105]]):
            road = payload()['roads'][0]
            road['geometry'] = coords
            with self.subTest(coords=coords), self.assertRaises(IntegrationContractError) as caught:
                MapRoad(road)
            self.assertEqual(caught.exception.code, 'INVALID_CONTRACT')

    def test_geometry_range_boundaries(self):
        road = payload()['roads'][0]
        road['geometry'] = [[-90, -180], [90, 180]]
        MapRoad(road)

    def test_network_mismatch(self):
        p = payload()
        p['roads'][0]['network_version'] = 'other'
        with self.assertRaises(IntegrationContractError) as caught:
            MapNetwork(p)
        self.assertEqual(caught.exception.code, 'NETWORK_VERSION_MISMATCH')

    def test_duplicate_not_deduplicated(self):
        p = payload()
        p['roads'] *= 2
        with self.assertRaises(IntegrationContractError):
            MapNetwork(p)

    def test_unsorted_roads_rejected(self):
        p = payload()
        p['roads'].append(dict(p['roads'][0], road_id='a-first'))
        with self.assertRaises(IntegrationContractError):
            MapNetwork(p)

    def test_non_map_fields_rejected(self):
        for field in ('source_id', 'provenance', 'labels', 'X', 'adjacency', 'lineage', 'risk',
                      'flood_risk', 'speed', 'label', 'forecast', 'horizon', 'model_version'):
            road = payload()['roads'][0]
            road[field] = 'not allowed'
            with self.subTest(field=field), self.assertRaises(IntegrationContractError):
                MapRoad(road)
        for field in ('route', 'ETA', 'distance', 'warnings'):
            p = payload()
            p[field] = 'not allowed'
            with self.subTest(field=field), self.assertRaises(IntegrationContractError):
                MapNetwork(p)

    def test_immutable_detached_and_canonical(self):
        p = payload()
        before = copy.deepcopy(p)
        network = MapNetwork(p)
        same = MapNetwork.from_dict(dict(reversed(list(p.items()))))
        self.assertEqual(network.to_json(), same.to_json())
        self.assertEqual(network.checksum(), hashlib.sha256(network.to_json().encode('utf-8')).hexdigest())
        self.assertIn('Đường', network.to_json())
        p['roads'][0]['geometry'][0][0] = 0
        network.to_dict()['roads'][0]['geometry'].reverse()
        self.assertEqual(network.to_dict(), before)
        with self.assertRaises(FrozenInstanceError):
            network.extra = 1
        road = MapRoad(before['roads'][0])
        before['roads'][0]['geometry'][0][0] = 0
        self.assertEqual(road.to_dict()['geometry'][0][0], 21)
        with self.assertRaises(FrozenInstanceError):
            road._json = '{}'

    def test_malformed_payload(self):
        for p in (None, [], {}, 'text'):
            with self.assertRaises(IntegrationContractError):
                MapNetwork(p)
