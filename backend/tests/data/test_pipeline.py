import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from vietsafe.core.network import ROADS
from vietsafe.core.simulation import build_snapshot
from vietsafe.data_pipeline.adapters.demo import load_demo_registry
from vietsafe.data_pipeline.config import DataPaths
from vietsafe.data_pipeline.exceptions import DataValidationError, ReleaseExistsError
from vietsafe.data_pipeline.manifest import create_manifest, publish_release
from vietsafe.data_pipeline.pipeline import run_pipeline
from vietsafe.data_pipeline.registry import canonical_bytes
from vietsafe.data_pipeline.validation import validate_dataset

from .helpers import REQUEST, TEST_COMMIT, demo


class PipelineTests(unittest.TestCase):
    def run_demo(self, **overrides):
        return run_pipeline(**{**REQUEST, "code_commit": TEST_COMMIT, **overrides})

    def test_demo_adapter(self):
        registry, observations, catalog = demo()
        self.assertEqual(len(observations), 36)
        self.assertEqual(validate_dataset(observations, registry, source_catalog=catalog), [])
        self.assertTrue(all(o.data_mode == "demo" and o.quality_score == 0 for o in observations))
        self.assertTrue(
            all(o.rainfall_30m is None and o.soil_moisture is None for o in observations)
        )
        self.assertTrue(
            all(any("DEMO_VALUE" in f.detail for f in o.quality_flags) for o in observations)
        )
        unknown = next(o for o in observations if o.road_id == "HN-029")
        self.assertIsNone(unknown.traffic_speed)
        self.assertIsNone(unknown.current_flood_depth)
        self.assertIsNone(unknown.flood_status)

    def test_manifest_generation(self):
        result = self.run_demo()
        manifest = result.manifest.to_dict()
        self.assertEqual(manifest["record_count"], 36)
        self.assertEqual(manifest["road_count"], 36)
        self.assertEqual(manifest["network_version"], result.registry.network_version)
        self.assertEqual(manifest["schema_version"], "0.1.0")
        self.assertEqual(manifest["data_mode"], "demo")
        self.assertEqual(manifest["code_commit"], TEST_COMMIT)
        self.assertTrue(all(s["license"] == "MIT" and s["checksum"] for s in manifest["sources"]))
        self.assertIsNone(result.manifest_path)
        # Canonical manifest is not mutable through its returned mapping.
        manifest["record_count"] = 0
        self.assertEqual(result.manifest.to_dict()["record_count"], 36)

    def test_pipeline_deterministic(self):
        a, b = self.run_demo(), self.run_demo()
        self.assertEqual(a.observations, b.observations)
        self.assertEqual(a.manifest.to_dict(), b.manifest.to_dict())
        self.assertEqual(a.summary(), b.summary())

    def test_manifest_input_order_independent(self):
        registry, observations, catalog = demo()
        manifest = create_manifest(
            observations[::-1],
            registry,
            source_catalog=dict(reversed(list(catalog.items()))),
            created_at=REQUEST["created_at"],
            code_commit=TEST_COMMIT,
            processing_parameters=self.run_demo().manifest.to_dict()["processing_parameters"],
        )
        self.assertEqual(manifest.to_dict(), self.run_demo().manifest.to_dict())

    def test_invalid_pipeline_timestamp_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = DataPaths(Path(tmp) / "output")
            with self.assertRaises((DataValidationError, ValueError)):
                run_pipeline(
                    **dict(REQUEST, timestamp="2026-10-08T02:15:00Z"),
                    code_commit=TEST_COMMIT,
                    paths=paths,
                    write=True,
                )
            self.assertFalse(paths.root.exists())

    def test_release_write_and_checksums(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_demo(paths=DataPaths(tmp), write=True)
            manifest = json.loads(result.manifest_path.read_text())
            for artifact in manifest["artifacts"].values():
                self.assertEqual(
                    hashlib.sha256((Path(tmp) / artifact["path"]).read_bytes()).hexdigest(),
                    artifact["sha256"],
                )
            records = (
                (Path(tmp) / manifest["artifacts"]["observations"]["path"]).read_text().splitlines()
            )
            self.assertEqual(len(records), 36)
            self.assertEqual(json.loads(records[0])["soil_moisture"], None)
            self.assertEqual(list((Path(tmp) / "manifests").glob("*.lock")), [])

    def test_release_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = DataPaths(tmp)
            result = self.run_demo(paths=paths, write=True)
            before = result.manifest_path.read_bytes()
            with self.assertRaises(ReleaseExistsError):
                self.run_demo(paths=paths, write=True)
            self.assertEqual(result.manifest_path.read_bytes(), before)

    def test_concurrent_release_only_one_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_demo()
            paths = DataPaths(tmp)

            def attempt():
                try:
                    publish_release(result.manifest, result.observations, result.registry, paths)
                    return "ok"
                except ReleaseExistsError:
                    return "exists"

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(lambda _: attempt(), range(2)))
            self.assertCountEqual(outcomes, ["ok", "exists"])
            self.assertEqual(len(list(paths.manifests.glob("*.json"))), 1)

    def test_stale_lock_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = DataPaths(tmp)
            paths.ensure_directories()
            lock = paths.manifests / (REQUEST["dataset_version"] + ".lock")
            lock.write_text("previous writer")
            with self.assertRaises(ReleaseExistsError):
                self.run_demo(paths=paths, write=True)
            self.assertEqual(lock.read_text(), "previous writer")

    def test_publication_failure_rolls_back_owned_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = DataPaths(tmp)
            with patch(
                "vietsafe.data_pipeline.manifest.os.fsync", side_effect=OSError("disk error")
            ):
                with self.assertRaises(OSError):
                    self.run_demo(paths=paths, write=True)
            self.assertFalse((paths.processed / REQUEST["dataset_version"]).exists())
            self.assertFalse((paths.manifests / (REQUEST["dataset_version"] + ".json")).exists())
            self.run_demo(paths=paths, write=True)

    def test_manifest_cannot_publish_modified_records(self):
        result = self.run_demo()
        changed = (replace(result.observations[0], quality_score=0.5),) + result.observations[1:]
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(DataValidationError):
            publish_release(result.manifest, changed, result.registry, DataPaths(tmp))

    def test_manifest_rejects_invalid_commit_and_created_time(self):
        for changes in (
            {"code_commit": ""},
            {"code_commit": "main"},
            {"created_at": "2026-10-08T02:00:00Z"},
        ):
            with self.subTest(changes=changes), self.assertRaises(DataValidationError):
                run_pipeline(**{**REQUEST, "code_commit": TEST_COMMIT, **changes})

    def test_pipeline_no_network(self):
        with patch("socket.socket", side_effect=AssertionError("offline only")):
            self.assertEqual(self.run_demo().summary()["record_count"], 36)

    def test_existing_runtime_not_mutated(self):
        before_network = canonical_bytes(ROADS)
        before_snapshot = build_snapshot("rain", now=1791426600)
        self.run_demo()
        self.assertEqual(canonical_bytes(ROADS), before_network)
        self.assertEqual(build_snapshot("rain", now=1791426600), before_snapshot)
        self.assertEqual(load_demo_registry().network_version, "hanoi-demo-d1bfac3198c0f477")

    def test_cli_dry_run_has_no_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = [
                sys.executable,
                "-m",
                "vietsafe.data_pipeline",
                "--data-root",
                str(Path(tmp) / "absent"),
            ]
            for key, value in dict(REQUEST, code_commit=TEST_COMMIT).items():
                args.extend(["--" + key.replace("_", "-"), value])
            result = subprocess.run(
                args,
                check=True,
                capture_output=True,
                text=True,
                cwd=Path(__file__).resolve().parents[2],
            )
            self.assertEqual(json.loads(result.stdout)["record_count"], 36)
            self.assertFalse((Path(tmp) / "absent").exists())
