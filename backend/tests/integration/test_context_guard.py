"""Cross-artifact consistency using synthetic contracts; no predictions."""

import copy
import os
import subprocess
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from vietsafe.integration.contracts import ForecastOutput
from vietsafe.integration.context_guard import build_integration_context
from vietsafe.integration.errors import IntegrationContractError
from vietsafe.integration.registry_map import build_map_network
from vietsafe.integration.registry_routing import build_routing_network
from .helpers import output_payload
from .test_registry_routing import road, registry


def networks():
    source = registry(road('both'), road('reverse', 'HN-002'), road(rid='HN-003'))
    return build_map_network(source), build_routing_network(source)


def forecast(h=30, ids=('HN-001', 'HN-002'), **changes):
    p = output_payload()
    p.update(network_version='test-v1', horizon_minutes=h)
    p.update(changes)
    issue = datetime.strptime(p['issue_time'], '%Y-%m-%dT%H:%M:%SZ')
    p['forecast_time'] = (issue + timedelta(minutes=h)).strftime('%Y-%m-%dT%H:%M:%SZ')
    p['roads'] = [dict(road_id=rid, status='OK', risk=0, speed_km_h=20) for rid in ids]
    p['coverage'].update(total=len(ids), predicted=len(ids))
    return p


def context(forecasts=(), mode='artifact', map_network=None, routing_network=None):
    m, r = networks()
    return build_integration_context(mode=mode, map_network=m if map_network is None else map_network,
        routing_network=r if routing_network is None else routing_network, forecasts=forecasts)


