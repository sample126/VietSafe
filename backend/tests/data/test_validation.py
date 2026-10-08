import copy
import unittest
from dataclasses import replace
from datetime import datetime

from vietsafe.data_pipeline.registry import RoadRegistry, checksum
from vietsafe.data_pipeline.validation import validate_dataset, validate_observation

from .helpers import demo


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.registry, self.observations, self.catalog = demo()
        self.payload = self.observations[0].to_dict()

    def issues(self, **changes):
        payload = copy.deepcopy(self.payload)
        payload.update(changes)
        return validate_observation(payload, self.registry, source_catalog=self.catalog)

    def codes(self, **changes):
        return {issue.code for issue in self.issues(**changes)}

    def test_valid_observation(self):
        self.assertEqual(self.issues(), [])

    def test_negative_rainfall_rejected(self):
        for field in ("rainfall_30m", "rainfall_1h", "rainfall_3h"):
            with self.subTest(field=field):
                self.assertIn("NEGATIVE_VALUE", self.codes(**{field: -1}))

    def test_numeric_ranges(self):
        for field, value in (
            ("soil_moisture", 1.1),
            ("soil_moisture", -0.1),
            ("slope", 90),
            ("slope", -1),
            ("traffic_speed", -1),
            ("free_flow_speed", 0),
            ("current_flood_depth", -1),
            ("historical_flood_count", -1),
            ("historical_flood_count", 0.5),
            ("latitude", 91),
            ("longitude", 181),
        ):
            with self.subTest(field=field, value=value):
                self.assertTrue(self.issues(**{field: value}))

    def test_quality_score_range(self):
        for value in (-0.1, 1.1):
            self.assertIn("OUT_OF_RANGE", self.codes(quality_score=value))

    def test_unknown_road_rejected(self):
        partial = RoadRegistry(self.registry.network_version, list(self.registry)[1:])
        codes = {
            e.code for e in validate_observation(self.payload, partial, source_catalog=self.catalog)
        }
        self.assertIn("UNKNOWN_ROAD", codes)

    def test_network_version_mismatch(self):
        self.assertIn("NETWORK_MISMATCH", self.codes(network_version="hanoi-demo-other"))

    def test_timestamp_timezone(self):
        for value in (
            "2026-10-08T02:30:00",
            "2026-10-08T09:30:00+07:00",
            datetime(2026, 10, 8, 2, 30),
        ):
            with self.subTest(value=value):
                self.assertIn("INVALID_TIMESTAMP", self.codes(timestamp=value))

    def test_timestamp_grid_and_calendar(self):
        self.assertIn("OFF_GRID", self.codes(timestamp="2026-10-08T02:15:00Z"))
        self.assertIn("INVALID_TIMESTAMP", self.codes(timestamp="2026-02-30T02:30:00Z"))

    def test_as_of_before_timestamp_rejected(self):
        self.assertIn("AS_OF_BEFORE_TIMESTAMP", self.codes(as_of="2026-10-08T02:00:00Z"))

    def test_nonfinite_raw_payload_rejected(self):
        for field in ("elevation", "twi", "latitude", "quality_score"):
            for value in (float("nan"), float("inf"), 10**400):
                with self.subTest(field=field):
                    self.assertIn("NON_FINITE", self.codes(**{field: value}))

    def test_rainfall_window_order(self):
        self.assertIn("RAINFALL_ORDER", self.codes(rainfall_30m=20, rainfall_1h=10))

    def test_depth_status_consistency(self):
        self.assertIn("FLOOD_INCONSISTENT", self.codes(current_flood_depth=5, flood_status=False))
        self.assertIn("FLOOD_INCONSISTENT", self.codes(current_flood_depth=0, flood_status=None))

    def test_null_depth_with_true_status_allowed(self):
        # Remove depth provenance and provide a missing reason; do not invent a measured depth.
        self.payload["current_flood_depth"] = None
        self.payload["flood_status"] = True
        for src in self.payload["source"]:
            src["fields"] = [f for f in src["fields"] if f != "current_flood_depth"]
            ref = self.catalog[src["record_ref"]]
            ref["fields"] = src["fields"][:]
            ref["input"]["values"] = {f: self.payload[f] for f in src["fields"]}
            ref["checksum"] = checksum(ref["input"])
        self.payload["quality_flags"] = [
            f for f in self.payload["quality_flags"] if f["field"] != "current_flood_depth"
        ]
        self.payload["quality_flags"].append(
            {"field": "current_flood_depth", "code": "missing", "detail": "No depth measurement"}
        )
        self.assertEqual(self.issues(), [])

    def test_null_needs_reason(self):
        flags = [f for f in self.payload["quality_flags"] if f["field"] != "soil_moisture"]
        self.assertIn("MISSING_REASON", self.codes(quality_flags=flags))

    def test_missing_and_duplicate_source(self):
        self.assertIn("MISSING_SOURCE", self.codes(source=self.payload["source"][1:]))
        self.assertIn(
            "DUPLICATE_SOURCE",
            self.codes(source=self.payload["source"] + [self.payload["source"][0]]),
        )

    def test_available_at_and_observed_at(self):
        for field, expected in (
            ("observed_at", "FUTURE_OBSERVATION"),
            ("available_at", "SOURCE_NOT_AVAILABLE"),
        ):
            sources = copy.deepcopy(self.payload["source"])
            sources[0][field] = "2026-10-08T03:00:00Z"
            self.assertIn(expected, self.codes(source=sources))

    def test_source_expiry_boundary(self):
        sources = copy.deepcopy(self.payload["source"])
        sources[1]["valid_until"] = self.payload["timestamp"]
        self.assertIn("STALE_SOURCE", self.codes(source=sources))
        sources[1]["valid_until"] = None
        self.assertIn("TTL_REQUIRED", self.codes(source=sources))

    def test_provenance_resolution_and_checksum(self):
        self.assertIn(
            "UNRESOLVED_SOURCE", {e.code for e in validate_observation(self.payload, self.registry)}
        )
        ref = self.catalog[self.payload["source"][0]["record_ref"]]
        ref["input"]["values"]["latitude"] = 0
        self.assertIn("CHECKSUM_MISMATCH", self.codes())
        self.assertIn("LINEAGE_VALUE_MISMATCH", self.codes())

    def test_provenance_metadata_mismatch(self):
        sources = copy.deepcopy(self.payload["source"])
        sources[0]["product"] = "another-product"
        self.assertIn("LINEAGE_MISMATCH", self.codes(source=sources))

    def test_quality_score_recomputed(self):
        self.assertIn("QUALITY_SCORE_MISMATCH", self.codes(quality_score=0.9))

    def test_demo_isolation(self):
        self.assertIn("SIMULATED_OBSERVED", self.codes(data_mode="observed"))
        sources = copy.deepcopy(self.payload["source"])
        sources[0]["provider"] = "nasa_gpm"
        self.assertIn("DEMO_SOURCE_REQUIRED", self.codes(source=sources))

    def test_simulated_flag_required(self):
        flags = [f for f in self.payload["quality_flags"] if f["field"] != "latitude"]
        self.assertIn("METHOD_FLAG_REQUIRED", self.codes(quality_flags=flags))

    def test_spatial_match(self):
        self.assertIn("SPATIAL_MISMATCH", self.codes(latitude=21.05))

    def test_duplicate_observation(self):
        errors = validate_dataset(
            [self.observations[0]] * 2, self.registry, source_catalog=self.catalog
        )
        self.assertIn("DUPLICATE_OBSERVATION", {e.code for e in errors})

    def test_mixed_dataset_version(self):
        records = [
            self.observations[0],
            replace(self.observations[1], dataset_version="another-release"),
        ]
        self.assertIn(
            "MIXED_RELEASE",
            {e.code for e in validate_dataset(records, self.registry, source_catalog=self.catalog)},
        )

    def test_structured_error(self):
        issue = self.issues(rainfall_30m=-1)[0].to_dict()
        self.assertEqual(
            issue,
            {
                "field": "rainfall_30m",
                "code": "NEGATIVE_VALUE",
                "message": "rainfall_30m must be >= 0",
                "severity": "error",
            },
        )

    def test_empty_dataset(self):
        self.assertIn("EMPTY_DATASET", {e.code for e in validate_dataset([], self.registry)})

    def test_dataset_version_not_empty(self):
        self.assertIn("INVALID_VERSION", self.codes(dataset_version=""))
        self.assertIn("INVALID_VERSION", self.codes(dataset_version="../../outside"))

    def test_malformed_nested_values_return_errors(self):
        for changes in (
            {"source": [None]},
            {"source": {}},
            {"quality_flags": [None]},
            {"quality_flags": False},
            {"road_id": []},
            {"data_mode": {}},
            {"source": [dict(self.payload["source"][0], fields=[{}])]},
        ):
            with self.subTest(changes=changes):
                self.assertTrue(self.issues(**changes))


