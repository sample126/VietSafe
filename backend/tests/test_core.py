"""Test logic lõi (core/): dự báo, định tuyến, tìm kiếm. Không cần DB hay HTTP."""

import unittest
from unittest.mock import patch

from vietsafe import config
from vietsafe.core.network import NODES, ROADS, distance, nearest_road
from vietsafe.core.osm_graph import load_graph
from vietsafe.core.routing import calculate_routes
from vietsafe.core.search import normalize, search_places
from vietsafe.core.simulation import build_snapshot


class RoutingTests(unittest.TestCase):
    def test_routes_exclude_blocked_and_unknown_and_are_contiguous(self):
        nodes, edges, _, _, _, _ = load_graph()
        for scenario in ("normal", "rain", "storm"):
            s = build_snapshot(scenario, now=1_781_000_000)
            prohibited = {r["id"] for r in s["roads"] if r["blocked"] or not r["known"]}
            for horizon in (0, 30, 60):
                result = calculate_routes(s, "caugiay", "hoankiem", horizon)
                if scenario != "storm":
                    self.assertTrue(result["routes"])
                elif not result["routes"]:
                    self.assertIn("Không tìm được tuyến", result["message"])
                for route in result["routes"]:
                    self.assertFalse(prohibited.intersection(route["road_ids"]))
                    self.assertGreater(len(route["coordinates"]), len(route["road_ids"]) + 1)
                    bit = 1
                    for start, end, eid in zip(route["coordinates"], route["coordinates"][1:], route["osm_edge_ids"]):
                        a, b, _, forward, backward = edges[eid][:5]
                        self.assertTrue((nodes[a] == start and nodes[b] == end and forward & bit) or (nodes[b] == start and nodes[a] == end and backward & bit))

    def test_disconnected_graph_returns_no_route(self):
        s = build_snapshot()
        for r in s["roads"]:
            r["blocked"] = True
        for route in calculate_routes(s, "caugiay", "hoankiem")["routes"]:
            self.assertFalse(route["road_ids"])

    def test_reproducible_time_and_peak_rules(self):
        from datetime import datetime, timezone
        morning = datetime(2026, 10, 19, 1, 0, tzinfo=timezone.utc).timestamp()
        quiet = datetime(2026, 10, 19, 4, 0, tzinfo=timezone.utc).timestamp()
        a = build_snapshot("normal", now=morning)
        b = build_snapshot("normal", now=morning + 120)
        c = build_snapshot("normal", now=quiet)
        self.assertEqual([(r["speed"], r["depth"]) for r in a["roads"]], [(r["speed"], r["depth"]) for r in b["roads"]])
        self.assertLess(a["roads"][0]["speed"], c["roads"][0]["speed"])

    def test_configurable_simulation_clock_keeps_report_clock_real(self):
        real = config.SIMULATION_EPOCH + 3600
        with patch.object(config, "SIMULATION_SPEED", 2), patch("vietsafe.core.simulation.time.time", return_value=real):
            snapshot = build_snapshot("normal")
        self.assertEqual(snapshot["generated_at"], config.SIMULATION_EPOCH + 7200)
        self.assertEqual(snapshot["simulation_speed"], 2)

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

    def test_vehicle_modes_use_directed_osm_edges(self):
        snapshot = build_snapshot("normal", now=1_781_000_000)
        nodes, edges, _, _, _, _ = load_graph()
        for vehicle, bit in (("motorbike", 1), ("car", 2), ("walk", 4)):
            routes = calculate_routes(snapshot, "caugiay", "hoankiem", vehicle=vehicle)["routes"]
            self.assertTrue(routes, vehicle)
            for route in routes:
                self.assertEqual(route["vehicle"], vehicle)
                for start, end, eid in zip(route["coordinates"], route["coordinates"][1:], route["osm_edge_ids"]):
                    a, b, _, forward, backward = edges[eid][:5]
                    self.assertTrue((nodes[a] == start and nodes[b] == end and forward & bit) or (nodes[b] == start and nodes[a] == end and backward & bit))
        self.assertGreater(calculate_routes(snapshot, "caugiay", "hoankiem", vehicle="walk")["routes"][0]["eta_minutes"], 50)


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
        self.assertEqual(len(s["roads"]), 111)
        self.assertEqual(len(s["nodes"]), 79)
        self.assertEqual(s["rainfall"], 28)
        self.assertEqual(s["mode"], "demo")

    def test_demo_hotspots_and_three_forecast_scores(self):
        s = build_snapshot("rain", now=1000)
        by_name = {road["name"]: road for road in s["roads"]}
        for name in ("Phan Bội Châu – Lý Thường Kiệt", "Nguyễn Xiển – Khuất Duy Tiến", "Đại lộ Thăng Long – An Khánh"):
            self.assertEqual(by_name[name]["event_type"], "flood")
            self.assertTrue(by_name[name]["reference_url"])
        for name in ("Lê Văn Lương – Khuất Duy Tiến", "Phạm Văn Đồng – Cổ Nhuế"):
            self.assertEqual(by_name[name]["event_type"], "traffic")
        self.assertEqual(by_name["Cầu Nhật Tân"]["event_type"], "incident")
        for road in s["roads"]:
            for point in road["forecast"]:
                for key in ("flood_risk", "traffic_risk", "incident_risk"):
                    if road["known"]:
                        self.assertGreaterEqual(point[key], 0)
                        self.assertLessEqual(point[key], 100)
                    else:
                        self.assertIsNone(point[key])

    def test_outer_districts_join_routing_graph(self):
        s = build_snapshot("normal", now=1000)
        self.assertTrue(calculate_routes(s, "sontay", "gialam")["routes"])
        self.assertTrue(calculate_routes(s, "socson", "phuxuyen")["routes"])


class NetworkAndSearchTests(unittest.TestCase):
    def test_osm_street_search_without_diacritics(self):
        self.assertTrue(any(item["kind"] == "osm_street" for item in search_places("Vo Chi Cong")))
    def test_all_demo_roads_use_cached_osm_geometry(self):
        self.assertEqual(len(ROADS), 111)
        for road in ROADS:
            self.assertEqual(road["geometry_source"], "osm_osrm", road["id"])
            self.assertGreater(len(road["coordinates"]), 2, road["id"])
            for point, node_id in ((road["coordinates"][0], road["a"]), (road["coordinates"][-1], road["b"])):
                node = NODES[node_id]
                self.assertLess(distance(point, [node["lat"], node["lng"]]), 1, road["id"])
            self.assertLess(nearest_road(*road["center"])[0], 0.01, road["id"])

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
