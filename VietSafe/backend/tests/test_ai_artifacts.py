"""Opt-in parity checks against frozen LOCAL artifacts, never training/retuning.

Set VIETSAFE_AI_VERIFY_ROOT to the parent of the three research folders.
The normal portable suite skips this module's tests when artifacts are absent.
"""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from vietsafe.forecasting import service

ROOT = os.environ.get("VIETSAFE_AI_VERIFY_ROOT")


@unittest.skipUnless(ROOT, "Set VIETSAFE_AI_VERIFY_ROOT for local checkpoint parity checks")
class ArtifactParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        import pandas as pd

        cls.np, cls.pd = np, pd
        cls.root = Path(ROOT)
        cls.environment = patch.dict(os.environ, {"VIETSAFE_AI_RESEARCH_ROOT": ROOT})
        cls.environment.start()
        cls.addClassCleanup(cls.environment.stop)
        cls.bellinge = service.provider("bellinge")
        cls.sztaxi = service.provider("sztaxi")
        cls.floodnet = service.provider("floodnet")

    def test_bellinge_matches_frozen_predictions_all_sensors(self):
        from threadpoolctl import threadpool_limits

        np = self.np
        with np.load(
            self.root / "vietsafe-model-comparison-20261007/results/test_predictions.npz"
        ) as saved:
            rows = np.linspace(0, len(saved["timestamps"]) - 1, 12).astype(int)
            for i in rows:
                stamp = self.pd.Timestamp(saved["timestamps"][i]).isoformat()
                index = self.bellinge.row_index(stamp)
                x = self.bellinge.features(index)
                with threadpool_limits(limits=2):
                    predicted = (
                        np.stack([model.predict(x) for model in self.bellinge.models], -1)
                        + self.bellinge.depth[index, :, None]
                    )
                np.testing.assert_allclose(
                    predicted, saved["HGB_all_nodes"][i], atol=1e-6, rtol=1e-6
                )

    def test_sztaxi_matches_frozen_predictions_all_roads(self):
        from threadpoolctl import threadpool_limits

        np = self.np
        with np.load(
            self.root / "vietsafe-traffic-tgcn-20261007/results/test_predictions.npz"
        ) as saved:
            for i in np.linspace(0, len(saved["issue_rows"]) - 1, 12).astype(int):
                x = self.sztaxi.features(int(saved["issue_rows"][i]))
                with threadpool_limits(limits=2):
                    predicted = np.maximum(
                        np.stack([model.predict(x) for model in self.sztaxi.models], -1), 0
                    )
                np.testing.assert_allclose(
                    predicted, saved["HGB_neighbours"][i], atol=1e-5, rtol=1e-6
                )

    def test_floodnet_matches_saved_calibrated_probabilities(self):
        saved = self.pd.read_parquet(
            self.root
            / "vietsafe-floodnet/early_warning/artifacts/audit_predictions_LOCAL_ONLY.parquet"
        )
        count = 0
        for row in saved.iloc[:: max(1, len(saved) // 30)].itertuples():
            if (
                row.site not in self.floodnet.frames
                or row.time_ns not in self.floodnet.frames[row.site].index
            ):
                continue
            result = service.predict(
                {
                    "task": "floodnet",
                    "site_id": row.site,
                    "origin": self.pd.Timestamp(row.time_ns, tz="UTC").isoformat(),
                }
            )
            self.assertAlmostEqual(result["horizons"][0]["value"], row.probability_30, places=9)
            self.assertAlmostEqual(result["horizons"][1]["value"], row.probability_60, places=9)
            count += 1
        self.assertGreaterEqual(count, 10)

    def test_defaults_json_units_and_no_future_observations(self):
        for task in ("bellinge", "floodnet", "sztaxi"):
            with self.subTest(task=task):
                default = service.sites(task)["default"]
                output = service.predict(
                    {"task": task, "site_id": default["site_id"], "origin": default["origin"]}
                )
                json.dumps(output, allow_nan=False)
                self.assertFalse(output["public_alert_allowed"])
                self.assertFalse(output["hanoi_calibrated"])
                self.assertFalse(output["future_observations_used_as_input"])
                self.assertTrue(all(p["offset_minutes"] <= 0 for p in output["history"]))
                self.assertTrue(
                    {"truth", "target_30", "target_60", "flood_risk", "speed_km_h"}.isdisjoint(
                        output
                    )
                )
                self.assertNotEqual(output["unit"], "km/h")

    def test_hanoi_unknown_sites_and_invalid_origins_rejected(self):
        for task, provider in (
            ("bellinge", self.bellinge),
            ("floodnet", self.floodnet),
            ("sztaxi", self.sztaxi),
        ):
            with self.subTest(task=task), self.assertRaises(ValueError):
                provider.predict("hanoi-cau-giay", provider.default["origin"])
            with self.subTest(task=task), self.assertRaises(ValueError):
                provider.predict(provider.default["site_id"], "2026-10-11")

    def test_feature_builders_cannot_read_beyond_origin(self):
        np = self.np
        # Truncate every time-indexed feature source at the issue point. Outputs must match.
        for provider, index, names in (
            (
                self.bellinge,
                self.bellinge.row_index(self.bellinge.default["origin"]),
                ("local", "mask", "rain", "rainmask", "calendar"),
            ),
            (self.sztaxi, 2411, ("x", "neighbours")),
        ):
            expected = provider.features(index)
            original = {name: getattr(provider, name) for name in names}
            try:
                for name, values in original.items():
                    setattr(provider, name, values[: index + 1])
                np.testing.assert_array_equal(provider.features(index), expected)
            finally:
                for name, values in original.items():
                    setattr(provider, name, values)

    def test_floodnet_excludes_labels_from_inference_frames(self):
        self.assertEqual(len(self.floodnet.features), 42)
        self.assertFalse(any("target" in name for name in self.floodnet.features))
        for frame in self.floodnet.frames.values():
            self.assertFalse(any("target" in name for name in frame.columns))

    def test_bellinge_refuses_degraded_measurement_window(self):
        index = self.bellinge.row_index(self.bellinge.default["origin"])
        original = self.bellinge.mask[index].copy()
        try:
            self.bellinge.mask[index] = 0
            with self.assertRaises(ValueError):
                self.bellinge.features(index)
        finally:
            self.bellinge.mask[index] = original
