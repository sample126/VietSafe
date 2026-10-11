"""Presentation of synthetic producer outputs; no prediction or routing."""

import copy
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from vietsafe.integration.api_projection import build_artifact_api_bundle
from vietsafe.integration.context_guard import build_integration_context
from vietsafe.integration.contracts import ForecastOutput
from vietsafe.integration.errors import IntegrationContractError
from .test_context_guard import networks, forecast

GENERATED_AT = '2026-10-08T04:12:34Z'


def inputs(fs=(), mode='artifact'):
    m, r = networks()
    c = build_integration_context(mode=mode, map_network=m, routing_network=r, forecasts=fs)
    return dict(context=c, map_network=m, forecasts=fs, generated_at=GENERATED_AT)


def bundle(fs=(), mode='artifact'):
    return build_artifact_api_bundle(**inputs(fs, mode))


class ApiProjectionTests(unittest.TestCase):
    def reject(self, args, code='INVALID_CONTRACT'):
        with self.assertRaises(IntegrationContractError) as caught:
            build_artifact_api_bundle(**args)
        self.assertEqual(caught.exception.code, code)

    def test_no_forecast_full_network_and_hashes(self):
        args = inputs()
        p = build_artifact_api_bundle(**args).to_dict()
        self.assertEqual(len(p['network']['roads']), 3)
        self.assertEqual(p['forecasts'], [])
        self.assertEqual(p['available_horizons_minutes'], [])
        self.assertEqual(p['source_checksums'], dict(integration_context=args['context'].checksum(),
            map_network=args['map_network'].checksum(), forecasts={}))

    def test_30_60_preserve_producer_payloads(self):
        fs = [ForecastOutput(forecast(60)), ForecastOutput(forecast(30))]
        p = bundle(fs).to_dict()
        self.assertEqual(p['available_horizons_minutes'], [30, 60])
        self.assertEqual(p['forecasts'], [fs[1].to_dict(), fs[0].to_dict()])
        self.assertEqual(p['source_checksums']['forecasts'], {'30': fs[1].checksum(), '60': fs[0].checksum()})

    def test_partial_no_synthesized_row(self):
        f = forecast()
        p = bundle([f]).to_dict()
        self.assertEqual(len(p['network']['roads']), 3)
        self.assertEqual(p['forecasts'][0]['roads'], f['roads'])
        self.assertEqual(p['forecasts'][0]['coverage'], f['coverage'])
        self.assertEqual(len(p['forecasts'][0]['roads']), 2)

    def test_all_statuses_missing_and_null_metrics(self):
        for status, group in [('OK', 'predicted'), ('MISSING_INPUT', 'missing_input'),
                              ('UNAVAILABLE', 'unavailable'), ('STALE', 'stale')]:
            f = forecast(ids=('HN-001',))
            if status != 'OK':
                f['roads'][0].update(status=status, reason_code='producer-reason', risk=None)
                del f['roads'][0]['speed_km_h']
                f['coverage'].update(predicted=0, **{group: 1})
            with self.subTest(status=status):
                self.assertEqual(bundle([f]).to_dict()['forecasts'][0], f)

    def test_metric_allowlist_risk_only(self):
        f = forecast()
        f['output_fields'] = ['risk']
        for row in f['roads']:
            del row['speed_km_h']
        self.assertEqual(bundle([f]).to_dict()['forecasts'][0], f)

    def test_multiple_metrics_pass_through_no_interpretation(self):
        f = forecast()
        f['output_fields'] = ['risk', 'speed_km_h', 'label', 'flood_risk']
        for row in f['roads']:
            row.update(risk=18.5, speed_km_h=7, label='producer label', flood_risk=-2)
        self.assertEqual(bundle([f]).to_dict()['forecasts'][0], f)

    def test_generated_at_preserves_all_other_times(self):
        f = forecast()
        p = bundle([f]).to_dict()
        self.assertEqual(p['generated_at'], GENERATED_AT)
        for key in ('issue_time', 'issued_at', 'forecast_time'):
            self.assertNotEqual(p['generated_at'], f[key])
            self.assertEqual(p['forecasts'][0][key], f[key])

    def test_generated_at_required_and_canonical(self):
        args = inputs()
        del args['generated_at']
        with self.assertRaises(TypeError):
            build_artifact_api_bundle(**args)
        for value in (None, 'now', '2026-10-08T04:00:00+00:00', '2026-10-08T04:00:00'):
            args['generated_at'] = value
            self.reject(args)

    def test_map_network_mismatch(self):
        args = inputs()
        m = args['map_network'].to_dict()
        m['network_version'] = 'other'
        for row in m['roads']:
            row['network_version'] = 'other'
        args['map_network'] = m
        self.reject(args, 'NETWORK_VERSION_MISMATCH')

    def test_map_checksum_mismatch(self):
        args = inputs()
        c = args['context'].to_dict()
        c['artifacts']['map_network']['checksum'] = 'a' * 64
        args['context'] = c
        self.reject(args)

    def test_context_map_scope_and_registry_summary(self):
        for mutation in ('scope', 'registry'):
            args = inputs()
            c = args['context'].to_dict()
            if mutation == 'scope':
                c['road_ids'] = ['different']
            else:
                for key in ('map_network', 'routing_network'):
                    c['artifacts'][key]['registry_checksum'] = 'a' * 64
            args['context'] = c
            self.reject(args)

    def test_forecast_checksum_mismatch(self):
        args = inputs([forecast()])
        c = args['context'].to_dict()
        c['artifacts']['forecasts'][0]['checksum'] = 'a' * 64
        args['context'] = c
        self.reject(args)

    def test_forecast_summary_mismatch_even_with_actual_hash(self):
        for key, value in [('issued_at', '2026-10-08T04:00:00Z'), ('model_version', 'other')]:
            args = inputs([forecast()])
            c = args['context'].to_dict()
            c['artifacts']['forecasts'][0][key] = value
            args['context'] = c
            self.reject(args)

    def test_missing_extra_and_duplicate_forecasts(self):
        args = inputs([forecast()])
        for fs in ([], [forecast(), forecast(60)], [forecast(), forecast()]):
            self.reject(dict(args, forecasts=fs))

    def test_forecast_network_mode_unknown_road(self):
        args = inputs([forecast()])
        for f, code in [(forecast(network_version='other'), 'NETWORK_VERSION_MISMATCH'),
                         (forecast(mode='demo'), 'INVALID_CONTRACT'),
                         (forecast(ids=('unknown',)), 'UNKNOWN_ROAD')]:
            self.reject(dict(args, forecasts=[f]), code)

    def test_forecast_order_determinism_and_detachment(self):
        fs = [forecast(60), forecast(30)]
        args = inputs(fs)
        before = copy.deepcopy(fs)
        a = build_artifact_api_bundle(**args)
        b = build_artifact_api_bundle(**dict(args, forecasts=list(reversed(fs))))
        self.assertEqual(a.to_json(), b.to_json())
        self.assertEqual(a.checksum(), b.checksum())
        self.assertEqual(fs, before)
        fs[0]['roads'].clear()
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_producer_row_order_preserved_no_index_join(self):
        f = forecast(ids=('HN-002', 'HN-001'))
        f['roads'][0]['risk'], f['roads'][1]['risk'] = 123, 456
        p = bundle([f]).to_dict()
        self.assertEqual(p['forecasts'][0]['roads'], f['roads'])
        self.assertEqual([r['road_id'] for r in p['network']['roads']], ['HN-001', 'HN-002', 'HN-003'])

    def test_map_allowlist_and_canonical_reverse_geometry(self):
        args = inputs()
        p = build_artifact_api_bundle(**args).to_dict()['network']
        self.assertEqual(set(p), {'schema', 'network_version', 'coordinate_order', 'roads'})
        self.assertEqual(p['coordinate_order'], 'lat_lon')
        for actual, source in zip(p['roads'], args['map_network'].to_dict()['roads']):
            self.assertEqual(set(actual), {'road_id', 'name', 'geometry', 'directionality'})
            self.assertEqual(actual['geometry'], source['geometry'])
            self.assertEqual(actual['directionality'], source['directionality'])

    def test_demo_mode_from_context(self):
        p = bundle([forecast(15, mode='demo')], mode='demo').to_dict()
        self.assertEqual(p['mode'], 'demo')
        self.assertEqual(p['available_horizons_minutes'], [15])
        self.assertEqual(bundle().to_dict()['mode'], 'artifact')  # same HN IDs, no inference

    def test_dict_inputs(self):
        args = inputs([ForecastOutput(forecast())])
        raw = dict(context=args['context'].to_dict(), map_network=args['map_network'].to_dict(),
                   forecasts=[f.to_dict() for f in args['forecasts']], generated_at=GENERATED_AT)
        before = copy.deepcopy(raw)
        self.assertEqual(build_artifact_api_bundle(**args).to_json(), build_artifact_api_bundle(**raw).to_json())
        self.assertEqual(raw, before)

    def test_offline_no_runtime(self):
        args = inputs([forecast()])
        with patch('socket.socket', side_effect=AssertionError('network')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('HTTP')), \
             patch('vietsafe.core.forecast.forecast', side_effect=AssertionError('prediction')), \
             patch('vietsafe.core.routing.calculate_routes', side_effect=AssertionError('routing')):
            build_artifact_api_bundle(**args)

    def test_import_safety(self):
        script = '''
import sys, socket, urllib.request
from unittest.mock import patch

def audit(event, args):
    if event == 'open':
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & 3):
            raise AssertionError('write')
    if event in ('os.mkdir', 'sqlite3.connect', 'socket.connect', 'socket.__new__'):
        raise AssertionError(event)
sys.addaudithook(audit)
with patch.object(socket, 'socket', side_effect=AssertionError('socket')), patch.object(urllib.request, 'urlopen', side_effect=AssertionError('HTTP')):
    import vietsafe.integration.api_contracts
    import vietsafe.integration.api_projection
assert not any(m in sys.modules for m in ['vietsafe.core.routing', 'vietsafe.core.forecast', 'vietsafe.service', 'vietsafe.web', 'vietsafe.db'])
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[2], env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
