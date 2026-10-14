"""Portable HTTP/contract tests: no ML packages or research data required."""

import http.client
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vietsafe.forecasting import service
from vietsafe.forecasting.contracts import Unavailable

from .helpers import ServerTestCase


class AIContractTests(unittest.TestCase):
    def test_base_server_import_without_site_packages(self):
        result = subprocess.run(
            [
                sys.executable,
                "-S",
                "-c",
                "from vietsafe.web.server import create_server; "
                "import sys; assert 'numpy' not in sys.modules; "
                "assert 'sklearn' not in sys.modules",
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))

    def test_extra_payload_fields_rejected(self):
        for extra in ("path", "target_60", "features", "model"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                service.predict({"task": "bellinge", "site_id": "x", "origin": "x", extra: "x"})

    def test_invalid_task_and_types(self):
        for task in (None, [], "../../secrets", "hanoi"):
            with self.subTest(task=task), self.assertRaises(ValueError):
                service.predict({"task": task, "site_id": "x", "origin": "x"})
        with self.assertRaises(ValueError):
            service.predict({"task": "sztaxi", "site_id": 90217, "origin": 2411})

    def test_modified_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            manifest = folder / "manifest.json"
            manifest.write_text(json.dumps({"bellinge": {"checkpoint.joblib": "0" * 64}}))
            (folder / "checkpoint.joblib").write_bytes(b"changed")
            with patch.object(service, "MANIFEST", manifest), self.assertRaises(Unavailable):
                service.verify_artifacts("bellinge", folder)


class AIHttpTests(ServerTestCase):
    def setUp(self):
        super().setUp()
        self.environment = patch.dict(os.environ, {"VIETSAFE_AI_RESEARCH_ROOT": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_catalog_without_artifacts(self):
        status, data = self.api("/api/ai/catalog")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["tasks"]), 3)
        self.assertTrue(all(t["status"] == "not_configured" for t in data["tasks"]))
        self.assertFalse(data["public_alert_allowed"])
        self.assertNotIn("F:\\", json.dumps(data))

    def test_unconfigured_returns_503_and_existing_health_stays_ok(self):
        status, data = self.api(
            "/api/ai/predict", {"task": "bellinge", "site_id": "x", "origin": "x"}
        )
        self.assertEqual(status, 503)
        self.assertNotIn("horizons", data)
        self.assertEqual(self.api("/api/health")[0], 200)
        self.assertEqual(self.api("/api/ai/sites?task=floodnet")[0], 503)

    def test_unknown_task_and_extra_fields_return_400(self):
        self.assertEqual(self.api("/api/ai/sites?task=hanoi")[0], 400)
        self.assertEqual(
            self.api(
                "/api/ai/predict",
                {"task": "sztaxi", "site_id": "90217", "origin": "2411", "future": 4},
            )[0],
            400,
        )

    def test_ai_assets_and_existing_forecast_link(self):
        for path in ("/forecast-lab.html", "/js/views/ai-forecast.js", "/css/ai-forecast.css"):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 200)
        self.assertIn(b"/forecast-lab.html", self.request("/")[2])

    def test_ai_post_requires_existing_same_origin_header(self):
        # No request body: avoid a Windows TCP reset when the guard rejects before reading it.
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(
                "POST", "/api/ai/predict", headers={"Origin": "https://untrusted.invalid"}
            )
            response = connection.getresponse()
            self.assertEqual(response.status, 403)
            response.read()
        finally:
            connection.close()

    def test_controller_passes_typed_prediction_unchanged(self):
        predicted = {
            "schema_version": "vietsafe.ai-replay.v1",
            "quantity": "drainage_water_level",
            "unit": "m",
            "horizons": [{"minutes": 30, "value": 0.1}],
        }
        with patch.object(service, "predict", return_value=predicted):
            status, data = self.api(
                "/api/ai/predict", {"task": "bellinge", "site_id": "s", "origin": "t"}
            )
        self.assertEqual(status, 200)
        self.assertEqual(data, predicted)
