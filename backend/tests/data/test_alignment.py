import hashlib
import json
import unittest
from unittest.mock import patch

from tests.data.alignment_helpers import A, T, ROOT, grid, registry, road
from vietsafe.data_pipeline.alignment import AlignmentInputError
from vietsafe.data_pipeline.ingestion.dem import read_hgt
from vietsafe.data_pipeline.ingestion.osm import read_overpass
from vietsafe.data_pipeline.processing.alignment import align_environment
from vietsafe.data_pipeline.processing.osm_network import build_road_network


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.network = build_road_network(read_overpass(ROOT / 'osm/overpass-small.json')).registry
        self.dem = read_hgt(ROOT / 'environment/dem/N21E105-mini.hgt', product_version='fixture-v1',
                            source_uri='urn:vietsafe:fixture:dem', fixture_tile='N21E105.hgt')

    def test_end_to_end_identity_and_provenance(self):
        result = align_environment(self.network, dem=self.dem, gpm=[grid()], smap=[grid('smap')], targets=[(T,A)])
        self.assertEqual(result.network_version, self.network.network_version)
        self.assertEqual(result.registry_checksum, self.network.checksum)
        self.assertEqual(len(result.static), len(self.network))
        self.assertEqual(len(result.dynamic), 2 * len(self.network))
        self.assertEqual({v.sample.road_id for v in result.static}, {r.road_id for r in self.network})
        for record in result.dynamic:
            value = record.to_dict()
            source = grid(value['source_type'])
            self.assertEqual(value['source_uri'], source.source_uri)
            self.assertEqual(value['raw_checksum'], source.raw_checksum)
            self.assertEqual(value['source_metadata'], source.to_dict()['metadata'])
            self.assertEqual(value['product_version'], source.product_version)
            self.assertEqual(value['as_of'], A)
            if value['value'] is None:
                self.assertIsNotNone(value['missing_reason'])
        self.assertTrue(any(v.value is not None for v in result.dynamic))
        self.assertEqual(json.loads(result.to_json())['alignment_version'], 'alignment-v1')

    def test_static_not_repeated_per_target(self):
        result = align_environment(self.network, dem=self.dem, targets=[(T,A),('2026-10-08T03:00:00Z',A)])
        self.assertEqual(len(result.static), len(self.network))
        self.assertTrue(all(v.timestamp is None for v in result.static))

    def test_dem_optional(self):
        self.assertEqual(align_environment(registry(), targets=[(T,A)]).static, ())

    def test_missing_sources_explicit(self):
        result = align_environment(registry(), targets=[(T,A)])
        self.assertEqual(len(result.dynamic), 2)
        self.assertTrue(all(v.missing_reason == 'NO_SOURCE_GRID' for v in result.dynamic))
        self.assertEqual(len(result.issues), 2)

    def test_deterministic_across_order(self):
        roads = [road(), road(21.031,105.801,'HN-002')]
        g1, g2 = grid(), grid(product='OTHER-SYNTHETIC-PRODUCT')
        targets = [(T,A), ('2026-10-08T03:00:00Z', A)]
        first = align_environment(registry(*roads), gpm=[g1,g2], targets=targets)
        second = align_environment(registry(*reversed(roads)), gpm=[g2,g1], targets=reversed(targets))
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.checksum(), second.checksum())
        self.assertEqual(first.checksum(), hashlib.sha256(first.to_json().encode()).hexdigest())

    def test_identical_sources_deduplicated(self):
        first = align_environment(registry(), gpm=[grid()], targets=[(T,A)])
        second = align_environment(registry(), gpm=[grid(),grid()], targets=[(T,A),(T,A)])
        self.assertEqual(first.to_json(), second.to_json())

    def test_conflicting_sources_quarantined(self):
        changed = grid(values=[[0,9,None],[2,3,4],[.25,0,5]])
        result = align_environment(registry(), gpm=[grid(),changed], targets=[(T,A)])
        records = [v for v in result.dynamic if v.sample.source_type == 'gpm']
        self.assertEqual(len(records), 2)
        self.assertTrue(all(v.value is None and v.missing_reason == 'SOURCE_CONFLICT' for v in records))
        reverse = align_environment(registry(), gpm=[changed,grid()], targets=[(T,A)])
        self.assertEqual(result.to_json(), reverse.to_json())

    def test_different_products_not_arbitrarily_selected(self):
        result = align_environment(registry(), gpm=[grid(),grid(product='OTHER')], targets=[(T,A)])
        records = [v for v in result.dynamic if v.sample.source_type == 'gpm']
        self.assertEqual(len(records), 2)
        self.assertTrue(all(v.value == 0 for v in records))

    def test_leakage_case_a_and_case_b(self):
        result = align_environment(registry(), gpm=[grid()], targets=[(T,T),(T,A)])
        records = {v.as_of:v for v in result.dynamic if v.sample.source_type == 'gpm'}
        self.assertIsNone(records[T].value)
        self.assertEqual(records[T].missing_reason, 'NOT_AVAILABLE_AS_OF')
        self.assertEqual(records[A].value, 0)
        self.assertEqual(records[A].to_dict()['source_available_at'], A)

    def test_no_input_mutation(self):
        source = grid()
        before = (self.network.to_dict(), source.to_json())
        align_environment(self.network, gpm=[source], targets=[(T,A)])
        self.assertEqual(before, (self.network.to_dict(), source.to_json()))

    def test_no_http(self):
        with patch('socket.socket', side_effect=AssertionError('No network')), \
                patch('urllib.request.urlopen', side_effect=AssertionError('No HTTP')):
            align_environment(self.network, dem=self.dem, gpm=[grid()], smap=[grid('smap')], targets=[(T,A)])

    def test_invalid_inputs(self):
        for options in ({'gpm':[grid('smap')]}, {'dem':grid()}, {'targets':[T]},
                        {'targets':[(T,'2026-10-08T01:00:00Z')]}):
            with self.subTest(options=options), self.assertRaises(AlignmentInputError):
                align_environment(registry(), **options)
