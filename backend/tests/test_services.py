"""Test dịch vụ (reports, service, auth) trên SQLite tạm."""

import json
import time
import unittest

from vietsafe import auth, reports, service
from vietsafe.core.routing import calculate_routes
from vietsafe.core.simulation import build_snapshot
from vietsafe.db import connect

from .helpers import DatabaseTestCase


class ReportTests(DatabaseTestCase):
    def report(self, **overrides):
        payload = dict(
            type="flood",
            severity=3,
            lat=21.0182,
            lng=105.8053,
            address="Duong Lang",
            description="Nuoc ngap sau, xe khong the di qua.",
        )
        payload.update(overrides)
        return reports.create_report(payload)

    def test_report_persistence_and_review_lifecycle(self):
        created = self.report()
        self.assertEqual(reports.get_reports()[0]["status"], "pending")
        service.current_snapshot()
        reports.review_report(created["id"], "verified")
        road = next(r for r in service.current_snapshot()["roads"] if r["id"] == created["road_id"])
        self.assertTrue(road["blocked"])
        self.assertEqual(road["origin"], "local_report")
        reports.review_report(created["id"], "resolved")
        self.assertEqual(reports.get_reports()[0]["status"], "resolved")
        with self.assertRaises(ValueError):
            reports.review_report(created["id"], "verified")

    def test_pending_report_does_not_affect_routing(self):
        self.report()
        pending = reports.get_reports()
        a = build_snapshot("normal", [], now=1000)
        b = build_snapshot("normal", pending, now=1000)
        self.assertEqual(a["roads"], b["roads"])
        self.assertEqual(
            calculate_routes(a, "caugiay", "hoankiem"), calculate_routes(b, "caugiay", "hoankiem")
        )

    def test_invalid_report_validation(self):
        cases = [
            dict(lat=float("nan")),
            dict(lat=0),
            dict(severity=9),
            dict(type="fake"),
            dict(description="short"),
            dict(image="data:image/svg+xml;base64,AA=="),
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.report(**overrides)

    def test_duplicate_submission_is_idempotent(self):
        first, second = self.report(), self.report()
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(len(reports.get_reports()), 1)

    def test_expired_report_cannot_affect_network(self):
        created = self.report()
        reports.review_report(created["id"], "verified")
        with connect() as db:
            db.execute("UPDATE reports SET expires_at=0")
        rows = reports.get_reports()
        self.assertEqual(rows[0]["status"], "expired")
        self.assertTrue(all(r["origin"] == "demo" for r in build_snapshot("normal", rows)["roads"]))

    def test_csv_export_neutralises_formula_injection(self):
        self.report(description="=HYPERLINK('http://evil') nội dung dài")
        text = reports.export_csv(reports.get_reports()).decode("utf-8-sig")
        self.assertIn("'=HYPERLINK", text)
        self.assertNotIn(",=HYPERLINK", text)


class ServiceTests(DatabaseTestCase):
    def test_snapshot_logging(self):
        service.current_snapshot()
        service.current_snapshot()
        with connect() as db:
            row = db.execute("SELECT * FROM prediction_logs LIMIT 1").fetchone()
        self.assertEqual(row["model_version"], "spatial-rule-demo-1.0")
        self.assertEqual(len(json.loads(row["payload"])), 36)

    def test_scenario_roundtrip_and_validation(self):
        self.assertEqual(service.get_scenario(), "rain")
        service.set_scenario("storm")
        self.assertEqual(service.get_scenario(), "storm")
        with self.assertRaises(ValueError):
            service.set_scenario("tsunami")


class AuthTests(DatabaseTestCase):
    def test_demo_accounts_seeded_and_login(self):
        user, token = auth.login("admin", "vietsafe2026")
        self.assertEqual(user["role"], "admin")
        self.assertEqual(auth.get_user_by_session(token)["username"], "admin")
        self.assertIsNone(auth.login("admin", "sai-mat-khau"))

    def test_register_validation_and_duplicates(self):
        auth.register("nguoi_moi", "123456", "Người mới")
        with self.assertRaises(ValueError):
            auth.register("nguoi_moi", "123456", "Trùng")
        for args in [
            ("ab", "123456", "x"),
            ("hop_le", "123", "x"),
            ("hop_le", "123456", ""),
            (1, 2, 3),
        ]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                auth.register(*args)

    def test_logout_invalidates_session(self):
        _, token = auth.login("nguoidan", "matkhau123")
        auth.delete_session(token)
        self.assertIsNone(auth.get_user_by_session(token))

    def test_expired_session_is_rejected(self):
        _, token = auth.login("nguoidan", "matkhau123")
        with connect() as db:
            db.execute("UPDATE sessions SET expires_at=?", (time.time() - 1,))
        self.assertIsNone(auth.get_user_by_session(token))


if __name__ == "__main__":
    unittest.main(verbosity=2)
