"""Physical invariants, event timing and API isolation for synthetic scenarios."""

import copy
import math
import unittest

from vietsafe.forecasting import scenario

from .helpers import ServerTestCase


class ScenarioTests(unittest.TestCase):
    def payload(self, **overrides):
        return {**copy.deepcopy(scenario.DEFAULT), **overrides}

    def test_dry_without_rain_cannot_create_water(self):
        result = scenario.predict(self.payload(rain_mm_h=[0] * 12))
        self.assertTrue(all(p["depth_cm"] == 0 for p in result["trajectory"]))
        self.assertTrue(all(not h["onset_within_horizon"] for h in result["horizons"]))
        self.assertIsNone(result["probability"])

    def test_no_drain_matches_analytical_water_volume(self):
        result = scenario.predict(self.payload(initial_depth_cm=2, catchment_area_ha=1,
                                  ponding_area_m2=1000, runoff_coefficient=0.5,
                                  drainage_capacity_lps=0, rain_mm_h=[12] * 12))
        # One hour: 12 mm * 10,000 m2 * 0.5 = 60 m3 = +6 cm.
        self.assertAlmostEqual(result["horizons"][0]["depth_cm"], 5, places=4)
        self.assertAlmostEqual(result["horizons"][1]["depth_cm"], 8, places=4)

    def test_conservation_and_nonnegative_depths_all_presets(self):
        for preset in scenario.PRESETS:
            result = scenario.predict(copy.deepcopy(preset["inputs"]))
            for run in (result, result["comparison"]):
                self.assertLess(abs(run["water_balance"]["residual_m3"]), 1e-7)
                self.assertTrue(all(p["depth_cm"] >= 0 for p in run["trajectory"]))
                self.assertTrue(all(math.isfinite(p["depth_cm"]) for p in run["trajectory"]))

    def test_reduced_drainage_does_not_reduce_depth(self):
        result = scenario.predict(self.payload())
        for base, weak in zip(result["trajectory"], result["comparison"]["trajectory"]):
            self.assertGreaterEqual(weak["depth_cm"] + 1e-6, base["depth_cm"])

    def test_event_confirmation_must_fit_inside_window(self):
        # Rise 0.2 cm/min; cross 5 cm at 25 min, confirmation ~35 min.
        result = scenario.predict(self.payload(catchment_area_ha=1, ponding_area_m2=1000,
                                  runoff_coefficient=1, drainage_capacity_lps=0,
                                  rain_mm_h=[12] * 12))
        self.assertFalse(result["horizons"][0]["onset_within_horizon"])
        self.assertTrue(result["horizons"][1]["onset_within_horizon"])
        self.assertAlmostEqual(result["confirmed_at_minute"], 35, delta=1/60+1e-7)

    def test_already_wet_is_not_new_onset(self):
        result = scenario.predict(self.payload(initial_depth_cm=18, rain_mm_h=[0] * 12))
        self.assertTrue(result["initially_above_threshold"])
        self.assertIsNone(result["first_onset_minute"])
        self.assertTrue(all(h["onset_status"] == "already_above_threshold"
                            and h["onset_within_horizon"] is None for h in result["horizons"]))
        self.assertLess(result["horizons"][1]["depth_cm"], 18)

    def test_full_blockage_equivalent_to_no_drain(self):
        blocked = scenario.predict(self.payload(blockage_percent=100))
        closed = scenario.predict(self.payload(drainage_capacity_lps=0))
        self.assertEqual(blocked["trajectory"], closed["trajectory"])

    def test_flood_can_recede_before_horizon_and_still_count_as_an_event(self):
        result = scenario.predict(self.payload(catchment_area_ha=1, ponding_area_m2=1000,
                                  runoff_coefficient=1, drainage_capacity_lps=200,
                                  blockage_percent=0, sustain_minutes=1,
                                  rain_mm_h=[150] * 3 + [0] * 9))
        self.assertTrue(result["horizons"][1]["onset_within_horizon"])
        self.assertLess(result["horizons"][1]["depth_cm"], result["inputs"]["threshold_cm"])

    def test_bad_input_is_rejected(self):
        bad = [self.payload(initial_depth_cm=True), self.payload(threshold_cm=float("nan")),
               self.payload(drainage_capacity_lps=-1), self.payload(rain_mm_h=[0]*11),
               self.payload(rain_mm_h=[float("inf")]*12), self.payload(sustain_minutes=1.5),
               self.payload(rain_mm_h=["10"]*12), self.payload(observed_depth_cm=12),
               self.payload(catchment_area_ha=0.1, ponding_area_m2=10000), {}]
        for payload in bad:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                scenario.predict(payload)

    def test_same_inputs_reproduce_identical_results(self):
        self.assertEqual(scenario.predict(self.payload()), scenario.predict(self.payload()))


class ScenarioHttpTests(ServerTestCase):
    def test_catalog_has_synthetic_provenance(self):
        status, data = self.api("/api/flood-simulation/catalog")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["presets"]), 4)
        self.assertTrue(data["synthetic"])
        self.assertFalse(data["uses_trained_ai"])

    def test_prediction_needs_no_research_artifacts_and_writes_no_alerts(self):
        before = self.api("/api/reports")[1]["reports"]
        status, data = self.api("/api/flood-simulation/predict", copy.deepcopy(scenario.DEFAULT))
        self.assertEqual(status, 200)
        self.assertFalse(data["hanoi_calibrated"])
        self.assertFalse(data["public_alert_allowed"])
        self.assertEqual(len(data["trajectory"]), 61)
        after = self.api("/api/reports")[1]["reports"]
        self.assertEqual(before, after)

    def test_invalid_input_and_static_assets(self):
        self.assertEqual(self.api("/api/flood-simulation/predict", {"rain_mm_h": [1]})[0], 400)
        for path in ("/flood-simulator.html", "/css/flood-simulator.css", "/js/views/flood-simulator.js"):
            self.assertEqual(self.request(path)[0], 200)
        self.assertIn(b"forecast-simulation-panel", self.request("/")[2])
        self.assertIn(b"/flood-simulator.html", self.request("/forecast-lab.html")[2])
