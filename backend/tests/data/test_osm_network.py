import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from vietsafe.data_pipeline.ingestion.osm import parse_overpass, read_overpass
from vietsafe.data_pipeline.processing import osm_network as network
from vietsafe.data_pipeline.registry import RoadRegistry

FIXTURE = Path(__file__).resolve().parents[3] / 'data/fixtures/osm/overpass-small.json'


def document(ways, nodes=None):
    if nodes is None:
        nodes = [dict(type='node', id=i, lat=21 + i * .001, lon=105 + (i % 2) * .001)
                 for i in range(1, 10)]
    return parse_overpass(json.dumps({'elements': nodes + ways}))


def way(identity=100, nodes=(1, 2, 3), **tags):
    return dict(type='way', id=identity, nodes=list(nodes),
                tags={'highway': 'residential', **tags})


class OSMFilterTests(unittest.TestCase):
    def test_accepted_highways(self):
        for highway in network.HIGHWAY_TYPES:
            self.assertIsNone(network.filter_reason({'highway': highway}))

    def test_rejected_highways_and_area(self):
        for highway in ('footway', 'path', 'pedestrian', 'cycleway', 'steps', 'construction', ''):
            self.assertEqual(network.filter_reason({'highway': highway}), 'HIGHWAY_EXCLUDED')
        self.assertEqual(network.filter_reason({'highway': 'service', 'area': 'yes'}), 'AREA_EXCLUDED')

    def test_access_restrictions(self):
        for key in network.ACCESS_KEYS:
            for value in ('no', 'private'):
                self.assertIsNotNone(network.filter_reason({'highway': 'residential', key: value}))
        # Conservative policy: explicit broad denial is not overridden in v1.
        self.assertIsNotNone(network.filter_reason({'highway': 'service', 'access': 'no',
                                                    'motor_vehicle': 'yes'}))


class StableOSMIDTests(unittest.TestCase):
    def test_canonical_forward_and_reverse_numeric_comparison(self):
        self.assertEqual(network.canonical_node_path([2, 11, 10]), (2, 11, 10))
        self.assertEqual(network.canonical_node_path([10, 11, 2]), (2, 11, 10))

    def test_exact_hash_and_both_directions(self):
        text = 'way=42;nodes=2,11,10'
        self.assertEqual(network.road_id_hash_input(42, [10, 11, 2]), text)
        digest = hashlib.sha256(text.encode('ascii')).hexdigest()
        for direction in ('f', 'r'):
            self.assertEqual(network.stable_road_id(42, [2, 11, 10], direction),
                             f'osm:v1:42:2:10:{digest}:{direction}')
            self.assertEqual(network.stable_road_id(42, [10, 11, 2], direction),
                             f'osm:v1:42:2:10:{digest}:{direction}')

    def test_id_rejects_invalid_inputs(self):
        for identity, nodes, direction in [(True, [1, 2], 'f'), (0, [1, 2], 'f'),
                                           (1, ['01', 2], 'f'), (1, [1, 2, 1], 'f'),
                                           (1, [1], 'f'), (1, [1, 2], 'x')]:
            with self.subTest(nodes=nodes), self.assertRaises(ValueError):
                network.stable_road_id(identity, nodes, direction)

    def test_ids_do_not_depend_on_names_coordinates_or_input_order(self):
        a = document([way()])
        raw = json.loads(a.raw_payload)
        raw['elements'].reverse()
        for element in raw['elements']:
            if element['type'] == 'node':
                element['lat'] += .0001
            else:
                element['tags']['name'] = 'Changed name'
        b = parse_overpass(json.dumps(raw))
        first, second = network.build_road_network(a), network.build_road_network(b)
        self.assertEqual([r.road_id for r in first.registry], [r.road_id for r in second.registry])
        self.assertNotEqual(first.registry.network_version, second.registry.network_version)

    def test_parallel_paths_and_distinct_ways_have_distinct_ids(self):
        ids = {network.stable_road_id(100, [1, 2, 4], 'f'),
               network.stable_road_id(100, [1, 3, 4], 'f'),
               network.stable_road_id(101, [1, 2, 4], 'f')}
        self.assertEqual(len(ids), 3)


