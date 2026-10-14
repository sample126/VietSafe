import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2] / 'backend'))
from vietsafe import auth, config, db, reports, service
from vietsafe.core.engine import build_snapshot, calculate_routes
from vietsafe.core.network import NODES, ROADS, nearest_road, road_midpoint
from vietsafe.web.server import Handler, ThreadingHTTPServer
from vietsafe.providers import tomtom_traffic, nasa_gpm, openmeteo_weather

"""Regression checks without real provider keys or internet access."""
import os
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import json
import time
from pathlib import Path
from unittest.mock import patch
from vietsafe.providers.openmeteo_weather import get_rain_forecast

class LiveDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.old_db = db.DB_PATH
        db.DB_PATH = Path(cls.tmp.name)/'test.sqlite3'
        db.init_db()
        cls.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.port = cls.httpd.server_port
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown();cls.httpd.server_close()
        db.DB_PATH=cls.old_db
        cls.tmp.cleanup()

    def get(self,path):
        req=urllib.request.Request('http://127.0.0.1:'+str(self.port)+path)
        try:
            with urllib.request.urlopen(req,timeout=5) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_health(self):
        code,data=self.get('/api/health')
        self.assertEqual(code,200)
        self.assertTrue(data['ok'])

    def test_demo_endpoints_disabled(self):
        for url,expected in [('/api/snapshot',409),('/api/routes',501)]:
            self.assertEqual(self.get(url)[0],expected)

    def test_demo_events_are_available_separately_from_live_snapshot(self):
        code,data=self.get('/api/demo/events')
        self.assertEqual(code,200)
        self.assertEqual(data['mode'],'demo')
        self.assertIn('không phải cảnh báo giao thông thực tế',data['notice'])
        self.assertTrue(data['events'])
        self.assertTrue(all(event['origin']=='demo' for event in data['events']))
        self.assertEqual(self.get('/api/snapshot')[0],409)

    def test_flood_starts_empty(self):
        code,data=self.get('/api/flood/observations')
        self.assertEqual(code,200)
        self.assertEqual(data['observations'],[])

    def test_flood_requires_admin(self):
        req=urllib.request.Request('http://127.0.0.1:'+str(self.port)+'/api/flood/observations',
                data=b'{}',method='POST',headers={'X-VietSafe':'local','Origin':'http://127.0.0.1:'+str(self.port),
                    'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as result:
            urllib.request.urlopen(req,timeout=5)
        self.assertEqual(result.exception.code,403)

    def test_forecast_validation(self):
        with self.assertRaises(ValueError):
            get_rain_forecast(float('nan'),105,24)
        with self.assertRaises(ValueError):
            get_rain_forecast(21,105,120)
        self.assertEqual(self.get('/api/weather/forecast?hours=100')[0],400)

    def test_flood_validation(self):
        with self.assertRaises(ValueError):
            reports.add_flood_observation({'lat':21,'lng':105,'depth_cm':-1,'observed_at':time.time(),
                'source':'sensor','source_reference':'sensor-01'})

if __name__=='__main__':unittest.main()
