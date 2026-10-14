import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2] / 'backend'))
from vietsafe import auth, config, db, reports, service
from vietsafe.core.engine import build_snapshot, calculate_routes
from vietsafe.core.network import NODES, ROADS, nearest_road, road_midpoint
from vietsafe.web.server import Handler, ThreadingHTTPServer
from vietsafe.providers import tomtom_traffic, nasa_gpm, openmeteo_weather

import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch



class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.original=db.DB_PATH
        db.DB_PATH=Path(self.temp.name)/'test.sqlite3'
        db.init_db()

    def tearDown(self):
        db.DB_PATH=self.original
        self.temp.cleanup()

    def report(self,**overrides):
        payload=dict(type='flood',severity=3,lat=21.0182,lng=105.8053,address='Duong Lang',description='Nuoc ngap sau, xe khong the di qua.')
        payload.update(overrides)
        return reports.create_report(payload)

    def test_load_local_env_reads_keys_without_overriding_process_environment(self):
        env_path=Path(self.temp.name)/'.env'
        env_path.write_text(
            'TOMTOM_API_KEY="local-key"\nNASA_EARTHDATA_TOKEN=earth-key\n',
            encoding='utf-8',
        )
        with patch.dict('os.environ',{'TOMTOM_API_KEY':'process-key'},clear=True):
            config.load_local_env(env_path)
            self.assertEqual(config.os.environ['TOMTOM_API_KEY'],'process-key')
            self.assertEqual(config.os.environ['NASA_EARTHDATA_TOKEN'],'earth-key')

    def test_report_persistence_and_review_lifecycle(self):
        created=self.report()
        self.assertEqual(reports.get_reports()[0]['status'],'pending')
        before=service.snapshot()
        reports.review_report(created['id'],'verified')
        after=service.snapshot()
        road=next(r for r in after['roads'] if r['id']==created['road_id'])
        self.assertTrue(road['blocked'])
        self.assertEqual(road['origin'],'local_report')
        reports.review_report(created['id'],'resolved')
        self.assertEqual(reports.get_reports()[0]['status'],'resolved')
        with self.assertRaises(ValueError):reports.review_report(created['id'],'verified')

    def test_pending_report_does_not_affect_routing(self):
        self.report()
        pending=reports.get_reports()
        a=build_snapshot('normal',[],now=1000)
        b=build_snapshot('normal',pending,now=1000)
        self.assertEqual(a['roads'],b['roads'])
        self.assertEqual(calculate_routes(a,'caugiay','hoankiem'),calculate_routes(b,'caugiay','hoankiem'))

    def test_routes_exclude_blocked_and_unknown_and_are_contiguous(self):
        for scenario in ('normal','rain','storm'):
            s=build_snapshot(scenario)
            prohibited={r['id'] for r in s['roads'] if r['blocked'] or not r['known']}
            for horizon in (0,30,60):
                result=calculate_routes(s,'caugiay','hoankiem',horizon)
                self.assertTrue(result['routes'])
                for route in result['routes']:
                    self.assertFalse(prohibited.intersection(route['road_ids']))
                    previous='caugiay'
                    for rid in route['road_ids']:
                        r=next(r for r in ROADS if r['id']==rid)
                        self.assertIn(previous,(r['a'],r['b']))
                        previous=r['b'] if previous==r['a'] else r['a']
                    self.assertEqual(previous,'hoankiem')

    def test_road_geometry_follows_osm_and_route_geometry_uses_road_shapes(self):
        self.assertEqual(len(ROADS),36)
        for road in ROADS:
            self.assertGreater(len(road['coordinates']),2)
            self.assertGreater(road['length_km'],0)
            self.assertLess(
                math.hypot(road['coordinates'][0][0]-NODES[road['a']]['lat'],
                           road['coordinates'][0][1]-NODES[road['a']]['lng']),
                1e-6)
            self.assertLess(
                math.hypot(road['coordinates'][-1][0]-NODES[road['b']]['lat'],
                           road['coordinates'][-1][1]-NODES[road['b']]['lng']),
                1e-6)
        snapshot=build_snapshot('normal')
        route=calculate_routes(snapshot,'caugiay','hoankiem')['routes'][0]
        self.assertGreater(len(route['coordinates']),len(route['road_ids'])*2)
        first=next(road for road in ROADS if road['id']==route['road_ids'][0])
        midpoint=road_midpoint(first['coordinates'])
        self.assertEqual(len(midpoint),2)
        snapped=nearest_road(*midpoint)
        self.assertLess(snapped[0],0.001)
        expected=[]
        previous='caugiay'
        for road_id in route['road_ids']:
            road=next(item for item in ROADS if item['id']==road_id)
            coordinates=road['coordinates'] if road['a']==previous else list(reversed(road['coordinates']))
            expected.extend(coordinates if not expected else coordinates[1:])
            previous=road['b'] if road['a']==previous else road['a']
        self.assertEqual(route['coordinates'],expected)

    def test_disconnected_graph_returns_no_route(self):
        s=build_snapshot()
        for r in s['roads']:r['blocked']=True
        self.assertEqual(calculate_routes(s,'caugiay','hoankiem')['routes'],[])

    def test_forecast_responds_to_weather_and_preserves_unknown(self):
        dry=build_snapshot('normal',now=1000);wet=build_snapshot('storm',now=1000)
        for a,b in zip(dry['roads'],wet['roads']):
            if not a['known']:
                self.assertTrue(all(f['risk'] is None for f in a['forecast']))
            else:
                self.assertGreaterEqual(b['forecast'][4]['flood_risk'],a['forecast'][4]['flood_risk'])
                self.assertEqual([f['horizon'] for f in b['forecast']],[0,15,30,45,60])

    def test_invalid_report_validation(self):
        for overrides in [dict(lat=float('nan')),dict(lat=0),dict(severity=9),dict(type='fake'),dict(description='short'),dict(image='data:image/svg+xml;base64,AA==')]:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):self.report(**overrides)

    def test_duplicate_submission_is_idempotent(self):
        first=self.report();second=self.report()
        self.assertEqual(first['id'],second['id']);self.assertTrue(second['duplicate'])
        self.assertEqual(len(reports.get_reports()),1)

    def test_expired_report_cannot_affect_network(self):
        created=self.report();reports.review_report(created['id'],'verified')
        with db.connect() as connection:connection.execute('UPDATE reports SET expires_at=0')
        rows=reports.get_reports();self.assertEqual(rows[0]['status'],'expired')
        self.assertTrue(all(r['origin']=='demo' for r in build_snapshot('normal',rows)['roads']))

    def test_snapshot_logging(self):
        service.snapshot();service.snapshot()
        with db.connect() as connection:
            row=connection.execute('SELECT * FROM prediction_logs LIMIT 1').fetchone()
        self.assertEqual(row['model_version'],'spatial-rule-demo-1.0')
        self.assertEqual(len(json.loads(row['payload'])),len(ROADS))

    def test_bad_routing_inputs(self):
        for args in [('invalid','hoankiem',0),('caugiay','caugiay',0),('caugiay','hoankiem',99)]:
            with self.assertRaises(ValueError):calculate_routes(build_snapshot(),*args)


if __name__=='__main__':unittest.main(verbosity=2)
