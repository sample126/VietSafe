"""Summary shape, deterministic serialization and deep immutability."""

import copy
import hashlib
import unittest
from dataclasses import FrozenInstanceError

from vietsafe.integration.context_contracts import IntegrationContext, SCHEMA
from vietsafe.integration.errors import IntegrationContractError
from .test_context_guard import context, forecast


class ContextContractTests(unittest.TestCase):
    def test_schema_roundtrip(self):
        c = context([forecast()])
        p = c.to_dict()
        self.assertEqual(p['schema'], SCHEMA)
        self.assertEqual(p['contract_status'], 'draft')
        self.assertEqual(IntegrationContext.from_dict(p).to_json(), c.to_json())
        self.assertEqual(c.checksum(), hashlib.sha256(c.to_json().encode('utf-8')).hexdigest())

    def test_envelope_and_forbidden_fields(self):
        for key, value in [('schema', 'bad'), ('contract_status', 'stable'), ('mode', 'live'),
                           ('network_version', ''), ('X', []), ('labels', []), ('adjacency', []),
                           ('routing_cost', 0), ('route', {}), ('risk', 0)]:
            p = context().to_dict()
            p[key] = value
            with self.subTest(key=key), self.assertRaises(IntegrationContractError):
                IntegrationContext(p)

    def test_invalid_road_ids(self):
        for ids in ([], ['A', 'A'], ['B', 'A'], [''], [True], None):
            p = context().to_dict()
            p['road_ids'] = ids
            with self.subTest(ids=ids), self.assertRaises(IntegrationContractError):
                IntegrationContext(p)

    def test_missing_required_fields(self):
        for key in context().to_dict():
            p = context().to_dict()
            del p[key]
            with self.subTest(key=key), self.assertRaises(IntegrationContractError):
                IntegrationContext(p)

    def test_summary_checksums_and_schema(self):
        for artifact in ('map_network', 'routing_network'):
            for key, value in [('schema', 'bad'), ('checksum', 'bad'), ('registry_checksum', None)]:
                p = context().to_dict()
                p['artifacts'][artifact][key] = value
                with self.subTest(artifact=artifact, key=key), self.assertRaises(IntegrationContractError):
                    IntegrationContext(p)

    def test_forecast_summary_consistency(self):
        for key, value in [('schema', 'bad'), ('checksum', 'bad'), ('mode', 'demo'),
                           ('network_version', 'other'), ('model_version', ''), ('issue_time', 'bad'),
                           ('issued_at', 'bad'), ('forecast_time', '2026-10-08T04:00:00Z'),
                           ('horizon_minutes', 15), ('road_ids', ['unknown']), ('coverage', {})]:
            p = context([forecast()]).to_dict()
            p['artifacts']['forecasts'][0][key] = value
            with self.subTest(key=key), self.assertRaises(IntegrationContractError):
                IntegrationContext(p)

    def test_horizon_summary_exact_sorted_unique(self):
        for value in ([], [60, 30], [30, 30], [True], ['30']):
            p = context([forecast(), forecast(60)]).to_dict()
            p['available_horizons_minutes'] = value
            with self.subTest(value=value), self.assertRaises(IntegrationContractError):
                IntegrationContext(p)
        p = context([forecast(), forecast(60)]).to_dict()
        p['artifacts']['forecasts'].reverse()
        with self.assertRaises(IntegrationContractError):
            IntegrationContext(p)

    def test_summary_coverage_counts(self):
        for changes in ({'total': 3}, {'predicted': 3}, {'predicted': True}, {'stale': -1}):
            p = context([forecast()]).to_dict()
            p['artifacts']['forecasts'][0]['coverage'].update(changes)
            with self.assertRaises(IntegrationContractError):
                IntegrationContext(p)

    def test_deep_immutability(self):
        p = context([forecast()]).to_dict()
        before = copy.deepcopy(p)
        c = IntegrationContext(p)
        p['artifacts']['forecasts'][0]['road_ids'].clear()
        c.to_dict()['road_ids'].clear()
        self.assertEqual(c.to_dict(), before)
        with self.assertRaises(FrozenInstanceError):
            c._json = '{}'
        with self.assertRaises(FrozenInstanceError):
            c.extra = True

    def test_malformed_and_nonfinite(self):
        for p in (None, [], {}, {'bad': float('nan')}, {'bad': float('inf')}):
            with self.assertRaises(IntegrationContractError):
                IntegrationContext(p)