class OSMSegmentationTests(unittest.TestCase):
    def test_intersection_and_endpoints_split(self):
        result = network.build_road_network(document([way(), way(200, [4, 2, 5])]))
        self.assertEqual(len(result.registry), 8)
        paths = {tuple(p['canonical_node_ids']) for p in result.to_dict()['lineage'].values()}
        self.assertEqual(paths, {(1, 2), (2, 3), (2, 4), (2, 5)})

    def test_unshared_internal_node_preserved(self):
        result = network.build_road_network(document([way()]))
        self.assertEqual(len(result.registry), 2)
        self.assertTrue(all(len(r.coordinates) == 3 for r in result.registry))

    def test_filtered_road_does_not_split_network(self):
        result = network.build_road_network(document([way(), way(200, [4, 2, 5], highway='footway')]))
        self.assertEqual(len(result.registry), 2)
        self.assertEqual(result.summary()['filtered_ways'], 1)

    def test_missing_and_invalid_node_quarantine(self):
        data = document([way(nodes=[1, 99]), way(200, [2, 3])])
        result = network.build_road_network(data)
        self.assertIn('MISSING_REFERENCED_NODE', [q['code'] for q in result.to_dict()['quarantine']])
        self.assertEqual(result.summary()['emitted_ways'], 1)
        raw = json.loads(data.raw_payload)
        raw['elements'][0]['lat'] = 100
        result = network.build_road_network(parse_overpass(json.dumps(raw)))
        self.assertIn('INVALID_NODE_COORDINATE', [q['code'] for q in result.to_dict()['quarantine']])

    def test_repeated_node_and_ambiguous_loop_quarantine(self):
        for nodes, code in [([1, 2, 1, 3], 'UNSUPPORTED_TOPOLOGY'),
                            ([1, 2, 1], 'AMBIGUOUS_CLOSED_LOOP'),
                            ([1, 2, 3, 2, 1], 'AMBIGUOUS_CLOSED_LOOP')]:
            result = network.build_road_network(document([way(nodes=nodes)]))
            self.assertIsNone(result.registry)
            self.assertEqual(result.to_dict()['quarantine'][0]['code'], code)

    def test_simple_ring_rotation_stable_ids(self):
        a = network.build_road_network(document([way(nodes=[1, 2, 3, 4, 1], junction='roundabout')]))
        b = network.build_road_network(document([way(nodes=[3, 4, 1, 2, 3], junction='roundabout')]))
        self.assertEqual(len(a.registry), 2)
        self.assertEqual([r.road_id for r in a.registry], [r.road_id for r in b.registry])

    def test_ring_splits_at_all_shared_anchors(self):
        result = network.build_road_network(document([
            way(nodes=[1, 2, 3, 4, 1], junction='roundabout'), way(200, [5, 2]), way(300, [3, 6])]))
        origins = [p for p in result.to_dict()['lineage'].values() if p['osm_way_id'] == 100]
        self.assertEqual(len(origins), 2)
        self.assertTrue(all(set((p['canonical_node_ids'][0], p['canonical_node_ids'][-1])) == {2, 3}
                            for p in origins))

    def test_degenerate_geometry_quarantine(self):
        nodes = [dict(type='node', id=i, lat=21, lon=105) for i in (1, 2)]
        result = network.build_road_network(document([way(nodes=[1, 2])], nodes))
        self.assertIsNone(result.registry)
        self.assertEqual(result.to_dict()['quarantine'][0]['code'], 'INVALID_GEOMETRY')

    def test_id_collision_quarantines_all_candidates(self):
        forced = network.stable_road_id(1, [1, 2], 'f')
        with patch.object(network, 'stable_road_id', return_value=forced):
            result = network.build_road_network(document([way()]))
        self.assertIsNone(result.registry)
        self.assertEqual(result.to_dict()['quarantine'][0]['code'], 'ID_COLLISION')


