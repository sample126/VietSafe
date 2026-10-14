import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
from engine import build_snapshot, calculate_routes
from network import NODES, ROADS, nearest_road


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.original=server.DB_PATH
        server.DB_PATH=Path(self.temp.name)/'test.sqlite3'
        server.init_db()

    def tearDown(self):
        server.DB_PATH=self.original
        self.temp.cleanup()

    def report(self,**overrides):
        payload=dict(type='flood',severity=3,lat=21.0182,lng=105.8053,address='Duong Lang',description='Nuoc ngap sau, xe khong the di qua.')
        payload.update(overrides)
        return server.create_report(payload)

    def test_report_persistence_and_review_lifecycle(self):
        created=self.report()
        self.assertEqual(server.get_reports()[0]['status'],'pending')
        before=server.snapshot()
        server.review_report(created['id'],'verified')
        after=server.snapshot()
        road=next(r for r in after['roads'] if r['id']==created['road_id'])
        self.assertTrue(road['blocked'])
        self.assertEqual(road['origin'],'local_report')
        server.review_report(created['id'],'resolved')
        self.assertEqual(server.get_reports()[0]['status'],'resolved')
        with self.assertRaises(ValueError):server.review_report(created['id'],'verified')

    def test_pending_report_does_not_affect_routing(self):
        self.report()
        pending=server.get_reports()
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
        self.assertEqual(len(server.get_reports()),1)

    def test_expired_report_cannot_affect_network(self):
        created=self.report();server.review_report(created['id'],'verified')
        with server.connect() as db:db.execute('UPDATE reports SET expires_at=0')
        rows=server.get_reports();self.assertEqual(rows[0]['status'],'expired')
        self.assertTrue(all(r['origin']=='demo' for r in build_snapshot('normal',rows)['roads']))

    def test_snapshot_logging(self):
        server.snapshot();server.snapshot()
        with server.connect() as db:
            row=db.execute('SELECT * FROM prediction_logs LIMIT 1').fetchone()
        self.assertEqual(row['model_version'],'spatial-rule-demo-1.0')
        self.assertEqual(len(json.loads(row['payload'])),len(ROADS))

    def test_bad_routing_inputs(self):
        for args in [('invalid','hoankiem',0),('caugiay','caugiay',0),('caugiay','hoankiem',99)]:
            with self.assertRaises(ValueError):calculate_routes(build_snapshot(),*args)


if __name__=='__main__':unittest.main(verbosity=2)
