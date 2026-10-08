"""Test logic lõi (core/): dự báo, định tuyến, tìm kiếm. Không cần DB hay HTTP."""

import unittest

from vietsafe.core.network import ROADS, nearest_road
from vietsafe.core.routing import calculate_routes
from vietsafe.core.search import normalize, search_places
from vietsafe.core.simulation import build_snapshot


class RoutingTests(unittest.TestCase):
    def test_routes_exclude_blocked_and_unknown_and_are_contiguous(self):
        for scenario in ("normal", "rain", "storm"):
            s = build_snapshot(scenario)
            prohibited = {r["id"] for r in s["roads"] if r["blocked"] or not r["known"]}
            for horizon in (0, 30, 60):
                result = calculate_routes(s, "caugiay", "hoankiem", horizon)
                self.assertTrue(result["routes"])
                for route in result["routes"]:
                    self.assertFalse(prohibited.intersection(route["road_ids"]))
                    previous = "caugiay"
                    for rid in route["road_ids"]:
                        r = next(r for r in ROADS if r["id"] == rid)
                        self.assertIn(previous, (r["a"], r["b"]))
                        previous = r["b"] if previous == r["a"] else r["a"]
                    self.assertEqual(previous, "hoankiem")

    def test_disconnected_graph_returns_no_route(self):
        s = build_snapshot()
        for r in s["roads"]:
            r["blocked"] = True
        self.assertEqual(calculate_routes(s, "caugiay", "hoankiem")["routes"], [])

    def test_bad_routing_inputs(self):
        for args in [
            ("invalid", "hoankiem", 0),
            ("caugiay", "caugiay", 0),
            ("caugiay", "hoankiem", 99),
        ]:
            with self.assertRaises(ValueError):
                calculate_routes(build_snapshot(), *args)

    def test_unknown_vehicle_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_routes(build_snapshot(), "caugiay", "hoankiem", 0, "helicopter")


class ForecastTests(unittest.TestCase):
    def test_forecast_responds_to_weather_and_preserves_unknown(self):
        dry = build_snapshot("normal", now=1000)
        wet = build_snapshot("storm", now=1000)
        for a, b in zip(dry["roads"], wet["roads"], strict=True):
            if not a["known"]:
                self.assertTrue(all(f["risk"] is None for f in a["forecast"]))
            else:
                self.assertGreaterEqual(
                    b["forecast"][4]["flood_risk"], a["forecast"][4]["flood_risk"]
                )
                self.assertEqual([f["horizon"] for f in b["forecast"]], [0, 15, 30, 45, 60])

    def test_snapshot_shape(self):
        s = build_snapshot("rain", now=1000)
        self.assertEqual(len(s["roads"]), 36)
        self.assertEqual(len(s["nodes"]), 25)
        self.assertEqual(s["rainfall"], 28)
        self.assertEqual(s["mode"], "demo")


class NetworkAndSearchTests(unittest.TestCase):
    def test_normalize_strips_vietnamese_diacritics(self):
        self.assertEqual(normalize("Đường Láng – Hạ"), "duong lang – ha")

    def test_search_is_accent_insensitive(self):
        names = {r["name"] for r in search_places("lang ha")}
        self.assertIn("Láng Hạ", names)

    def test_search_limit(self):
        self.assertLessEqual(len(search_places("")), 12)

    def test_nearest_road_on_segment_is_zero_distance(self):
        road = ROADS[0]
        (lat, lng) = road["coordinates"][0]
        km, nearest, _ = nearest_road(lat, lng)
        self.assertAlmostEqual(km, 0, places=3)
        self.assertIn(nearest["id"], {r["id"] for r in ROADS})


if __name__ == "__main__":
    unittest.main(verbosity=2)
