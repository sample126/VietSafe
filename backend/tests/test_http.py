import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2] / 'backend'))
from vietsafe import auth, config, db, reports, service
from vietsafe.core.engine import build_snapshot, calculate_routes
from vietsafe.core.network import NODES, ROADS, nearest_road, road_midpoint
from vietsafe.web.server import Handler, ThreadingHTTPServer
from vietsafe.providers import tomtom_traffic, nasa_gpm, openmeteo_weather

import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
import urllib.error



class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.original=db.DB_PATH
        db.DB_PATH=Path(cls.temp.name)/'http.sqlite3'
        db.init_db()
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.http.server_port}'
        with db.connect() as connection:
            connection.execute('INSERT OR IGNORE INTO users VALUES(?,?,?,?)',('admin',auth.hash_password('test-long-admin-password'),'Admin','admin'))
        cls.admin_token = auth.create_session('admin')

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join(timeout=5)
        db.DB_PATH=cls.original
        cls.temp.cleanup()

    def request(self,path,body=None,headers=None):
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
                                   headers=headers or {})
        try:
            with urllib.request.urlopen(req,timeout=5) as r:return r.status,r.headers,r.read()
        except urllib.error.HTTPError as e:
            with e:return e.code,e.headers,e.read()

    def test_page_and_local_assets(self):
        for path in ('/','/js/views/app.js','/js/views/map-ai.js','/css/map-ai.css','/css/style.css','/vendor/leaflet.js','/favicon.svg','/js/data/bacninh-roads.json'):
            code,headers,body=self.request(path)
            self.assertEqual(code,200);self.assertTrue(body)
            if path=='/js/data/bacninh-roads.json':
                self.assertIn('application/json',headers['Content-Type'])
                self.assertEqual(len(json.loads(body)['roads']),14)
        code,headers,_=self.request('/js/views/app.js')
        self.assertIn('javascript',headers['Content-Type'])
        code,headers,_=self.request('/')
        self.assertIn('https://tile.openstreetmap.de',headers['Content-Security-Policy'])
        self.assertIn('https://*.tile.openstreetmap.fr',headers['Content-Security-Policy'])
        self.assertIn("connect-src 'self'",headers['Content-Security-Policy'])

    def test_map_page_does_not_load_simulation_modules(self):
        _,_,body=self.request('/')
        page=body.decode('utf-8')
        self.assertIn('/js/main.js',page)
        self.assertNotIn('/js/views/enhancements.js',page)
        self.assertNotIn('/js/views/tgcn.js',page)
        self.assertNotIn('+30 phút',page)
        self.assertNotIn('Trạng thái nguồn dữ liệu bản đồ',page)
        self.assertNotIn('flood-observation-status',page)
        self.assertNotIn('weather-forecast-status',page)
        self.assertIn('Lưu lượng giao thông trực tiếp · Hà Nội',page)
        self.assertIn('aria-label="Bản đồ tương tác Hà Nội"',page)
        self.assertNotIn('<option value="all">Toàn vùng</option>',page)
        self.assertNotIn('<option value="bacninh">Bắc Ninh</option>',page)
        code,headers,boundary=self.request('/js/data/hanoi-boundary.json')
        self.assertEqual(code,200)
        self.assertIn('application/json',headers['Content-Type'])
        feature=json.loads(boundary)['features'][0]
        self.assertEqual(feature['properties']['name'],'Hà Nội')
        self.assertEqual(feature['geometry']['type'],'Polygon')
        _,_,app=self.request('/js/views/app.js')
        self.assertIn('maxBoundsViscosity:1',app.decode('utf-8'))
        self.assertIn('/js/data/hanoi-boundary.json',app.decode('utf-8'))
        self.assertIn('hanoiMaskPane',app.decode('utf-8'))
        self.assertIn('isWithinHanoi(e.latlng.lat,e.latlng.lng)',app.decode('utf-8'))
        self.assertNotIn('/api/map/geometry',app.decode('utf-8'))
        self.assertNotIn('/js/data/bacninh-roads.json',app.decode('utf-8'))
        code,_,_=self.request('/api/map/geometry')
        self.assertEqual(code,404)

    def test_snapshot_search_and_routes(self):
        for path,expected in [('/api/snapshot',409),('/api/search?q=Lang',200),('/api/routes?origin=caugiay&destination=hoankiem',501)]:
            code,_,body=self.request(path);self.assertEqual(code,expected);self.assertIsInstance(json.loads(body),dict)

    def test_live_status_reports_configuration_without_exposing_credentials(self):
        tomtom=os.environ.pop('TOMTOM_API_KEY',None)
        nasa=os.environ.pop('NASA_EARTHDATA_TOKEN',None)
        try:
            code,_,body=self.request('/api/live-status')
            self.assertEqual(code,200)
            status=json.loads(body)
            self.assertEqual(status['mode'],'live-only')
            self.assertFalse(status['traffic']['configured'])
            self.assertFalse(status['rainfall']['configured'])
            self.assertFalse(status['traffic_forecast_model'])
            self.assertFalse(status['gemini'])
            self.assertNotIn('key',json.dumps(status).lower())
            self.assertNotIn('token',json.dumps(status).lower())
        finally:
            if tomtom is not None:config.os.environ['TOMTOM_API_KEY']=tomtom
            if nasa is not None:config.os.environ['NASA_EARTHDATA_TOKEN']=nasa

    def test_gpm_endpoint_requires_earthdata_token(self):
        previous=config.os.environ.pop('NASA_EARTHDATA_TOKEN',None)
        try:
            code,_,body=self.request('/api/gpm/rainfall')
            self.assertEqual(code,503)
            self.assertIn('NASA_EARTHDATA_TOKEN',json.loads(body)['error'])
        finally:
            if previous is not None:
                config.os.environ['NASA_EARTHDATA_TOKEN']=previous

    def test_tomtom_tiles_and_segment_require_server_api_key(self):
        previous=config.os.environ.pop('TOMTOM_API_KEY',None)
        try:
            code,_,body=self.request('/api/tomtom/flow/15/1/1.png')
            self.assertEqual(code,502)
            self.assertIn('TOMTOM_API_KEY',json.loads(body)['error'])
            code,_,body=self.request('/api/tomtom/segment?lat=21.0&lng=105.8')
            self.assertEqual(code,502)
            self.assertIn('TOMTOM_API_KEY',json.loads(body)['error'])
            code,_,body=self.request('/api/tomtom/flow/15/32768/1.png')
            self.assertEqual(code,400)
            self.assertIn('phạm vi',json.loads(body)['error'])
        finally:
            if previous is not None:
                config.os.environ['TOMTOM_API_KEY']=previous

    def test_tomtom_tile_and_clicked_segment_routes(self):
        tile=b'\x89PNG\r\n\x1a\nflow tile'
        with patch('vietsafe.web.controllers.system.get_flow_tile',return_value=tile) as get_tile:
            code,headers,body=self.request('/api/tomtom/flow/15/10/12.png')
        self.assertEqual(code,200)
        self.assertEqual(headers['Content-Type'],'image/png')
        self.assertEqual(headers['Cache-Control'],'public, max-age=180')
        self.assertEqual(body,tile)
        get_tile.assert_called_once_with(15,10,12)

        segment={
            'coordinates':[[21.0,105.8],[21.001,105.801]],
            'current_speed_kmh':18,
            'free_flow_speed_kmh':45,
        }
        with patch('vietsafe.web.controllers.system.get_flow_segment',return_value=segment) as get_segment, \
             patch('vietsafe.web.controllers.system.get_road_name',return_value='Hoàng Diệu') as get_road_name:
            code,_,body=self.request('/api/tomtom/segment?lat=21.0&lng=105.8&zoom=16')
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body),{
            **segment,
            'street_name':'Hoàng Diệu',
            'street_name_source':'TomTom',
        })
        get_segment.assert_called_once_with(21.0,105.8,16)
        get_road_name.assert_called_once_with(21.0,105.8)

    def test_tomtom_segment_retains_flow_when_street_lookup_fails(self):
        segment={'coordinates':[[21.0,105.8],[21.001,105.801]],'current_speed_kmh':18}
        with patch('vietsafe.web.controllers.system.get_flow_segment',return_value=segment), \
             patch('vietsafe.web.controllers.system.get_road_name',side_effect=tomtom_traffic.TomTomUnavailable('Tên đường chưa có')):
            code,_,body=self.request('/api/tomtom/segment?lat=21.0&lng=105.8&zoom=16')
        self.assertEqual(code,200)
        result=json.loads(body)
        self.assertEqual(result['current_speed_kmh'],18)
        self.assertEqual(result['street_name_error'],'Tên đường chưa có')

    def test_tomtom_permission_denial_uses_openstreetmap_for_road_name(self):
        segment={'coordinates':[[21.0,105.8],[21.001,105.801]],'current_speed_kmh':18}
        denied=tomtom_traffic.TomTomPermissionDenied('TomTom key chưa có quyền Search API.')
        with patch('vietsafe.web.controllers.system.get_flow_segment',return_value=segment), \
             patch('vietsafe.web.controllers.system.get_road_name',side_effect=denied), \
             patch('vietsafe.web.controllers.system.get_osm_road_name',return_value='Phố Hoàng Diệu') as get_osm_name:
            code,_,body=self.request('/api/tomtom/segment?lat=21.0&lng=105.8&zoom=16')

        self.assertEqual(code,200)
        result=json.loads(body)
        self.assertEqual(result['current_speed_kmh'],18)
        self.assertEqual(result['street_name'],'Phố Hoàng Diệu')
        self.assertEqual(result['street_name_source'],'OpenStreetMap')
        self.assertNotIn('street_name_error',result)
        get_osm_name.assert_called_once_with(21.0,105.8)

    def test_reject_cross_origin_and_missing_custom_header(self):
        for headers in ({},{'X-VietSafe':'local','Origin':'https://example.org'}):
            self.assertEqual(self.request('/api/scenario',{'scenario':'storm'},headers)[0],403)

    def test_bad_host_and_traversal(self):
        self.assertEqual(self.request('/api/health',headers={'Host':'example.org'})[0],403)
        self.assertEqual(self.request('/%2e%2e/server.py')[0],404)

    def test_scenario_update(self):
        code,_,_=self.request('/api/scenario',{'scenario':'storm'},{'X-VietSafe':'local','X-VietSafe-Session':self.admin_token})
        self.assertEqual(code,200)
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT value FROM settings WHERE key='scenario'").fetchone()[0],'storm')

    def test_invalid_route_returns_client_error(self):
        self.assertEqual(self.request('/api/routes?origin=bad&destination=bad')[0],501)

    def test_csv_has_download_headers(self):
        code,headers,body=self.request('/api/export/reports',headers={'X-VietSafe-Session':self.admin_token})
        self.assertEqual(code,200);self.assertIn('attachment',headers['Content-Disposition']);self.assertTrue(body.startswith(b'\xef\xbb\xbf'))


if __name__=='__main__':unittest.main(verbosity=2)
