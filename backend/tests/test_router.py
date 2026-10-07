"""Test bảng route và bộ giới hạn tốc độ (không cần HTTP)."""

import unittest

from vietsafe.web.ratelimit import SlidingWindowLimiter
from vietsafe.web.router import Request, Router, authorize


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.router = Router()
        self.router.add("GET", "/api/a", lambda r: {}, auth=None)
        self.router.add("GET", "/api/items/{item_id}", lambda r: {}, auth="admin", deny="Cấm")

    def test_exact_and_parametrised_match(self):
        route, params = self.router.match("GET", "/api/items/R-1")
        self.assertEqual(params, {"item_id": "R-1"})
        self.assertIsNotNone(self.router.match("GET", "/api/a"))

    def test_method_and_path_must_match(self):
        self.assertIsNone(self.router.match("POST", "/api/a"))
        self.assertIsNone(self.router.match("GET", "/api/items/a/b"))
        self.assertIsNone(self.router.match("GET", "/api/items/"))

    def test_authorize_admin_required(self):
        route, _ = self.router.match("GET", "/api/items/x")
        req = Request("GET", "/api/items/x", {}, None, {}, "1.1.1.1")
        req._user = None
        self.assertEqual(authorize(route, req).status, 403)
        req._user = {"username": "u", "role": "citizen"}
        self.assertEqual(authorize(route, req).status, 403)
        req._user = {"username": "a", "role": "admin"}
        self.assertIsNone(authorize(route, req))


class RateLimiterTests(unittest.TestCase):
    def test_blocks_after_limit_per_key(self):
        limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
        self.assertTrue(limiter.allow("ip1"))
        self.assertTrue(limiter.allow("ip1"))
        self.assertFalse(limiter.allow("ip1"))
        self.assertTrue(limiter.allow("ip2"))

    def test_window_expires(self):
        limiter = SlidingWindowLimiter(limit=1, window_seconds=0.05)
        self.assertTrue(limiter.allow("k"))
        self.assertFalse(limiter.allow("k"))
        import time

        time.sleep(0.08)
        self.assertTrue(limiter.allow("k"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
