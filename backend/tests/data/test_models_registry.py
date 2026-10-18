import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from vietsafe.core.network import ROADS
from vietsafe.data_pipeline.adapters.demo import load_demo_registry
from vietsafe.data_pipeline.config import DataPaths
from vietsafe.data_pipeline.exceptions import DataValidationError
from vietsafe.data_pipeline.models import RoadObservation
from vietsafe.data_pipeline.quality import REASON_CODES, QualityReason
from vietsafe.data_pipeline.registry import RoadRegistry

from .helpers import demo


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = load_demo_registry()

    def test_registry_load(self):
        self.assertEqual(len(self.registry), 36)
        self.assertEqual([r.road_id for r in self.registry], [f"HN-{i:03}" for i in range(1, 37)])
        self.assertEqual(self.registry.get("HN-017").name, "Đường Láng")
        self.assertIsNone(self.registry.get("HN-099"))
        self.assertTrue(all(r.directionality == "both" for r in self.registry))

    def test_registry_unique_road_id(self):
        with self.assertRaises(DataValidationError) as result:
            RoadRegistry(self.registry.network_version, [self.registry.get("HN-001")] * 2)
        self.assertIn("DUPLICATE_ROAD_ID", [e.code for e in result.exception.issues])

    def test_registry_invalid_geometry_and_length(self):
        for change in (
            {"coordinates": ((91, 105), (21, 105))},
            {"coordinates": ((21, 105),) * 2},
            {"length_km": 0},
            {"length_km": True},
            {"name": ""},
            {"directionality": "sideways"},
            {"network_version": "another-v1"},
        ):
            with self.subTest(change=change), self.assertRaises(DataValidationError):
                RoadRegistry(
                    self.registry.network_version, [replace(self.registry.get("HN-001"), **change)]
                )

    def test_registry_deterministic_order_and_fingerprint(self):
        reversed_registry = RoadRegistry(self.registry.network_version, list(self.registry)[::-1])
        self.assertEqual(self.registry.checksum, reversed_registry.checksum)
        self.assertEqual(self.registry.network_version, "hanoi-demo-d1bfac3198c0f477")
        self.assertEqual([r.road_id for r in self.registry], [r["id"] for r in ROADS])

    def test_registry_does_not_expose_runtime_lists(self):
        payload = self.registry.to_dict()
        payload["roads"][0]["coordinates"][0][0] = 0
        self.assertEqual(ROADS[0]["coordinates"][0][0], 21.0313)
        self.assertEqual(self.registry.get("HN-001").coordinates[0][0], 21.0313)

    def test_representative_point_follows_polyline_length(self):
        road = replace(self.registry.get("HN-001"), coordinates=((0, 0), (0, 1), (0, 3)))
        self.assertEqual(road.representative_point(), (0.0, 1.5))

    def test_config_paths_portable_and_no_creation_on_init(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "nested" / "data"
            with patch.dict(os.environ, {"VIETSAFE_DATA_ROOT": str(root)}):
                paths = DataPaths.from_env()
            self.assertEqual(paths.root, root)
            self.assertFalse(root.exists())
            paths.ensure_directories()
            self.assertEqual(
                {p.name for p in root.iterdir()},
                {"raw", "interim", "processed", "manifests", "registry", "fixtures"},
            )


class ModelTests(unittest.TestCase):
    def setUp(self):
        _, self.observations, _ = demo()
        self.observation = self.observations[0]

    def test_model_round_trip(self):
        self.assertEqual(RoadObservation.from_json(self.observation.to_json()), self.observation)

    def test_nan_rejected(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value), self.assertRaises(DataValidationError):
                replace(self.observation, elevation=value)

    def test_null_not_converted_to_zero(self):
        record = RoadObservation.from_json(self.observation.to_json())
        self.assertIsNone(record.soil_moisture)
        self.assertEqual(record.current_flood_depth, 0)
        self.assertIs(record.flood_status, False)

    def test_model_does_not_coerce_types(self):
        for field, value in (("traffic_speed", True), ("rainfall_30m", "0"), ("flood_status", 0)):
            payload = self.observation.to_dict()
            payload[field] = value
            with self.subTest(field=field), self.assertRaises(DataValidationError):
                RoadObservation.from_dict(payload)

    def test_required_and_unknown_fields(self):
        payload = self.observation.to_dict()
        del payload["soil_moisture"]
        with self.assertRaises(DataValidationError):
            RoadObservation.from_dict(payload)
        payload = self.observation.to_dict()
        payload["extra"] = 1
        with self.assertRaises(DataValidationError):
            RoadObservation.from_dict(payload)

    def test_strict_json_rejects_nan_duplicate_keys(self):
        for value in ('{"x": NaN}', '{"x":1,"x":2}'):
            with self.subTest(value=value), self.assertRaises(DataValidationError):
                RoadObservation.from_json(value)

    def test_nested_nan_rejected(self):
        payload = self.observation.to_dict()
        payload["source"][0]["available_at"] = float("nan")
        with self.assertRaises(DataValidationError):
            RoadObservation.from_dict(payload)

    def test_to_dict_is_detached(self):
        payload = self.observation.to_dict()
        payload["source"][0]["fields"].clear()
        self.assertTrue(self.observation.source[0].fields)

    def test_quality_reasons_preserve_contract_vocabulary(self):
        self.assertEqual(REASON_CODES[QualityReason.DEMO_VALUE], "simulated")
        self.assertEqual(REASON_CODES[QualityReason.MISSING_GPM], "missing")
        schema = json.loads(
            (
                Path(__file__).resolve().parents[3] / "docs/schemas/road-observation.schema.json"
            ).read_text()
        )
        self.assertEqual(set(self.observation.to_dict()), set(schema["required"]))
        codes = schema["$defs"]["quality_flag"]["properties"]["code"]["enum"]
        self.assertTrue(all(c in codes for c in REASON_CODES.values()))


class DefensiveModelTests(unittest.TestCase):
    def test_model_freezes_caller_owned_sequences(self):
        _, records, _ = demo()
        sources = list(records[0].source)
        record = replace(records[0], source=sources)
        sources.clear()
        self.assertTrue(record.source)
        with self.assertRaises(DataValidationError):
            replace(record, source=[{}])

    def test_registry_version_read_only(self):
        registry = load_demo_registry()
        with self.assertRaises(AttributeError):
            registry.network_version = "another-version"
