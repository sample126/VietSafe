import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vietsafe.data_pipeline.environment import EnvironmentInputError
from vietsafe.data_pipeline.ingestion.dem import read_hgt, tile_coordinates

FIXTURE = Path(__file__).resolve().parents[3] / "data/fixtures/environment/dem/N21E105-mini.hgt"
OPTIONS = dict(product_version='fixture-v1', source_uri='urn:vietsafe:fixture:dem', fixture_tile='N21E105.hgt')


class DEMIngestionTests(unittest.TestCase):
    def test_tile_hemispheres(self):
        for name, expected in (('N21E105.hgt', (21, 105)), ('N21W105.hgt', (21, -105)),
                               ('S21E105.hgt', (-21, 105)), ('S21W105.hgt', (-21, -105))):
            self.assertEqual(tile_coordinates(name), expected)

    def test_tile_names_rejected(self):
        for name in ('N21E105-mini.hgt', 'N90E105.hgt', 'N21E180.hgt', 'S91W181.hgt',
                     'N1E105.hgt', 'n21e105.hgt', '../N21E105.hgt', None):
            with self.subTest(name=name), self.assertRaises(EnvironmentInputError):
                tile_coordinates(name)

    def test_signed_int16_and_nodata(self):
        grid = read_hgt(FIXTURE, **OPTIONS)
        self.assertEqual(grid.values, ((100, 200, 300), (0, None, 30), (-10, 20, 40)))
        self.assertEqual(grid.units, 'm')
        self.assertEqual(grid.variable, 'elevation')
        self.assertIsNone(json.loads(grid.to_json())['values'][1][1])

    def test_orientation_spacing(self):
        grid = read_hgt(FIXTURE, **OPTIONS)
        self.assertEqual(grid.cell_center(0, 0), (22, 105))
        self.assertEqual(grid.cell_center(2, 2), (21, 106))
        self.assertEqual(grid.cell_center(1, 1), (21.5, 105.5))
        self.assertEqual(grid.metadata['grid_registration'], 'point')

    def test_south_west_orientation(self):
        grid = read_hgt(FIXTURE, **{**OPTIONS, 'fixture_tile': 'S21W105.hgt'})
        self.assertEqual(grid.cell_center(0, 0), (-20, -105))
        self.assertEqual(grid.cell_center(2, 2), (-21, -104))

    def test_static_provenance_and_checksum(self):
        grid = read_hgt(FIXTURE, **OPTIONS)
        self.assertIsNone(grid.observed_at)
        self.assertIsNone(grid.available_at)
        self.assertEqual(grid.metadata['temporal_semantics'], 'static')
        self.assertTrue(grid.metadata['is_test_fixture'])
        self.assertIn('NOT A REAL SRTM TILE', grid.metadata['fixture_notice'])
        self.assertEqual(grid.raw_checksum, hashlib.sha256(FIXTURE.read_bytes()).hexdigest())

    def test_determinism_across_temporary_paths(self):
        first = read_hgt(FIXTURE, **OPTIONS)
        with tempfile.TemporaryDirectory() as directory:
            alternate = Path(directory) / 'different-location.hgt'
            alternate.write_bytes(FIXTURE.read_bytes())
            second = read_hgt(alternate, **OPTIONS)
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.checksum(), second.checksum())

    def test_bad_sizes(self):
        for raw in (b'', b'\x00', b'\x00\x00', b'\x00' * 12):
            with self.subTest(length=len(raw)), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'N21E105.hgt'
                path.write_bytes(raw)
                with self.assertRaises(EnvironmentInputError):
                    read_hgt(path, **OPTIONS)

    def test_production_rejects_mini(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'N21E105.hgt'
            path.write_bytes(FIXTURE.read_bytes())
            with self.assertRaises(EnvironmentInputError):
                read_hgt(path, product_version='v3', source_uri='urn:test:srtm')
        with self.assertRaises(EnvironmentInputError):
            read_hgt(FIXTURE, product_version='v3', source_uri='urn:test:srtm')

    def test_production_1201_tile(self):
        # Generated temporary format sample, never a committed/downloaded real tile.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'N21E105.hgt'
            path.write_bytes(struct.pack('>h', 12) * (1201 * 1201))
            grid = read_hgt(path, product_version='synthetic-format-test', source_uri='urn:test:srtm')
        self.assertEqual((grid.rows, grid.cols), (1201, 1201))
        self.assertEqual(grid.cell_center(1200, 1200), (21, 106))
        self.assertEqual(grid.values[-1][-1], 12)

    def test_fixture_dimension_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'large-fixture.hgt'
            path.write_bytes(b'\0\0' * (33 * 33))
            with self.assertRaises(EnvironmentInputError):
                read_hgt(path, **OPTIONS)

    def test_no_network_or_implicit_output(self):
        before = set(FIXTURE.parent.iterdir())
        with patch('socket.socket', side_effect=AssertionError('No network')):
            read_hgt(FIXTURE, **OPTIONS)
        self.assertEqual(before, set(FIXTURE.parent.iterdir()))

    def test_cli_help_summary_and_no_overwrite(self):
        command = [sys.executable, '-m', 'vietsafe.data_pipeline.ingestion.dem']
        self.assertEqual(subprocess.run(command + ['--help'], capture_output=True).returncode, 0)
        args = ['--input', str(FIXTURE), '--fixture-tile', 'N21E105.hgt',
                '--product-version', 'fixture-v1', '--source-uri', OPTIONS['source_uri']]
        run = subprocess.run(command + args, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['rows'], 3)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'grid.json'
            self.assertEqual(subprocess.run(command + args + ['--output', str(output)],
                                            capture_output=True).returncode, 0)
            original = output.read_bytes()
            self.assertEqual(subprocess.run(command + args + ['--output', str(output)],
                                            capture_output=True).returncode, 2)
            self.assertEqual(output.read_bytes(), original)