class ObservedQualityTests(unittest.TestCase):
    def test_observed_score_and_carried_forward_weight(self):
        # Entirely artificial unit-test input; not an observed dataset release.
        demo_registry, records, catalog = demo()
        registry = RoadRegistry(
            "test-network-v1",
            [
                replace(r, network_version="test-network-v1", source_type="test")
                for r in demo_registry
            ],
        )
        payload = records[0].to_dict()
        payload.update(
            data_mode="observed",
            network_version=registry.network_version,
            quality_score=round(4 / 12, 4),
        )
        payload["quality_flags"] = [f for f in payload["quality_flags"] if f["code"] != "simulated"]
        for src in payload["source"]:
            src.update(provider="derived", method="derived")
            ref = catalog[src["record_ref"]]
            ref.update(src)
            ref["input"]["registry_checksum"] = registry.checksum
            ref["checksum"] = checksum(ref["input"])
        self.assertEqual(validate_observation(payload, registry, source_catalog=catalog), [])
        dynamic = payload["source"][1]
        dynamic["method"] = "carry_forward"
        catalog[dynamic["record_ref"]]["method"] = "carry_forward"
        for field in dynamic["fields"]:
            payload["quality_flags"].append(
                {"field": field, "code": "carried_forward", "detail": "Synthetic test of weighting"}
            )
        payload["quality_score"] = round(2.5 / 12, 4)
        self.assertEqual(validate_observation(payload, registry, source_catalog=catalog), [])
