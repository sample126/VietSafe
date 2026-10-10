import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests.data.alignment_helpers import grid, registry, road, ROOT
from vietsafe.data_pipeline.alignment import AlignmentInputError
from vietsafe.data_pipeline.ingestion.osm import read_overpass
from vietsafe.data_pipeline.processing.osm_network import build_road_network
from vietsafe.data_pipeline.processing.spatial_alignment import nearest_cell, sample_road, align_spatial


class SpatialAlignmentTests(unittest.TestCase):
    def test_representative_point_is_used(self):
        r = road()
        point = r.representative_point()
        sample = sample_road(r, grid())
        self.assertEqual((sample.road_lat, sample.road_lon), point)
        self.assertEqual(sample.road_id, r.road_id)
        self.assertEqual(sample.to_dict()['spatial_method'], 'representative-point-nearest-cell-v1')

    def test_nearest_and_negative_lat_step(self):
        g = grid()
        self.assertEqual(nearest_cell(g, 21.0311, 105.8011), (1, 1))
        sample = sample_road(road(21.0311, 105.8011), g)
        self.assertEqual((sample.cell_lat, sample.cell_lon), g.cell_center(1, 1))

    def test_exact_centers(self):
        g = grid()
        for r in range(3):
            for c in range(3):
                self.assertEqual(nearest_cell(g, *g.cell_center(r, c)), (r, c))

    def test_tie_chooses_north_west(self):
        self.assertEqual(nearest_cell(grid(), 21.0315, 105.8005), (0, 0))
        self.assertEqual(nearest_cell(grid(), 21.0305, 105.8015), (1, 1))

    def test_inclusive_half_cell_edges(self):
        g = grid()
        self.assertEqual(nearest_cell(g, 21.0325, 105.7995), (0, 0))
        self.assertEqual(nearest_cell(g, 21.0295, 105.8025), (2, 2))

    def test_outside_never_clamped(self):
        for point in ((21.03250001, 105.8), (21.02949999, 105.8),
                      (21.031, 105.79949999), (21.031, 105.80250001)):
            with self.subTest(point=point), self.assertRaises(AlignmentInputError) as caught:
                nearest_cell(grid(), *point)
            self.assertEqual(caught.exception.code, 'OUTSIDE_GRID')

    def test_outside_record_retains_reason(self):
        sample = sample_road(road(22, 106), grid())
        self.assertEqual(sample.missing_reason, 'OUTSIDE_GRID')
        self.assertIsNone(sample.value)
        self.assertIsNone(sample.grid_row)
        self.assertIsNotNone(sample.grid_checksum)

    def test_nodata_no_neighbor_fill(self):
        sample = sample_road(road(21.032, 105.802), grid())
        self.assertIsNone(sample.value)
        self.assertEqual(sample.missing_reason, 'GRID_NODATA')
        self.assertEqual((sample.grid_row, sample.grid_col), (0, 2))

    def test_zero_preserved(self):
        sample = sample_road(road(), grid())
        self.assertEqual(sample.value, 0)
        self.assertIsNone(sample.missing_reason)

    def test_unsupported_crs(self):
        # The ingestion model already rejects this; exercise the alignment guard too.
        g = grid()
        proxy = SimpleNamespace(**{name: getattr(g, name) for name in
                                 ('origin_lat', 'origin_lon', 'lat_step', 'lon_step', 'rows', 'cols')},
                                metadata={'crs': 'EPSG:3857'})
        with self.assertRaises(AlignmentInputError) as caught:
            nearest_cell(proxy, 21.031, 105.801)
        self.assertEqual(caught.exception.code, 'UNSUPPORTED_CRS')
        with patch('vietsafe.data_pipeline.processing.spatial_alignment.nearest_cell',
                   side_effect=AlignmentInputError('UNSUPPORTED_CRS', 'Unsupported')):
            self.assertEqual(sample_road(road(), g).missing_reason, 'UNSUPPORTED_CRS')

    def test_invalid_points(self):
        for point in ((float('nan'), 105), (21, float('inf')), (True, 105), (91, 105)):
            with self.subTest(point=point), self.assertRaises(AlignmentInputError):
                nearest_cell(grid(), *point)

    def test_iteration_order_and_determinism(self):
        roads = [road(identity='HN-001'), road(21.031, 105.801, 'HN-002')]
        first = align_spatial(registry(*roads), grid())
        second = align_spatial(registry(*reversed(roads)), grid())
        self.assertEqual([s.to_dict() for s in first], [s.to_dict() for s in second])

    def test_directional_ids_remain_separate(self):
        network = build_road_network(read_overpass(ROOT / 'osm/overpass-small.json')).registry
        samples = align_spatial(network, grid())
        by_id = {s.road_id: s for s in samples}
        pairs = [(key, key[:-1] + 'r') for key in by_id if key.endswith(':f') and key[:-1] + 'r' in by_id]
        self.assertTrue(pairs)
        for forward, reverse in pairs:
            self.assertNotEqual(by_id[forward].road_id, by_id[reverse].road_id)
            self.assertEqual((by_id[forward].road_lat, by_id[forward].road_lon),
                             (by_id[reverse].road_lat, by_id[reverse].road_lon))
        self.assertEqual(len(by_id), len(network))
