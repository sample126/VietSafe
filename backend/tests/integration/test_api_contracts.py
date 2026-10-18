"""Raw API bundle rejection, serialization and immutability."""

import copy
import hashlib
import unittest
from dataclasses import FrozenInstanceError

from vietsafe.integration.api_contracts import ArtifactApiBundle, SCHEMA
from vietsafe.integration.errors import IntegrationContractError
from .test_api_projection import bundle, forecast


class ApiContractTests(unittest.TestCase):
    def reject(self, p):
        with self.assertRaises(IntegrationContractError):
            ArtifactApiBundle(p)

    def test_schema_and_roundtrip(self):
        b = bundle([forecast()])
        self.assertEqual(b.to_dict()['schema'], SCHEMA)
        self.assertEqual(b.to_dict()['contract_status'], 'draft')
        self.assertEqual(ArtifactApiBundle.from_dict(b.to_dict()).to_json(), b.to_json())
        self.assertEqual(b.checksum(), hashlib.sha256(b.to_json().encode('utf-8')).hexdigest())

    def test_invalid_envelope(self):
        for key, value in [('schema', 'bad'), ('contract_status', 'stable'), ('mode', 'bad'),
                           ('network_version', ''), ('generated_at', '2026-02-30T00:00:00Z')]:
            p = bundle().to_dict()
            p[key] = value
            self.reject(p)

    def test_forbidden_route_and_raw_data_fields(self):
        for field in ('route', 'routes', 'ETA', 'distance', 'warnings', 'routing_cost', 'vehicle',
                       'X', 'X_mask', 'y', 'y_mask', 'labels', 'feature_names', 'adjacency',
                       'soil_grids', 'rain_grids', 'DEM', 'training_split'):
            for target in ('bundle', 'network', 'road', 'forecast', 'forecast_road'):
                p = bundle([forecast()]).to_dict()
                container = {'bundle': p, 'network': p['network'], 'road': p['network']['roads'][0],
                             'forecast': p['forecasts'][0], 'forecast_road': p['forecasts'][0]['roads'][0]}[target]
                container[field] = []
                with self.subTest(field=field, target=target):
                    self.reject(p)

    def test_missing_fields_and_malformed_payloads(self):
        for key in bundle().to_dict():
            p = bundle().to_dict()
            del p[key]
            self.reject(p)
        for p in (None, [], {}, {'x': float('nan')}):
            self.reject(p)

    def test_network_validation_reuses_map_rules(self):
        for key, value in [('geometry', []), ('geometry', [[True, 1], [2, 3]]),
                           ('geometry', [[91, 0], [21, 105]]), ('name', ''),
                           ('directionality', 'bad'), ('source_id', 'internal')]:
            p = bundle().to_dict()
            p['network']['roads'][0][key] = value
            self.reject(p)
        p = bundle().to_dict()
        p['network']['roads'].reverse()
        self.reject(p)
        p = bundle().to_dict()
        p['network']['roads'].append(p['network']['roads'][0])
        self.reject(p)

    def test_raw_horizon_order_duplicates_and_available(self):
        p = bundle([forecast(), forecast(60)]).to_dict()
        p['forecasts'].reverse()
        self.reject(p)
        p = bundle([forecast()]).to_dict()
        p['forecasts'] *= 2
        self.reject(p)
        for hs in ([60, 30], [30, 30], [], [True]):
            p = bundle([forecast()]).to_dict()
            p['available_horizons_minutes'] = hs
            self.reject(p)

    def test_unknown_road_network_and_mode(self):
        for field, value in [('network_version', 'other'), ('mode', 'demo')]:
            p = bundle([forecast()]).to_dict()
            p['forecasts'][0][field] = value
            self.reject(p)
        p = bundle([forecast()]).to_dict()
        p['forecasts'][0]['roads'][0]['road_id'] = 'unknown'
        self.reject(p)

    def test_source_checksum_shape_and_content(self):
        for field in ('integration_context', 'map_network'):
            p = bundle().to_dict()
            p['source_checksums'][field] = 'invalid'
            self.reject(p)
        for value in ({}, {'30': 'bad'}, {'30': 'a' * 64}, {'30': 'a' * 64, '60': 'b' * 64}):
            p = bundle([forecast()]).to_dict()
            p['source_checksums']['forecasts'] = value
            self.reject(p)

    def test_coverage_and_nonfinite_and_undeclared_metrics(self):
        p = bundle([forecast()]).to_dict()
        p['forecasts'][0]['coverage']['predicted'] = 0
        self.reject(p)
        for value in (float('nan'), float('inf'), -float('inf'), True):
            p = bundle([forecast()]).to_dict()
            p['forecasts'][0]['roads'][0]['risk'] = value
            self.reject(p)
        p = bundle([forecast()]).to_dict()
        p['forecasts'][0]['roads'][0]['label'] = 'undeclared'
        self.reject(p)

    def test_deep_frozen_detached(self):
        p = bundle([forecast()]).to_dict()
        before = copy.deepcopy(p)
        b = ArtifactApiBundle(p)
        p['network']['roads'][0]['geometry'].clear()
        b.to_dict()['forecasts'][0]['roads'].clear()
        self.assertEqual(b.to_dict(), before)
        with self.assertRaises(FrozenInstanceError):
            b._json = '{}'
        with self.assertRaises(FrozenInstanceError):
            b.extra = True
