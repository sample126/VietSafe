import copy
import hashlib
import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from vietsafe.data_pipeline.environment import EnvironmentalGrid, EnvironmentInputError, utc_timestamp
from vietsafe.data_pipeline.ingestion.gpm import read_gpm

FIXTURE = Path(__file__).resolve().parents[3] / "data/fixtures/environment/gpm/gpm-grid.json"


class EnvironmentalGridTests(unittest.TestCase):
    def setUp(self):
        self.payload = read_gpm(FIXTURE).to_dict()

    def invalid(self, **changes):
        payload = copy.deepcopy(self.payload)
        payload.update(changes)
        with self.assertRaises(EnvironmentInputError):
            EnvironmentalGrid.from_dict(payload)

    def test_dimensions(self):
        for rows, cols in ((0, 3), (-1, 3), (True, 3), (3, '3'), (3.0, 3), (10**400, 3)):
            with self.subTest(rows=rows, cols=cols):
                self.invalid(rows=rows, cols=cols)

    def test_shape(self):
        for values in (None, [], [[0]], [[0, 1, 2], [0, 1], [0, 1, 2]], ['abc'] * 3):
            with self.subTest(values=values):
                self.invalid(values=values)

    def test_cell_center_and_orientation(self):
        grid = EnvironmentalGrid.from_dict(self.payload)
        self.assertEqual(grid.cell_center(0, 0), (21.2, 105.5))
        lat, lon = grid.cell_center(2, 2)
        self.assertAlmostEqual(lat, 21)
        self.assertAlmostEqual(lon, 105.7)
        self.assertLess(lat, grid.origin_lat)
        self.assertGreater(lon, grid.origin_lon)

    def test_bad_indexes(self):
        grid = EnvironmentalGrid.from_dict(self.payload)
        for position in ((-1, 0), (3, 0), (0, 3), (True, 0), (0, 0.5)):
            with self.subTest(position=position), self.assertRaises(EnvironmentInputError):
                grid.cell_center(*position)

    def test_coordinates_resolution(self):
        for key, value in (('origin_lat', 91), ('origin_lon', -181), ('lat_step', 0),
                           ('lon_step', 0), ('lat_step', 1), ('lon_step', -1),
                           ('origin_lat', float('nan')), ('lon_step', float('inf')),
                           ('origin_lat', True), ('origin_lon', '105'), ('lat_step', -100)):
            with self.subTest(key=key, value=value):
                self.invalid(**{key: value})

    def test_nonfinite_and_invalid_values(self):
        for value in (float('nan'), float('inf'), float('-inf'), True, '1', {}, 10**400):
            with self.subTest(value=value):
                self.invalid(values=[[value, 0, None], [0, 0, 0], [0, 0, 0]])

    def test_null_and_zero(self):
        grid = EnvironmentalGrid.from_dict(self.payload)
        decoded = json.loads(grid.to_json())
        self.assertIsNone(decoded['values'][0][2])
        self.assertIsNone(decoded['nodata'])
        self.assertEqual(decoded['values'][0][0], 0)
        self.invalid(nodata=-9999)

    def test_canonical_roundtrip_checksum(self):
        grid = EnvironmentalGrid.from_dict(self.payload)
        reordered = dict(reversed(list(self.payload.items())))
        self.assertEqual(grid.to_json(), EnvironmentalGrid.from_dict(reordered).to_json())
        self.assertEqual(grid.checksum(), hashlib.sha256(grid.to_json().encode()).hexdigest())
        self.assertEqual(grid.to_json(), EnvironmentalGrid.from_dict(json.loads(grid.to_json())).to_json())

    def test_checksum_changes_for_data_and_provenance(self):
        original = EnvironmentalGrid.from_dict(self.payload)
        for changes in ({'product_version': 'v2'}, {'raw_checksum': '0' * 64},
                        {'values': [[0, 2, None], [2, 3, 4], [.25, 0, 5]]}):
            changed = EnvironmentalGrid.from_dict({**self.payload, **changes})
            self.assertNotEqual(original.checksum(), changed.checksum())

    def test_immutable_and_defensive_copy(self):
        grid = EnvironmentalGrid.from_dict(self.payload)
        self.payload['values'][0][0] = 9
        self.payload['metadata']['reference'] = 'changed'
        self.assertEqual(grid.values[0][0], 0)
        self.assertNotEqual(grid.metadata['reference'], 'changed')
        with self.assertRaises(TypeError):
            grid.metadata['reference'] = 'changed'
        with self.assertRaises(FrozenInstanceError):
            grid.rows = 4
        exported = grid.to_dict()
        exported['metadata']['reference'] = 'changed'
        self.assertNotEqual(grid.metadata['reference'], 'changed')

    def test_timestamp_normalization(self):
        self.assertEqual(utc_timestamp('2026-10-08T09:30:00+07:00'), '2026-10-08T02:30:00Z')
        self.assertEqual(utc_timestamp('2026-10-08T02:30:00.123Z'), '2026-10-08T02:30:00.123000Z')

    def test_bad_timestamps(self):
        for value in (None, 4, '2026-10-08T02:30:00', '2026-02-30T02:30:00Z',
                      '2026-10-08T02:30:00+07:90', '2026-10-08T02:30:00-00:00',
                      '2026-10-08', 'yesterday'):
            with self.subTest(value=value):
                self.invalid(observed_at=value)
        self.invalid(available_at='2026-10-08T01:00:00Z')

    def test_units_and_source(self):
        for changes in ({'units': 'mm'}, {'variable': 'rain_30m_mm'}, {'source_type': 'nasa'},
                        {'source_type': []}, {'product': ''}, {'product_version': None}):
            self.invalid(**changes)

    def test_provenance(self):
        for checksum in ('xyz', 'A' * 64, None, 3):
            self.invalid(raw_checksum=checksum)
        for uri in ('', '/tmp/data.json', 'https://user:password@example.com/grid'):
            self.invalid(source_uri=uri)

    def test_metadata(self):
        for metadata in (None, [], {}, {'crs': 'EPSG:4326'}):
            self.invalid(metadata=metadata)
        for key, value in (('crs', 'EPSG:3857'), ('grid_registration', 'unknown'),
                           ('reference', ''), ('processing_version', 1), ('extra', float('inf'))):
            self.invalid(metadata={**self.payload['metadata'], key: value})

    def test_strict_fields_and_schema(self):
        self.invalid(schema='vietsafe.environment-grid.v2')
        self.invalid(unexpected=True)
        del self.payload['product']
        with self.assertRaises(EnvironmentInputError):
            EnvironmentalGrid.from_dict(self.payload)

    def test_invalid_unicode_cannot_enter_canonical_output(self):
        self.invalid(product='\ud800')
        self.invalid(metadata={**self.payload['metadata'], 'extra': '\udfff'})
        self.invalid(metadata={**self.payload['metadata'], '\ud800': 'value'})