class ContextGuardTests(unittest.TestCase):
    def reject(self, code='INVALID_CONTRACT', **kwargs):
        with self.assertRaises(IntegrationContractError) as caught:
            context(**kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_no_forecast_checksums_scope(self):
        m, r = networks()
        p = context().to_dict()
        self.assertEqual(p['road_ids'], ['HN-001', 'HN-002', 'HN-003'])
        self.assertEqual(p['network_version'], 'test-v1')
        self.assertEqual(p['artifacts']['map_network']['checksum'], m.checksum())
        self.assertEqual(p['artifacts']['routing_network']['checksum'], r.checksum())
        self.assertEqual(p['available_horizons_minutes'], [])

    def test_30_60_and_true_checksums(self):
        fs = [ForecastOutput(forecast(30)), ForecastOutput(forecast(60))]
        p = context(fs).to_dict()
        self.assertEqual(p['available_horizons_minutes'], [30, 60])
        self.assertEqual([f['checksum'] for f in p['artifacts']['forecasts']], [f.checksum() for f in fs])

    def test_routing_network_mismatch(self):
        r = networks()[1].to_dict()
        r['network_version'] = 'other'
        for arc in r['arcs']:
            arc['network_version'] = 'other'
        self.reject('NETWORK_VERSION_MISMATCH', routing_network=r)

    def test_forecast_network_mismatch(self):
        self.reject('NETWORK_VERSION_MISMATCH', forecasts=[forecast(network_version='other')])

    def test_missing_routing_roads(self):
        self.reject(routing_network=build_routing_network(registry(road('both'))))

    def test_extra_routing_roads(self):
        source = registry(road('both'), road(rid='HN-002'), road(rid='HN-003'), road(rid='HN-004'))
        self.reject('UNKNOWN_ROAD', routing_network=build_routing_network(source))

    def test_both_arc_count_is_not_scope(self):
        m, r = networks()
        self.assertEqual(len(m.to_dict()['roads']), 3)
        self.assertEqual(len(r.to_dict()['arcs']), 4)
        self.assertEqual(len(context().to_dict()['road_ids']), 3)

    def test_partial_preserves_scope_coverage_no_synthesis(self):
        f = ForecastOutput(forecast())
        p = context([f]).to_dict()['artifacts']['forecasts'][0]
        self.assertEqual(p['road_ids'], ['HN-001', 'HN-002'])
        self.assertEqual(p['coverage'], f.to_dict()['coverage'])
        self.assertNotIn('roads', p)
        with self.assertRaises(IntegrationContractError) as caught:
            f.validate_scope('test-v1', ['HN-001', 'HN-002', 'HN-003'])
        self.assertEqual(caught.exception.code, 'MISSING_INPUT')

    def test_empty_explicit_forecast_scope(self):
        p = context([forecast(ids=())]).to_dict()['artifacts']['forecasts'][0]
        self.assertEqual(p['road_ids'], [])
        self.assertEqual(p['coverage']['total'], 0)

    def test_unknown_forecast_road(self):
        self.reject('UNKNOWN_ROAD', forecasts=[forecast(ids=('HN-004',))])

    def test_mode_mismatch_both_directions(self):
        self.reject(forecasts=[forecast(mode='demo')])
        self.reject(mode='demo', forecasts=[forecast()])

    def test_explicit_mode_not_inferred_from_hn_ids(self):
        self.assertEqual(context().to_dict()['mode'], 'artifact')
        self.assertEqual(context([forecast(15, mode='demo')], mode='demo').to_dict()['available_horizons_minutes'], [15])

    def test_issue_time_mismatch(self):
        self.reject(forecasts=[forecast(), forecast(60, issue_time='2026-10-08T03:00:00Z')])

    def test_issued_at_can_differ(self):
        p = context([forecast(), forecast(60, issued_at='2026-10-08T02:32:00Z')]).to_dict()
        self.assertEqual(len(p['artifacts']['forecasts']), 2)

    def test_model_version_mismatch(self):
        self.reject(forecasts=[forecast(), forecast(60, model_version='other')])

    def test_duplicate_horizon(self):
        self.reject(forecasts=[forecast(), forecast()])

    def test_invalid_artifact_horizons_reuse_validator(self):
        for h in (15, 45):
            self.reject('UNSUPPORTED_HORIZON', forecasts=[forecast(h)])

    def test_invalid_forecast_schema_coverage_time(self):
        for key, value in [('schema', 'bad'), ('coverage', {}), ('forecast_time', '2026-10-08T05:00:00Z')]:
            p = forecast()
            p[key] = value
            self.reject(forecasts=[p])

    def test_determinism_and_no_mutation(self):
        m, r = networks()
        fs = [forecast(60), forecast(30)]
        before = copy.deepcopy(fs)
        a = context(fs, map_network=m.to_dict(), routing_network=r.to_dict())
        b = context(list(reversed(fs)), map_network=m, routing_network=r)
        self.assertEqual(a.to_json(), b.to_json())
        self.assertEqual(a.checksum(), b.checksum())
        self.assertEqual(fs, before)
        fs[0]['roads'].clear()
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_registry_snapshot_mismatch(self):
        r = networks()[1].to_dict()
        r['registry_checksum'] = 'a' * 64
        self.reject(routing_network=r)

    def test_invalid_types_and_missing_artifacts(self):
        for mode in (None, True, 'live', []):
            self.reject(mode=mode)
        for fs in (None, {}, 'bad'):
            self.reject(forecasts=fs)
        for key in ('map_network', 'routing_network'):
            with self.assertRaises(IntegrationContractError):
                m, r = networks()
                arguments = dict(map_network=m, routing_network=r)
                arguments[key] = None
                build_integration_context(mode='artifact', **arguments)

    def test_offline_no_runtime_and_geometry_unchanged(self):
        m, r = networks()
        before = (m.to_json(), r.to_json())
        with patch('socket.socket', side_effect=AssertionError('network')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('HTTP')), \
             patch('vietsafe.core.forecast.forecast', side_effect=AssertionError('prediction')), \
             patch('vietsafe.core.routing.calculate_routes', side_effect=AssertionError('routing')):
            context([forecast()], map_network=m, routing_network=r)
        self.assertEqual(before, (m.to_json(), r.to_json()))

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
    import vietsafe.integration.context_contracts
    import vietsafe.integration.context_guard
assert not any(m in sys.modules for m in ['vietsafe.core.routing', 'vietsafe.core.forecast', 'vietsafe.service', 'vietsafe.web', 'vietsafe.db'])
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[2], env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
