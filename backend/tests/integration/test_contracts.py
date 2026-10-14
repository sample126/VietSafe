"""Synthetic structure validation, never model accuracy."""

import copy
import hashlib
import unittest
from dataclasses import FrozenInstanceError

from vietsafe.integration.contracts import DataForecastInput, ForecastOutput, ForecastRoadResult, validate_network_match
from vietsafe.integration.errors import IntegrationContractError
from .helpers import input_payload, output_payload


class ContractTests(unittest.TestCase):
    def reject_input(self, field, value, code='INVALID_CONTRACT'):
        payload = input_payload()
        payload[field] = value
        with self.assertRaises(IntegrationContractError) as caught:
            DataForecastInput(payload)
        self.assertEqual(caught.exception.code, code)

    def test_valid_shape_zero_null_draft(self):
        p = DataForecastInput(input_payload()).to_dict()
        self.assertEqual(p['contract_status'], 'draft')
        self.assertEqual([len(p['X']), len(p['X'][0]), len(p['X'][0][0])], [2, 2, 6])
        self.assertEqual(p['X'][0][0][0], 0)
        self.assertIsNone(p['X'][0][0][1])
        self.assertEqual(p['X_mask'][0][0][:2], [True, False])

    def test_schemas_and_mode(self):
        for field in ['schema', 'source_schema', 'contract_status', 'mode']:
            with self.subTest(field=field):
                self.reject_input(field, 'wrong')

    def test_feature_schema(self):
        for field, value in [('feature_version', 'v99'), ('feature_units', ['x'] * 6),
                             ('feature_names', list(reversed(input_payload()['feature_names'])))]:
            with self.subTest(field=field):
                self.reject_input(field, value, 'FEATURE_SCHEMA_MISMATCH')

    def test_duplicate_features(self):
        self.reject_input('feature_names', ['x'] * 6)

    def test_duplicate_roads(self):
        self.reject_input('road_ids', ['x', 'x'])

    def test_road_order(self):
        self.reject_input('road_ids', list(reversed(input_payload()['road_ids'])))

    def test_graph_checksum(self):
        self.reject_input('graph_checksum', 'c' * 64)

    def test_graph_network(self):
        graph = input_payload()['graph']
        graph['network_version'] = 'other'
        self.reject_input('graph', graph, 'NETWORK_VERSION_MISMATCH')

    def test_graph_shape_edges_and_extensions(self):
        for field, value in [('adjacency', [[0]]), ('directed_edges', []), ('policy', 'normalized'),
                             ('label_checksums', ['secret'])]:
            graph = input_payload()['graph']
            graph[field] = value
            with self.subTest(field=field):
                self.reject_input('graph', graph)

    def test_horizons_30_60(self):
        for steps in (1, 2):
            p = input_payload()
            p.update(horizon_steps=steps, horizon_minutes=steps * 30)
            self.assertEqual(DataForecastInput(p).to_dict()['horizon_minutes'], steps * 30)

    def test_unsupported_horizons(self):
        for value in (15, 45, 90, True, '30'):
            with self.subTest(value=value):
                self.reject_input('horizon_minutes', value, 'UNSUPPORTED_HORIZON')

    def test_invalid_shapes(self):
        for field in ('X', 'X_mask', 'feature_as_of', 'feature_row_checksums'):
            for value in ([], [None], [[[1]]]):
                with self.subTest(field=field, value=value):
                    self.reject_input(field, value)

    def test_numeric_and_masks(self):
        for value, mask in [(None, True), (1, False), (True, True), ('1', True),
                            (float('nan'), True), (float('inf'), True), (-float('inf'), True), (1, 1)]:
            p = input_payload()
            p['X'][0][0][0], p['X_mask'][0][0][0] = value, mask
            with self.subTest(value=value, mask=mask), self.assertRaises(IntegrationContractError):
                DataForecastInput(p)

    def test_history_continuity_and_end(self):
        for history in (['2026-10-08T01:30:00Z', '2026-10-08T02:30:00Z'],
                        ['2026-10-08T01:30:00Z', '2026-10-08T02:00:00Z'], []):
            self.reject_input('history_timestamps', history)

    def test_time_format_and_bin(self):
        for value in ('2026-10-08T02:30:00', '2026-10-08T02:30:00+00:00',
                      '2026-10-08T02:15:00Z', '2026-02-30T02:30:00Z'):
            self.reject_input('issue_time', value)

    def test_future_as_of(self):
        self.reject_input('feature_as_of', [['2026-10-08T03:00:00Z'] * 2] * 2)

    def test_deterministic_immutable_copy(self):
        p = input_payload()
        before = copy.deepcopy(p)
        contract = DataForecastInput(p)
        self.assertEqual(p, before)
        other = DataForecastInput(dict(reversed(list(p.items()))))
        self.assertEqual(contract.to_json(), other.to_json())
        self.assertEqual(contract.checksum(), hashlib.sha256(contract.to_json().encode()).hexdigest())
        p['X'][0][0][0] = 123
        exported = contract.to_dict()
        exported['graph']['adjacency'][0][1] = 0
        self.assertEqual(contract.to_dict(), before)
        with self.assertRaises(FrozenInstanceError):
            contract._json = '{}'

    def test_network_match(self):
        validate_network_match('a', 'a')
        with self.assertRaises(IntegrationContractError) as caught:
            validate_network_match('a', 'b')
        self.assertEqual(caught.exception.code, 'NETWORK_VERSION_MISMATCH')

    def test_error_serialization(self):
        error = IntegrationContractError('INVALID_CONTRACT', 'Bad shape', 'X')
        self.assertEqual(error.to_dict(), dict(code='INVALID_CONTRACT', message='Bad shape', path='X'))

    def test_output_times_30_60_and_publication_delay(self):
        for horizon, target in [(30, '03:00'), (60, '03:30')]:
            p = output_payload()
            p.update(horizon_minutes=horizon, forecast_time=f'2026-10-08T{target}:00Z')
            ForecastOutput(p)
        p['forecast_time'] = '2026-10-08T03:31:00Z'
        with self.assertRaises(IntegrationContractError):
            ForecastOutput(p)

    def test_output_profile(self):
        for mutation in ('missing', 'null', 'undeclared', 'unsupported'):
            p = output_payload()
            if mutation == 'missing':
                del p['roads'][0]['risk']
            elif mutation == 'null':
                p['roads'][0]['risk'] = None
            elif mutation == 'undeclared':
                p['roads'][0]['label'] = 'not declared'
            else:
                p['output_fields'].append('confidence')
            with self.subTest(mutation=mutation), self.assertRaises(IntegrationContractError):
                ForecastOutput(p)

    def test_all_statuses_with_coverage(self):
        for status, group in [('MISSING_INPUT', 'missing_input'), ('UNAVAILABLE', 'unavailable'), ('STALE', 'stale')]:
            p = output_payload()
            p['roads'][0].update(status=status, reason_code=status, risk=None, speed_km_h=None)
            p['coverage']['predicted'] = 0
            p['coverage'][group] = 1
            result = ForecastOutput(p).to_dict()
            self.assertIsNone(result['roads'][0]['risk'])

    def test_status_reason_and_duplicates(self):
        for mutation in ('status', 'reason', 'duplicate'):
            p = output_payload()
            if mutation == 'status':
                p['roads'][0]['status'] = 'SAFE'
            elif mutation == 'reason':
                p['roads'][0]['status'] = 'UNAVAILABLE'
            else:
                p['roads'] *= 2
            with self.subTest(mutation=mutation), self.assertRaises(IntegrationContractError):
                ForecastOutput(p)

    def test_output_nonfinite_and_bool(self):
        for value in [float('nan'), float('inf'), -float('inf'), True]:
            p = output_payload()
            p['roads'][0]['risk'] = value
            with self.subTest(value=value), self.assertRaises(IntegrationContractError):
                ForecastOutput(p)

    def test_coverage_exact_not_just_sum(self):
        p = output_payload()
        p['coverage'].update(predicted=0, unavailable=1)
        with self.assertRaises(IntegrationContractError):
            ForecastOutput(p)

    def test_output_scope(self):
        result = ForecastOutput(output_payload())
        result.validate_scope('fixture-v1', ['fixture-forward'])
        for network, roads, code in [('wrong', ['fixture-forward'], 'NETWORK_VERSION_MISMATCH'),
                                     ('fixture-v1', ['other'], 'UNKNOWN_ROAD'),
                                     ('fixture-v1', ['fixture-forward', 'other'], 'MISSING_INPUT')]:
            with self.assertRaises(IntegrationContractError) as caught:
                result.validate_scope(network, roads)
            self.assertEqual(caught.exception.code, code)

    def test_output_serialization_and_immutability(self):
        p = output_payload()
        result = ForecastOutput(p)
        again = ForecastOutput.from_dict(result.to_dict())
        self.assertEqual(result.to_json(), again.to_json())
        self.assertEqual(result.checksum(), again.checksum())
        p['roads'][0]['risk'] = 99
        self.assertEqual(result.to_dict()['roads'][0]['risk'], 0)
        self.assertEqual(ForecastRoadResult(p['roads'][0]).to_dict()['status'], 'OK')

    def test_boolean_graph_indices_rejected(self):
        p = input_payload()
        p['graph']['directed_edges'][0][1] = True
        with self.assertRaises(IntegrationContractError):
            DataForecastInput(p)

    def test_frozen_no_new_attributes(self):
        result = DataForecastInput(input_payload())
        with self.assertRaises(FrozenInstanceError):
            result.hidden_metadata = {'y': 999}
