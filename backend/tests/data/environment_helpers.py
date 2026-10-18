"""Shared environmental interchange assertions, isolated from backend helpers."""

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

from vietsafe.data_pipeline.environment import EnvironmentInputError

ROOT = Path(__file__).resolve().parents[3] / 'data/fixtures/environment'


class InterchangeChecks:
    """Mixin tested independently against each public source loader."""

    def setUp(self):
        self.fixture = ROOT / self.source / f'{self.source}-grid.json'
        self.payload = json.loads(self.fixture.read_text(encoding='utf-8'))

    def load_payload(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.json'
            path.write_text(json.dumps(payload), encoding='utf-8')
            return self.loader(path)

    def assert_invalid(self, payload):
        with self.assertRaises(EnvironmentInputError):
            self.load_payload(payload)

    def test_fixture(self):
        grid = self.loader(self.fixture)
        self.assertEqual((grid.rows, grid.cols), (3, 3))
        self.assertEqual(grid.source_type, self.source)
        self.assertEqual(grid.units, self.units)
        self.assertEqual(grid.variable, self.variable)
        self.assertTrue(grid.metadata['is_test_fixture'])
        self.assertIn('not NASA production', grid.metadata['fixture_notice'])

    def test_null_zero_preserved(self):
        grid = self.loader(self.fixture)
        self.assertEqual(grid.values[0][0], 0)
        self.assertIsNone(grid.values[0][2])
        self.assertIsNone(json.loads(grid.to_json())['values'][0][2])

    def test_raw_checksum_and_determinism(self):
        first = self.loader(self.fixture)
        self.assertEqual(first.raw_checksum, hashlib.sha256(self.fixture.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'other.json'
            path.write_bytes(self.fixture.read_bytes())
            second = self.loader(path)
        self.assertEqual(first.to_json(), second.to_json())
        self.assertEqual(first.checksum(), second.checksum())

    def test_utc_normalization(self):
        self.payload['observed_at'] = '2026-10-08T09:30:00+07:00'
        self.payload['available_at'] = '2026-10-08T11:00:00+07:00'
        grid = self.load_payload(self.payload)
        self.assertEqual(grid.observed_at, '2026-10-08T02:30:00Z')
        self.assertEqual(grid.available_at, '2026-10-08T04:00:00Z')

    def test_bad_timestamp(self):
        for value in (None, '2026-10-08T02:30:00', 'invalid'):
            self.assert_invalid({**self.payload, 'observed_at': value})

    def test_units_not_guessed(self):
        self.assert_invalid({**self.payload, 'units': 'unknown'})
        payload = copy.deepcopy(self.payload)
        payload['metadata']['original_units'] = 'unknown'
        self.assert_invalid(payload)

    def test_malformed_and_native_bytes_rejected(self):
        for raw in (b'{', b'[]', b'null', b'\x89HDF\r\n\x1a\n', b'\xff'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'invalid.json'
                path.write_bytes(raw)
                with self.assertRaises(EnvironmentInputError):
                    self.loader(path)

    def test_duplicate_keys_rejected(self):
        raw = self.fixture.read_text(encoding='utf-8')
        for text in (raw.replace('"rows": 3', '"rows": 3, "rows": 3'),
                     raw.replace('"crs": "EPSG:4326"', '"crs": "EPSG:4326", "crs": "EPSG:4326"')):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'duplicate.json'
                path.write_text(text, encoding='utf-8')
                with self.assertRaises(EnvironmentInputError):
                    self.loader(path)

    def test_nonfinite_json_rejected(self):
        for literal in ('NaN', 'Infinity', '-Infinity', '1e9999'):
            raw = self.fixture.read_text(encoding='utf-8').replace('null', literal)
            with self.subTest(literal=literal), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'nonfinite.json'
                path.write_text(raw, encoding='utf-8')
                with self.assertRaises(EnvironmentInputError):
                    self.loader(path)

    def test_schema_fields_and_metadata(self):
        for changes in ({'schema': 'v2'}, {'source_type': 'dem'}, {'extra': 1},
                        {'metadata': None}, {'values': [[0]]}, {'raw_checksum': '0' * 64}):
            self.assert_invalid({**self.payload, **changes})
        payload = copy.deepcopy(self.payload)
        del payload['product_version']
        self.assert_invalid(payload)
        payload = copy.deepcopy(self.payload)
        payload['metadata']['processing_version'] = 'unknown'
        self.assert_invalid(payload)

    def test_metadata_provenance_required(self):
        for key in ('reference', 'original_units', 'original_variable', 'processing_version', 'crs'):
            payload = copy.deepcopy(self.payload)
            del payload['metadata'][key]
            self.assert_invalid(payload)

    def test_size_limit(self):
        with patch('vietsafe.data_pipeline.ingestion.environment_json.MAX_JSON_BYTES', 16):
            with self.assertRaises(EnvironmentInputError):
                self.loader(self.fixture)

    def test_no_http_no_implicit_output(self):
        before = set(self.fixture.parent.iterdir())
        with patch('socket.socket', side_effect=AssertionError('No network')), \
                patch('urllib.request.urlopen', side_effect=AssertionError('No HTTP')):
            self.loader(self.fixture)
        self.assertEqual(before, set(self.fixture.parent.iterdir()))

    def test_cli_help_summary_and_exclusive_output(self):
        command = [sys.executable, '-m', f'vietsafe.data_pipeline.ingestion.{self.source}']
        self.assertEqual(subprocess.run(command + ['--help'], capture_output=True).returncode, 0)
        args = ['--input', str(self.fixture)]
        run = subprocess.run(command + args, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['source_type'], self.source)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'grid.json'
            self.assertEqual(subprocess.run(command + args + ['--output', str(output)],
                                            capture_output=True).returncode, 0)
            original = output.read_bytes()
            self.assertEqual(subprocess.run(command + args + ['--output', str(output)],
                                            capture_output=True).returncode, 2)
            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(json.loads(original)['raw_checksum'],
                             hashlib.sha256(self.fixture.read_bytes()).hexdigest())