class OSMDirectionTests(unittest.TestCase):
    def assert_directions(self, nodes, tags, expected):
        result = network.build_road_network(document([way(nodes=nodes, **tags)]))
        self.assertEqual({r.road_id.rsplit(':', 1)[1] for r in result.registry}, set(expected))
        for road in result.registry:
            origin = result.to_dict()['lineage'][road.road_id]
            canonical = origin['canonical_node_ids']
            self.assertEqual(road.endpoint_a, str(canonical[0]))
            self.assertEqual(road.endpoint_b, str(canonical[-1]))
            self.assertEqual(road.directionality, 'forward' if road.road_id.endswith(':f') else 'reverse')
            travel = canonical if road.directionality == 'forward' else canonical[::-1]
            self.assertEqual(origin['travel_node_ids'], travel)

    def test_two_way(self):
        self.assert_directions([3, 2, 1], {}, {'f', 'r'})

    def test_oneway_yes_true_one_respects_original_direction(self):
        for value in ('yes', 'true', '1'):
            self.assert_directions([1, 2, 3], {'oneway': value}, {'f'})
            self.assert_directions([3, 2, 1], {'oneway': value}, {'r'})

    def test_oneway_minus_one(self):
        self.assert_directions([1, 2, 3], {'oneway': '-1'}, {'r'})
        self.assert_directions([3, 2, 1], {'oneway': '-1'}, {'f'})

    def test_roundabout_and_explicit_no(self):
        self.assert_directions([3, 2, 1], {'junction': 'roundabout'}, {'r'})
        self.assert_directions([3, 2, 1], {'junction': 'roundabout', 'oneway': 'no'}, {'f', 'r'})

    def test_implied_motorway_and_override(self):
        self.assert_directions([3, 2, 1], {'highway': 'motorway'}, {'r'})
        self.assert_directions([3, 2, 1], {'highway': 'motorway', 'oneway': 'no'}, {'f', 'r'})

    def test_unsupported_direction_and_conditional_quarantine(self):
        for tags in ({'oneway': 'reversible'}, {'oneway:conditional': 'yes @ (Mo-Fr)'},
                     {'motor_vehicle:forward': 'no'}):
            result = network.build_road_network(document([way(**tags)]))
            self.assertIsNone(result.registry)
            self.assertEqual(result.to_dict()['quarantine'][0]['code'], 'UNSUPPORTED_TOPOLOGY')


class OSMRegistryTests(unittest.TestCase):
    def test_fixture_valid_registry_and_statistics(self):
        result = network.build_road_network(read_overpass(FIXTURE))
        self.assertIsInstance(result.registry, RoadRegistry)
        roads = list(result.registry)
        self.assertEqual(len(roads), 12)
        self.assertEqual(len({r.road_id for r in roads}), 12)
        self.assertTrue(all(r.length_km > 0 and r.source_type == 'osm' for r in roads))
        self.assertEqual(result.summary()['filtered_ways'], 2)
        self.assertEqual(result.summary()['quarantine_count'], 0)

    def test_deterministic_registry_checksum_and_serialization(self):
        data = read_overpass(FIXTURE)
        a, b = network.build_road_network(data), network.build_road_network(data)
        self.assertEqual(a.registry.checksum, b.registry.checksum)
        self.assertEqual(a.to_json(), b.to_json())
        self.assertEqual(json.loads(a.registry_json()), a.registry.to_dict())
        self.assertIn('Đường thử nghiệm', a.to_json())

    def test_network_version_changes_with_processing_policy(self):
        data = read_overpass(FIXTURE)
        a = network.build_road_network(data)
        with patch.object(network, 'PROCESSOR_VERSION', 'osm-network-2.0.0'):
            b = network.build_road_network(data)
        self.assertNotEqual(a.registry.network_version, b.registry.network_version)

    def test_lineage_roundtrip_complete(self):
        data = parse_overpass(FIXTURE.read_bytes(), source='synthetic', bbox=(21.03,105.8,21.04,105.81),
                              query='fixture query metadata only', endpoint='offline')
        payload = network.build_road_network(data).to_dict()
        self.assertEqual(payload['provenance']['raw_sha256'], data.raw_checksum)
        self.assertEqual(payload['provenance']['endpoint'], 'offline')
        self.assertEqual(payload['provenance']['query'], 'fixture query metadata only')
        for origin in payload['lineage'].values():
            for field in ('osm_way_id', 'source_node_ids', 'canonical_node_ids', 'raw_sha256',
                          'processor_version', 'way_metadata', 'node_metadata'):
                self.assertIn(field, origin)

    def test_fallback_name_and_haversine(self):
        result = network.build_road_network(document([way(nodes=[1, 2])]))
        self.assertTrue(all(r.name == 'OSM way 100' for r in result.registry))
        self.assertAlmostEqual(network.length_km(((0,0),(0,1))), 111.195080234, places=6)

    def test_empty_result_reports_without_fabricated_registry(self):
        result = network.build_road_network(document([way(highway='footway')]))
        self.assertIsNone(result.registry)
        self.assertEqual(result.summary()['directed_roads'], 0)
        self.assertEqual(json.loads(result.to_json())['registry'], None)
        with self.assertRaises(ValueError):
            result.registry_json()
