"""Tiện ích dùng chung cho test: DB tạm và máy chủ HTTP chạy trên cổng ngẫu nhiên."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from vietsafe import config
from vietsafe.app import init_app
from vietsafe.web.api import report_limiter
from vietsafe.web.server import create_server


class DatabaseTestCase(unittest.TestCase):
    """Mỗi test chạy trên một SQLite tạm mới, không đụng tới dữ liệu thật trong data/."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._original_db = config.DB_PATH
        config.DB_PATH = Path(self._tmp.name) / "test.sqlite3"
        init_app()
        report_limiter.reset()

    def tearDown(self):
        config.DB_PATH = self._original_db
        self._tmp.cleanup()


class ServerTestCase(DatabaseTestCase):
    """DatabaseTestCase + một máy chủ HTTP thật (cổng 0 = cổng trống do HĐH chọn)."""

    def setUp(self):
        super().setUp()
        self.server = create_server("127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        super().tearDown()

    def request(self, path, body=None, headers=None):
        """Trả về (status, headers, bytes). Có `body` -> POST JSON, không có -> GET."""
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.headers, e.read()

    def api(self, path, body=None, token=None):
        """Gọi API như frontend (có header X-VietSafe). Trả về (status, dict JSON)."""
        headers = {"X-VietSafe": "local", "Origin": self.base}
        if token:
            headers["X-VietSafe-Session"] = token
        if body is not None:
            headers["Content-Type"] = "application/json"
        status, _, raw = self.request(path, body, headers)
        return status, json.loads(raw)

    def login(self, username, password):
        status, data = self.api("/api/auth/login", {"username": username, "password": password})
        self.assertEqual(status, 200, data)
        return data["token"]
