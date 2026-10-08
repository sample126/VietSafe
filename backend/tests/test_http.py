"""Test HTTP: file tĩnh, an ninh (Host/Origin/traversal), định dạng phản hồi."""

import http.client
import json
import unittest

from .helpers import ServerTestCase


class HTTPTests(ServerTestCase):
    def test_page_and_local_assets(self):
        paths = ("/", "/js/main.js", "/css/base.css", "/vendor/leaflet.js", "/favicon.svg")
        for path in paths:
            with self.subTest(path=path):
                code, _, body = self.request(path)
                self.assertEqual(code, 200)
                self.assertTrue(body)
        _, headers, _ = self.request("/js/main.js")
        self.assertIn("javascript", headers["Content-Type"])

    def test_security_headers_present(self):
        _, headers, _ = self.request("/")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("script-src 'self'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Frame-Options"], "DENY")

    def test_snapshot_search_and_routes(self):
        paths = (
            "/api/snapshot",
            "/api/search?q=Lang",
            "/api/routes?origin=caugiay&destination=hoankiem",
        )
        for path in paths:
            with self.subTest(path=path):
                code, _, body = self.request(path)
                self.assertEqual(code, 200)
                self.assertIsInstance(json.loads(body), dict)

    def test_health(self):
        code, _, body = self.request("/api/health")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["ok"])

    def test_reject_cross_origin_and_missing_custom_header(self):
        for headers in ({}, {"X-VietSafe": "local", "Origin": "https://example.org"}):
            with self.subTest(headers=headers):
                code, _, _ = self.request("/api/scenario", {"scenario": "storm"}, headers)
                self.assertEqual(code, 403)

    def test_bad_host_and_traversal(self):
        self.assertEqual(self.request("/api/health", headers={"Host": "example.org"})[0], 403)
        self.assertEqual(self.request("/%2e%2e/backend/vietsafe/config.py")[0], 404)
        self.assertEqual(self.request("/%2e%2e/%2e%2e/etc/passwd")[0], 404)

    def test_unknown_routes(self):
        self.assertEqual(self.request("/api/khong-ton-tai")[0], 404)
        self.assertEqual(self.request("/khong-co-file.js")[0], 404)
        status, _ = self.api("/api/khong-ton-tai", {})
        self.assertEqual(status, 404)

    def test_invalid_route_returns_client_error(self):
        self.assertEqual(self.request("/api/routes?origin=bad&destination=bad")[0], 400)
        self.assertEqual(
            self.request("/api/routes?origin=caugiay&destination=hoankiem&horizon=x")[0], 400
        )

    def _raw_post(self, body, content_length=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"X-VietSafe": "local", "Content-Type": "application/json"}
        headers["Content-Length"] = str(len(body) if content_length is None else content_length)
        conn.request("POST", "/api/auth/login", body=body, headers=headers)
        response = conn.getresponse()
        status = response.status
        conn.close()
        return status

    def test_malformed_json_is_400(self):
        self.assertEqual(self._raw_post(b"{khong phai json"), 400)

    def test_json_must_be_an_object(self):
        self.assertEqual(self._raw_post(b"[1, 2, 3]"), 400)

    def test_declared_oversized_body_is_413(self):
        self.assertEqual(self._raw_post(b"{}", content_length=50_000_000), 413)

    def test_empty_body_is_413(self):
        self.assertEqual(self._raw_post(b"", content_length=0), 413)

    def test_csv_has_download_headers(self):
        token = self.login("admin", "vietsafe2026")
        code, headers, body = self.request(
            "/api/export/reports", headers={"X-VietSafe-Session": token}
        )
        self.assertEqual(code, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
