"""Test phân quyền qua API (RBAC): khách / người dân / quản trị viên.

Trước đây là `test_auth.py` dạng script chạy tay (đường dẫn cứng, ghi vào DB thật); nay là
test tự động chạy trên DB tạm.
"""

import time
import unittest

from .helpers import ServerTestCase

REPORT = {
    "type": "flood",
    "severity": 2,
    "lat": 21.0285,
    "lng": 105.8355,
    "address": "Phố Giảng Võ",
    "description": "Nước ngập nửa bánh xe, xe máy đi lại khó khăn",
}


class AuthApiTests(ServerTestCase):
    def test_anonymous_me_is_null(self):
        status, data = self.api("/api/auth/me")
        self.assertEqual((status, data["user"]), (200, None))

    def test_wrong_password_is_401(self):
        status, _ = self.api("/api/auth/login", {"username": "admin", "password": "sai"})
        self.assertEqual(status, 401)

    def test_login_missing_fields_is_400(self):
        status, _ = self.api("/api/auth/login", {"username": "", "password": ""})
        self.assertEqual(status, 400)

    def test_citizen_cannot_change_scenario(self):
        token = self.login("nguoidan", "matkhau123")
        status, _ = self.api("/api/scenario", {"scenario": "heavy_rain"}, token)
        self.assertEqual(status, 403)

    def test_anonymous_cannot_report(self):
        status, _ = self.api("/api/reports", REPORT)
        self.assertEqual(status, 401)

    def test_report_review_flow_and_permissions(self):
        citizen = self.login("nguoidan", "matkhau123")
        status, created = self.api("/api/reports", REPORT, citizen)
        self.assertEqual(status, 201, created)
        report_id = created["id"]

        status, _ = self.api(f"/api/reports/{report_id}", {"status": "verified"}, citizen)
        self.assertEqual(status, 403)  # người dân không được duyệt

        admin = self.login("admin", "vietsafe2026")
        status, data = self.api(f"/api/reports/{report_id}", {"status": "verified"}, admin)
        self.assertEqual((status, data["status"]), (200, "verified"))

    def test_admin_changes_scenario(self):
        admin = self.login("admin", "vietsafe2026")
        status, _ = self.api("/api/scenario", {"scenario": "storm"}, admin)
        self.assertEqual(status, 200)
        _, snapshot = self.api("/api/snapshot")
        self.assertEqual(snapshot["rainfall"], 55)

    def test_exports_require_admin(self):
        for path in ("/api/export/reports", "/api/export/predictions"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 403)
                citizen = self.login("nguoidan", "matkhau123")
                code, _, _ = self.request(path, headers={"X-VietSafe-Session": citizen})
                self.assertEqual(code, 403)

    def test_register_then_use_token(self):
        username = f"user_{int(time.time())}"
        status, data = self.api(
            "/api/auth/register",
            {"username": username, "password": "password123", "display_name": "Người dùng mới"},
        )
        self.assertEqual(status, 200, data)
        status, me = self.api("/api/auth/me", token=data["token"])
        self.assertEqual(me["user"]["username"], username)
        self.assertEqual(me["user"]["role"], "citizen")

    def test_logout_invalidates_token(self):
        admin = self.login("admin", "vietsafe2026")
        status, _ = self.api("/api/auth/logout", {}, admin)
        self.assertEqual(status, 200)
        _, me = self.api("/api/auth/me", token=admin)
        self.assertIsNone(me["user"])

    def test_report_rate_limit(self):
        citizen = self.login("nguoidan", "matkhau123")
        statuses = []
        for i in range(12):
            body = {**REPORT, "description": f"Nước ngập sâu lần {i}, xe không đi qua được"}
            statuses.append(self.api("/api/reports", body, citizen)[0])
        self.assertEqual(statuses.count(201), 10)
        self.assertEqual(statuses[-1], 429)


if __name__ == "__main__":
    unittest.main(verbosity=2)
