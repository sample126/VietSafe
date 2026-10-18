"""Offline E2E contract compatibility, not model accuracy or runtime integration."""

import copy
import os
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

from vietsafe.data_pipeline.adapters.demo import load_demo_registry
from vietsafe.data_pipeline.registry import RoadRegistry
from vietsafe.integration.api_contracts import ArtifactApiBundle
from vietsafe.integration.api_projection import build_artifact_api_bundle
from vietsafe.integration.context_contracts import IntegrationContext
from vietsafe.integration.context_guard import build_integration_context
from vietsafe.integration.contracts import ForecastOutput
from vietsafe.integration.end_to_end import run_contract_pipeline
from vietsafe.integration.errors import IntegrationContractError
from vietsafe.integration.map_contracts import MapNetwork
from vietsafe.integration.registry_routing import build_routing_network
from vietsafe.integration.routing_contracts import RoutingNetwork
from .e2e_helpers import GENERATED_AT, osm_registry, synthetic_contract_forecast
from .test_registry_routing import road, registry as synthetic_registry


def run(registry, forecasts=(), mode='artifact'):
    return run_contract_pipeline(registry=registry, mode=mode, generated_at=GENERATED_AT, forecasts=forecasts)


class IntegrationEndToEndTests(unittest.TestCase):
    def test_osm_e2e_offline_identity_scope_geometry(self):
        with patch('socket.socket', side_effect=AssertionError('network')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('HTTP')):
            registry = osm_registry()
            result = run(registry)
        self.assertIsInstance(result.routing_network, RoutingNetwork)
        self.assertIsInstance(result.map_network, MapNetwork)
        self.assertIsInstance(result.context, IntegrationContext)
        self.assertIsInstance(result.api_bundle, ArtifactApiBundle)
        m, r, c, api = (a.to_dict() for a in (result.map_network, result.routing_network,
                                            result.context, result.api_bundle))
        ids = {road.road_id for road in registry}
        for p in (m, r, c, api):
            self.assertEqual(p['network_version'], registry.network_version)
        for p in (m, r):
            self.assertEqual(p['registry_checksum'], registry.checksum)
        self.assertEqual({v['road_id'] for v in m['roads']}, ids)
        self.assertEqual({v['road_id'] for v in r['arcs']}, ids)
        self.assertEqual(set(c['road_ids']), ids)
        self.assertEqual({v['road_id'] for v in api['network']['roads']}, ids)
        self.assertEqual(len(r['arcs']), sum(2 if road.directionality == 'both' else 1 for road in registry))
        # Exact registry identity equality proves no replacement/demo ID was introduced.
        for entry in api['network']['roads']:
            source = registry.get(entry['road_id'])
            self.assertEqual(entry['geometry'], [list(p) for p in source.coordinates])
        for arc in r['arcs']:
            source = registry.get(arc['road_id'])
            coords = list(source.coordinates)
            if source.directionality == 'reverse':
                coords.reverse()
            self.assertEqual(arc['travel_geometry'], [list(p) for p in coords])
        self.assertEqual(api['forecasts'], [])
        self.assertEqual(api['available_horizons_minutes'], [])

    def test_demo_36_scope_without_simulation(self):
        with patch('vietsafe.data_pipeline.adapters.demo.generate_demo_observations', side_effect=AssertionError('simulation')), \
             patch('vietsafe.core.forecast.forecast', side_effect=AssertionError('Forecast')), \
             patch('vietsafe.core.routing.calculate_routes', side_effect=AssertionError('Routing')), \
             patch('socket.socket', side_effect=AssertionError('network')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('HTTP')):
            source = load_demo_registry()
            result = run(source, mode='demo')
        self.assertEqual(len(result.map_network.to_dict()['roads']), 36)
        self.assertEqual(len(result.routing_network.to_dict()['arcs']), 72)
        self.assertEqual(len(result.context.to_dict()['road_ids']), 36)
        self.assertEqual(result.api_bundle.to_dict()['mode'], 'demo')
        self.assertEqual(set(result.context.to_dict()['road_ids']), {r.road_id for r in source})

    def test_forward_reverse_both_full_polylines(self):
        source = synthetic_registry(road(), road('reverse', 'HN-002'), road('both', 'HN-003'))
        result = run(source)
        maps = {r['road_id']: r for r in result.map_network.to_dict()['roads']}
        api_roads = {r['road_id']: r for r in result.api_bundle.to_dict()['network']['roads']}
        arcs = result.routing_network.to_dict()['arcs']
        self.assertEqual(len(arcs), 4)
        for road_source in source:
            canonical = [list(p) for p in road_source.coordinates]
            self.assertEqual(maps[road_source.road_id]['geometry'], canonical)
            self.assertEqual(api_roads[road_source.road_id]['geometry'], canonical)
            travels = [a for a in arcs if a['road_id'] == road_source.road_id]
            if road_source.directionality == 'both':
                self.assertEqual(len(travels), 2)
                self.assertEqual(travels[0]['travel_geometry'], list(reversed(travels[1]['travel_geometry'])))
            else:
                self.assertEqual(travels[0]['travel_geometry'], canonical if road_source.directionality == 'forward' else canonical[::-1])

    def test_forecast_partial_zero_null_statuses_e2e(self):
        with patch('socket.socket', side_effect=AssertionError('network')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('HTTP')):
            source = osm_registry()
            forecasts = [synthetic_contract_forecast(source, h) for h in (30, 60)]
            result = run(source, forecasts)
        p = result.api_bundle.to_dict()
        self.assertEqual(result.context.to_dict()['available_horizons_minutes'], [30, 60])
        self.assertEqual(p['available_horizons_minutes'], [30, 60])
        self.assertEqual(len(p['network']['roads']), len(source))
        self.assertGreater(len(source), 4)
        for actual, original in zip(p['forecasts'], forecasts):
            self.assertEqual(actual, original.to_dict())
            self.assertEqual(len(actual['roads']), 4)
            self.assertEqual(actual['roads'][0]['risk'], 0)
            self.assertIsNone(actual['roads'][1]['risk'])
            self.assertNotIn('risk', actual['roads'][2])
            self.assertEqual([r['status'] for r in actual['roads']], ['OK', 'MISSING_INPUT', 'UNAVAILABLE', 'STALE'])

    def test_repeated_and_reversed_inputs_checksums(self):
        source = osm_registry()
        fs = [synthetic_contract_forecast(source, h) for h in (30, 60)]
        reversed_registry = RoadRegistry(source.network_version, list(reversed(list(source))))
        a, b, c = run(source, fs), run(source, fs), run(reversed_registry, list(reversed(fs)))
        for field in ('routing_network', 'map_network', 'context', 'api_bundle'):
            with self.subTest(field=field):
                self.assertEqual(getattr(a, field).to_json(), getattr(b, field).to_json())
                self.assertEqual(getattr(a, field).checksum(), getattr(c, field).checksum())

    def test_producer_road_order_does_not_join_by_index(self):
        source = osm_registry()
        p = synthetic_contract_forecast(source).to_dict()
        p['roads'].reverse()
        result = run(source, [ForecastOutput(p)])
        self.assertEqual(result.api_bundle.to_dict()['forecasts'][0]['roads'], p['roads'])
        self.assertEqual(result.context.to_dict()['road_ids'], sorted(r.road_id for r in source))

    def test_network_mismatch_fails_before_api(self):
        source = osm_registry()
        f = synthetic_contract_forecast(source).to_dict()
        f['network_version'] = 'other-network'
        with patch('vietsafe.integration.end_to_end.build_artifact_api_bundle', side_effect=AssertionError('must not reach API')):
            with self.assertRaises(IntegrationContractError) as caught:
                run(source, [f])
        self.assertEqual(caught.exception.code, 'NETWORK_VERSION_MISMATCH')

    def test_unknown_forecast_road(self):
        source = osm_registry()
        f = synthetic_contract_forecast(source).to_dict()
        f['roads'][0]['road_id'] = 'opaque-unknown-road'
        with self.assertRaises(IntegrationContractError) as caught:
            run(source, [f])
        self.assertEqual(caught.exception.code, 'UNKNOWN_ROAD')

    def test_routing_scope_mismatch_not_intersected(self):
        source = osm_registry()
        subset = RoadRegistry(source.network_version, list(source)[:-1])
        wrong_routing = build_routing_network(subset)
        with patch('vietsafe.integration.end_to_end.build_routing_network', return_value=wrong_routing):
            with self.assertRaises(IntegrationContractError) as caught:
                run(source)
        self.assertEqual(caught.exception.code, 'INVALID_CONTRACT')

    def test_tampered_context_checksums_fail_without_rebuild(self):
        source = osm_registry()
        fs = [synthetic_contract_forecast(source)]
        real_builder = build_integration_context
        for kind in ('map', 'forecast'):
            def tampered(**kwargs):
                p = real_builder(**kwargs).to_dict()
                if kind == 'map':
                    p['artifacts']['map_network']['checksum'] = 'a' * 64
                else:
                    p['artifacts']['forecasts'][0]['checksum'] = 'a' * 64
                return IntegrationContext(p)
            with patch('vietsafe.integration.end_to_end.build_integration_context', side_effect=tampered) as builder:
                with self.assertRaises(IntegrationContractError) as caught:
                    run(source, fs)
                self.assertEqual(caught.exception.code, 'INVALID_CONTRACT')
                self.assertEqual(builder.call_count, 1)

    def test_issue_mismatch(self):
        source = osm_registry()
        fs = [synthetic_contract_forecast(source), synthetic_contract_forecast(source, 60, '2026-10-08T03:00:00Z')]
        with self.assertRaises(IntegrationContractError):
            run(source, fs)

    def test_duplicate_horizon(self):
        source = osm_registry()
        f = synthetic_contract_forecast(source)
        with self.assertRaises(IntegrationContractError):
            run(source, [f, f])

    def test_unsupported_horizons(self):
        source = osm_registry()
        for h in (15, 45):
            p = synthetic_contract_forecast(source).to_dict()
            p['horizon_minutes'] = h
            with self.assertRaises(IntegrationContractError) as caught:
                run(source, [p])
            self.assertEqual(caught.exception.code, 'UNSUPPORTED_HORIZON')

    def test_recursive_api_no_raw_ml_or_route_internals(self):
        source = osm_registry()
        p = run(source, [synthetic_contract_forecast(source)]).api_bundle.to_dict()
        forbidden = {'X', 'X_mask', 'y', 'y_mask', 'labels', 'feature_names', 'feature_tensors',
                     'adjacency', 'training_split', 'raw_grids', 'soil_grids', 'rain_grids', 'DEM',
                     'routes', 'route', 'ETA', 'distance', 'vehicle', 'warnings', 'routing_cost',
                     'arcs', 'outgoing', 'source_id', 'provenance', 'lineage'}
        def inspect(value):
            if isinstance(value, dict):
                self.assertFalse(set(value) & forbidden)
                for child in value.values():
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)
        inspect(p)

    def test_deep_no_mutation_and_frozen_result(self):
        source = osm_registry()
        fs = [synthetic_contract_forecast(source, 60), synthetic_contract_forecast(source)]
        before = (copy.deepcopy(source.to_dict()), [f.to_dict() for f in fs])
        result = run(source, fs)
        self.assertEqual((source.to_dict(), [f.to_dict() for f in fs]), before)
        artifacts = (result.map_network, result.routing_network, result.context, result.api_bundle)
        snapshots = [a.to_json() for a in artifacts]
        build_artifact_api_bundle(context=result.context, map_network=result.map_network,
                                  forecasts=result.forecasts, generated_at=GENERATED_AT)
        self.assertEqual([a.to_json() for a in artifacts], snapshots)
        result.map_network.to_dict()['roads'].clear()
        result.api_bundle.to_dict()['forecasts'].clear()
        fs.clear()
        self.assertEqual([a.to_json() for a in artifacts], snapshots)
        self.assertIsInstance(result.forecasts, tuple)
        with self.assertRaises(FrozenInstanceError):
            result.context = None

    def test_required_timestamp_and_invalid_inputs(self):
        source = osm_registry()
        with self.assertRaises(TypeError):
            run_contract_pipeline(registry=source, mode='artifact')
        for field, value in [('registry', {}), ('mode', 'bad'), ('generated_at', 'now'), ('forecasts', None)]:
            args = dict(registry=source, mode='artifact', generated_at=GENERATED_AT)
            args[field] = value
            with self.assertRaises(IntegrationContractError):
                run_contract_pipeline(**args)

    def test_no_runtime_or_output_during_pipeline(self):
        source = osm_registry()
        fs = [synthetic_contract_forecast(source)]
        with patch('builtins.open', side_effect=AssertionError('file IO')), \
             patch('os.mkdir', side_effect=AssertionError('mkdir')), \
             patch('builtins.print', side_effect=AssertionError('print')), \
             patch('socket.socket', side_effect=AssertionError('network')), \
             patch('urllib.request.urlopen', side_effect=AssertionError('HTTP')), \
             patch('vietsafe.core.forecast.forecast', side_effect=AssertionError('forecast')), \
             patch('vietsafe.core.routing.calculate_routes', side_effect=AssertionError('route')), \
             patch('vietsafe.data_pipeline.adapters.demo.generate_demo_observations', side_effect=AssertionError('simulation')):
            run(source, fs)

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
    import vietsafe.integration.end_to_end
assert not any(m in sys.modules for m in ['vietsafe.core.routing', 'vietsafe.core.forecast', 'vietsafe.service', 'vietsafe.web', 'vietsafe.db'])
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[2], env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')
