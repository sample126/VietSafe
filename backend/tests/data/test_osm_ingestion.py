import contextlib
import hashlib
import importlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

from vietsafe.data_pipeline.ingestion import osm

FIXTURE = Path(__file__).resolve().parents[3] / "data/fixtures/osm/overpass-small.json"
BBOX = (21.03, 105.80, 21.032, 105.802)


class OSMIngestionTests(unittest.TestCase):
    def test_bbox_valid_and_numeric_normalization(self):
        self.assertEqual(osm.validate_bbox(BBOX), BBOX)
        self.assertEqual(osm.validate_bbox([0, 0, 0.01, 0.01]), (0., 0., 0.01, 0.01))

    def test_bbox_invalid(self):
        for bounds in ((1, 2, 3), (2, 1, 1, 2), (1, 2, 2, 1),
                       (91, 1, 92, 2), (0, 180, .01, 181), (0, 0, 1, 1),
                       (0, 0, .05, .05), (0, 0, .06, .001),
                       (0, 0, float('nan'), .01), (False, 0, .01, .01),
                       ('0', 0, .01, .01), (0, 0, 10**400, 1)):
            with self.subTest(bounds=bounds), self.assertRaises(osm.OSMInputError):
                osm.validate_bbox(bounds)

    def test_query_exact_and_deterministic(self):
        expected = '[out:json][timeout:25];way["highway"](21.03,105.8,21.032,105.802);(._;>;);out meta;'
        self.assertEqual(osm.build_query(BBOX), expected)
        self.assertEqual(osm.build_query(list(BBOX)), expected)

    def test_timeout_limits(self):
        for timeout in (0, 61, True, 2.5, '25'):
            with self.subTest(timeout=timeout), self.assertRaises(osm.OSMInputError):
                osm.build_query(BBOX, timeout)

    def test_fixture_parsing_without_http(self):
        with patch.object(osm, 'urlopen', side_effect=AssertionError('No HTTP')), \
                patch('socket.socket', side_effect=AssertionError('No network')):
            data = osm.read_overpass(FIXTURE)
        self.assertEqual(len(data.nodes), 13)
        self.assertEqual(len(data.ways), 7)
        self.assertEqual(data.quarantine, ())
        self.assertEqual(data.nodes[1].latitude, 21.03)
        self.assertEqual(data.ways[100].nodes, (1, 2, 3))
        self.assertEqual(data.ways[300].tags['oneway'], 'yes')
        self.assertEqual(json.loads(data.ways[100].metadata_json)['version'], 1)
        self.assertIn('not production', data.provenance['fixture_notice'])

    def test_raw_checksum_exact_bytes(self):
        raw = FIXTURE.read_bytes()
        a, b = osm.parse_overpass(raw), osm.parse_overpass(raw)
        self.assertEqual(a.raw_checksum, hashlib.sha256(raw).hexdigest())
        self.assertEqual(a.provenance, b.provenance)
        self.assertNotEqual(a.raw_checksum, osm.parse_overpass(raw + b' ').raw_checksum)

    def test_malformed_json_and_missing_elements(self):
        for raw in (b'{', b'[]', b'{}', b'{"elements":null}', b'\xff',
                    b'{"elements":[],"x":NaN}', b'{"elements":[],"elements":[]}',
                    b'{"elements":[],"x":1e400}',
                    b'{"elements":[],"remark":"runtime timeout"}'):
            with self.subTest(raw=raw), self.assertRaises(osm.OSMInputError):
                osm.parse_overpass(raw)

    def test_payload_size_limit(self):
        with patch.object(osm, 'MAX_BYTES', 3), self.assertRaises(osm.OSMInputError):
            osm.parse_overpass(b'{"elements":[]}')

    def test_invalid_ids_types_coordinates_and_refs_quarantined(self):
        elements = [dict(type='way', id='12', nodes=[1, 2]),
                    dict(type='node', id=True, lat=21, lon=105),
                    dict(type='node', id=2, lat=91, lon=105),
                    dict(type='way', id=3, nodes=[1]),
                    dict(type='way', id=4, nodes=[1, False]),
                    dict(type='way', id=5, nodes=[1, 2], tags={'highway': 3}),
                    None, dict(type='relation', id=1)]
        data = osm.parse_overpass(json.dumps({'elements': elements}))
        self.assertEqual(len(data.quarantine), len(elements))
        self.assertEqual(set(q.code for q in data.quarantine), {
            'INVALID_WAY_ID', 'INVALID_NODE_ID', 'INVALID_NODE_COORDINATE',
            'INSUFFICIENT_NODES', 'INVALID_NODE_REFERENCE', 'INVALID_TAGS', 'UNSUPPORTED_ELEMENT'})

    def test_duplicate_identical_payload_deduplicated(self):
        node = dict(type='node', id=1, lat=21., lon=105.)
        data = osm.parse_overpass(json.dumps({'elements': [node, node]}))
        self.assertEqual(len(data.nodes), 1)
        self.assertEqual(data.quarantine, ())

    def test_duplicate_conflict_excludes_both_order_independent(self):
        for kind, first, second in (
            ('node', dict(type='node', id=1, lat=21, lon=105),
             dict(type='node', id=1, lat=22, lon=105)),
            ('way', dict(type='way', id=1, nodes=[1, 2]),
             dict(type='way', id=1, nodes=[2, 3])),
        ):
            for items in ([first, second], [second, first]):
                data = osm.parse_overpass(json.dumps({'elements': items}))
                self.assertEqual(len(data.nodes) + len(data.ways), 0)
                self.assertEqual(data.quarantine[0].code, 'DUPLICATE_PAYLOAD_CONFLICT')
                self.assertEqual(data.quarantine[0].entity, kind)

    def test_import_has_no_http(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('No HTTP')):
            importlib.reload(osm)

    def test_explicit_fetch_mock_checks_request_and_provenance(self):
        class Response(io.BytesIO):
            def geturl(self):
                return 'https://example.test/api/interpreter'

        with patch.object(osm, 'urlopen', return_value=Response(FIXTURE.read_bytes())) as call:
            data = osm.fetch_overpass(BBOX, endpoint='https://example.test/api/interpreter', timeout=12)
        call.assert_called_once()
        request = call.call_args.args[0]
        self.assertEqual(call.call_args.kwargs['timeout'], 17)
        self.assertEqual(request.get_header('User-agent'), osm.USER_AGENT)
        self.assertEqual(parse_qs(request.data.decode())['data'][0], osm.build_query(BBOX, 12))
        self.assertEqual(data.provenance['bbox'], list(BBOX))
        self.assertEqual(data.provenance['endpoint'], 'https://example.test/api/interpreter')

    def test_invalid_endpoint_does_not_request(self):
        with patch.object(osm, 'urlopen') as call:
            for endpoint in ('file:///tmp/input', 'https://user:pass@example.org/x',
                             'https://example.org/x?token=x', 'https:///x'):
                with self.subTest(endpoint=endpoint), self.assertRaises(osm.OSMInputError):
                    osm.fetch_overpass(BBOX, endpoint=endpoint)
            call.assert_not_called()

    def test_cli_offline_no_network_summary_output_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp, \
                patch.object(osm, 'urlopen', side_effect=AssertionError('No HTTP')), \
                patch('socket.socket', side_effect=AssertionError('No network')):
            target = Path(temp) / 'registry.json'
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(osm.main(['--input', str(FIXTURE)]), 0)
            self.assertEqual(list(Path(temp).iterdir()), [])
            self.assertEqual(json.loads(output.getvalue())['directed_roads'], 12)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(osm.main(['--input', str(FIXTURE), '--output', str(target)]), 0)
                before = target.read_bytes()
                self.assertEqual(osm.main(['--input', str(FIXTURE), '--output', str(target)]), 2)
            self.assertEqual(target.read_bytes(), before)
            self.assertEqual(len(json.loads(before)['registry']['roads']), 12)

    def test_cli_module_help_and_fixture(self):
        prefix = [sys.executable, '-m', 'vietsafe.data_pipeline.ingestion.osm']
        cwd = Path(__file__).resolve().parents[2]
        help_result = subprocess.run(prefix + ['--help'], cwd=cwd, capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertIn('--bbox', help_result.stdout)
        result = subprocess.run(prefix + ['--input', str(FIXTURE)], cwd=cwd,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['directed_roads'], 12)
