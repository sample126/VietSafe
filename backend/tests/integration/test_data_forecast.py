"""Real Data fixture interoperability plus explicit leakage/offline protections."""

import copy
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.data.feature_helpers import dataset, fixture, feature_rows
from vietsafe.data_pipeline.features.dataset import build_dataset
from vietsafe.integration.data_forecast import build_forecast_input, normalize_forecast_output
from vietsafe.integration.errors import IntegrationContractError
from .helpers import output_metadata


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = dataset()
        assert cls.source.samples

    def test_object_and_dict_same_no_mutation(self):
        before = self.source.to_json()
        raw = self.source.to_dict()
        copy_before = copy.deepcopy(raw)
        first = build_forecast_input(self.source)
        self.assertEqual(first.to_json(), build_forecast_input(raw).to_json())
        self.assertEqual(self.source.to_json(), before)
        self.assertEqual(raw, copy_before)

    def test_strips_targets_recursively_and_marker_values(self):
        raw = self.source.to_dict()
        sample = raw['samples'][0]
        sample.update(y=[987654321.125] * len(raw['road_ids']), y_mask=[True] * len(raw['road_ids']),
                      label_available_at=['SECRET_LABEL_TIME'], label_checksums=['SECRET_LABEL_HASH'],
                      event_ids=['SECRET_EVENT'], labels={'nested': 'SECRET_LABEL_VALUE'})
        raw['target_name'] = 'SECRET_TARGET'
        raw['split'] = {'training': 'SECRET_SPLIT'}
        result = build_forecast_input(raw).to_dict()
        forbidden = {'y', 'y_mask', 'labels', 'label_available_at', 'label_checksums', 'event_ids', 'target_name', 'split'}
        def walk(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & forbidden)
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(result)
        serialized = json.dumps(result)
        self.assertNotIn('SECRET_', serialized)
        self.assertNotIn('987654321.125', serialized)
        self.assertIn('y', sample)  # source untouched

    def test_inference_without_labels(self):
        registry, _, _ = fixture()
        source = build_dataset(registry, feature_rows(), target_name='flood_depth_cm', require_targets=False)
        self.assertTrue(all(value is None for value in source.samples[0].y))
        build_forecast_input(source)

    def test_invalid_dataset_metadata(self):
        for field, value, code in [('schema', 'wrong', 'INVALID_CONTRACT'),
                                   ('feature_version', 'wrong', 'FEATURE_SCHEMA_MISMATCH'),
                                   ('graph_checksum', 'c' * 64, 'INVALID_CONTRACT'),
                                   ('network_version', 'wrong', 'NETWORK_VERSION_MISMATCH'),
                                   ('horizon_steps', 3, 'UNSUPPORTED_HORIZON')]:
            raw = self.source.to_dict()
            raw[field] = value
            with self.subTest(field=field), self.assertRaises(IntegrationContractError) as caught:
                build_forecast_input(raw)
            self.assertEqual(caught.exception.code, code)

    def test_independent_road_order_rejected(self):
        raw = self.source.to_dict()
        raw['road_ids'].reverse()
        with self.assertRaises(IntegrationContractError):
            build_forecast_input(raw)

    def test_missing_sample_and_fields(self):
        for index in (-1, 999, True, '0'):
            with self.assertRaises(IntegrationContractError):
                build_forecast_input(self.source, index)
        raw = self.source.to_dict()
        del raw['samples'][0]['X']
        with self.assertRaises(IntegrationContractError):
            build_forecast_input(raw)

    def test_malformed_source_sample(self):
        for field, value in [('X', []), ('X_mask', []), ('history_timestamps', []),
                             ('feature_as_of', [])]:
            raw = self.source.to_dict()
            raw['samples'][0][field] = value
            with self.subTest(field=field), self.assertRaises(IntegrationContractError):
                build_forecast_input(raw)

    def test_no_targets_hidden_in_graph(self):
        raw = self.source.to_dict()
        raw['graph']['labels'] = {'secret': 999}
        with self.assertRaises(IntegrationContractError):
            build_forecast_input(raw)

    def test_partial_coverage_only_adds_unavailable(self):
        metadata = output_metadata()
        rows = [dict(road_id='one', status='MISSING_INPUT', reason_code='MISSING_INPUT')]
        before = copy.deepcopy(rows)
        result = normalize_forecast_output(metadata, rows, network_version='fixture-v1', road_ids=['one', 'two'])
        self.assertEqual(rows, before)
        data = result.to_dict()
        self.assertEqual(data['roads'][1], dict(road_id='two', status='UNAVAILABLE', reason_code='UNAVAILABLE'))
        self.assertEqual(data['coverage'], dict(total=2, predicted=0, missing_input=1, unavailable=1, stale=0))

    def test_empty_producer_and_empty_scope(self):
        for scope in ([], ['one']):
            result = normalize_forecast_output(output_metadata(), [], network_version='fixture-v1', road_ids=scope)
            self.assertEqual(result.to_dict()['coverage']['unavailable'], len(scope))

    def test_normalization_rejects_unknown_duplicate_and_network(self):
        for roads, scope, network, code in [
            ([dict(road_id='unknown', status='UNAVAILABLE', reason_code='UNAVAILABLE')], ['one'], 'fixture-v1', 'UNKNOWN_ROAD'),
            ([dict(road_id='one', status='UNAVAILABLE', reason_code='UNAVAILABLE')] * 2, ['one'], 'fixture-v1', 'INVALID_CONTRACT'),
            ([], ['one'], 'other', 'NETWORK_VERSION_MISMATCH')]:
            with self.assertRaises(IntegrationContractError) as caught:
                normalize_forecast_output(output_metadata(), roads, network_version=network, road_ids=scope)
            self.assertEqual(caught.exception.code, code)

    def test_entrypoints_offline_no_forecast(self):
        with patch('socket.socket', side_effect=AssertionError('network')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('HTTP')), \
             patch('vietsafe.core.forecast.forecast', side_effect=AssertionError('forecast called')), \
             patch('vietsafe.core.simulation.build_snapshot', side_effect=AssertionError('simulation called')):
            build_forecast_input(self.source)
            normalize_forecast_output(output_metadata(), [], network_version='fixture-v1', road_ids=['one'])

    def test_import_safety_fresh_interpreter(self):
        script = '''
import sys, socket, urllib.request
from unittest.mock import patch

def audit(event, args):
    if event == 'open':
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & 3):
            raise AssertionError('write on import')
    if event in ('os.mkdir', 'sqlite3.connect', 'socket.connect', 'socket.__new__'):
        raise AssertionError(event)
sys.addaudithook(audit)
with patch.object(socket, 'socket', side_effect=AssertionError('network')), patch.object(urllib.request, 'urlopen', side_effect=AssertionError('HTTP')):
    import vietsafe.integration
    import vietsafe.integration.contracts
    import vietsafe.integration.data_forecast
assert not any(name in sys.modules for name in ['vietsafe.core.forecast', 'vietsafe.core.simulation', 'vietsafe.core.routing', 'vietsafe.db', 'vietsafe.service'])
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                                capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2])
        self.assertEqual(result.returncode, 0, result.stderr)
