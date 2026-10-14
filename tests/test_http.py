import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.original=server.DB_PATH
        server.DB_PATH=Path(cls.temp.name)/'http.sqlite3'
        server.init_db()
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.http.server_port}'
        cls.admin_token = server.create_session('admin')

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join(timeout=5)
        server.DB_PATH=cls.original
        cls.temp.cleanup()

    def request(self,path,body=None,headers=None):
        req=urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
                                   headers=headers or {})
        try:
            with urllib.request.urlopen(req,timeout=5) as r:return r.status,r.headers,r.read()
        except urllib.error.HTTPError as e:
            with e:return e.code,e.headers,e.read()

    def test_page_and_local_assets(self):
        for path in ('/','/app.js','/style.css','/vendor/leaflet.js','/favicon.svg'):
            code,headers,body=self.request(path)
            self.assertEqual(code,200);self.assertTrue(body)
        code,headers,_=self.request('/app.js')
        self.assertIn('javascript',headers['Content-Type'])

    def test_snapshot_search_and_routes(self):
        for path in ('/api/snapshot','/api/search?q=Lang','/api/routes?origin=caugiay&destination=hoankiem'):
            code,_,body=self.request(path);self.assertEqual(code,200);self.assertIsInstance(json.loads(body),dict)

    def test_reject_cross_origin_and_missing_custom_header(self):
        for headers in ({},{'X-VietSafe':'local','Origin':'https://example.org'}):
            self.assertEqual(self.request('/api/scenario',{'scenario':'storm'},headers)[0],403)

    def test_bad_host_and_traversal(self):
        self.assertEqual(self.request('/api/health',headers={'Host':'example.org'})[0],403)
        self.assertEqual(self.request('/%2e%2e/server.py')[0],404)

    def test_scenario_update(self):
        code,_,_=self.request('/api/scenario',{'scenario':'storm'},{'X-VietSafe':'local','X-VietSafe-Session':self.admin_token})
        self.assertEqual(code,200)
        _,_,body=self.request('/api/snapshot')
        self.assertEqual(json.loads(body)['rainfall'],55)

    def test_invalid_route_returns_client_error(self):
        self.assertEqual(self.request('/api/routes?origin=bad&destination=bad')[0],400)

    def test_csv_has_download_headers(self):
        code,headers,body=self.request('/api/export/reports',headers={'X-VietSafe-Session':self.admin_token})
        self.assertEqual(code,200);self.assertIn('attachment',headers['Content-Disposition']);self.assertTrue(body.startswith(b'\xef\xbb\xbf'))


if __name__=='__main__':unittest.main(verbosity=2)
