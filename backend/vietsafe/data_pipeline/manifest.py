"""Deterministic manifests and write-once offline release bundles."""

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .exceptions import DataValidationError, ReleaseExistsError, ValidationIssue
from .registry import VERSION_PATTERN, canonical_bytes, checksum
from .validation import parse_utc, require_valid


@dataclass(frozen=True)
class DatasetManifest:
    """Store canonical JSON internally so caller mutations cannot change the manifest."""

    _json: str

    def to_dict(self):
        return json.loads(self._json)

    @property
    def dataset_version(self):
        return self.to_dict()["dataset_version"]


def observation_bytes(observations):
    return b"".join(
        canonical_bytes(o.to_dict())
        for o in sorted(observations, key=lambda o: (o.road_id, o.timestamp))
    )


def create_manifest(
    observations, registry, *, source_catalog, created_at, code_commit, processing_parameters
):
    observations = tuple(sorted(observations, key=lambda o: (o.road_id, o.timestamp)))
    require_valid(observations, registry, source_catalog=source_catalog)
    issues = []
    try:
        created = parse_utc(created_at)
        if any(parse_utc(o.as_of) > created for o in observations):
            issues.append(
                ValidationIssue("created_at", "BEFORE_CUTOFF", "created_at must be >= every as_of")
            )
    except ValueError as error:
        issues.append(ValidationIssue("created_at", "INVALID_TIMESTAMP", str(error)))
    if not isinstance(code_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", code_commit):
        issues.append(
            ValidationIssue(
                "code_commit", "INVALID_COMMIT", "Require full lowercase Git commit SHA"
            )
        )
    if not isinstance(processing_parameters, dict):
        issues.append(
            ValidationIssue("processing_parameters", "INVALID_TYPE", "Expected parameter object")
        )
    if issues:
        raise DataValidationError(issues)
    times = [o.timestamp for o in observations]
    points = [c for r in registry for c in r.coordinates]
    flags = Counter(f.code for o in observations for f in o.quality_flags)
    record = observations[0]
    contents = {
        "dataset_version": record.dataset_version,
        "schema_version": record.schema_version,
        "network_version": registry.network_version,
        "created_at": created_at,
        "code_commit": code_commit,
        "data_mode": record.data_mode,
        "sources": [{"record_ref": key, **source_catalog[key]} for key in sorted(source_catalog)],
        "record_count": len(observations),
        "road_count": len({o.road_id for o in observations}),
        "time_range": {"start": min(times), "end": max(times)},
        "spatial_coverage": {
            "crs": "EPSG:4326",
            "bbox_order": "west,south,east,north",
            "bbox": [
                min(c[1] for c in points),
                min(c[0] for c in points),
                max(c[1] for c in points),
                max(c[0] for c in points),
            ],
        },
        "quality_statistics": {
            "policy": "coverage-v0.1",
            "mean_score": sum(o.quality_score for o in observations) / len(observations),
            "flags": dict(sorted(flags.items())),
        },
        "processing_parameters": processing_parameters,
        "artifacts": {
            "observations": {
                "path": f"processed/{record.dataset_version}/observations.jsonl",
                "sha256": hashlib.sha256(observation_bytes(observations)).hexdigest(),
            },
            "registry": {
                "path": f"processed/{record.dataset_version}/registry.json",
                "sha256": registry.checksum,
            },
        },
    }
    # This hash covers code, config, raw lineage and artifact hashes; no wall clock/random IDs.
    try:
        contents["content_sha256"] = checksum(contents)
        return DatasetManifest(canonical_bytes(contents).decode("utf-8"))
    except (ValueError, TypeError) as error:
        raise DataValidationError(
            [ValidationIssue("manifest", "INVALID_JSON", str(error))]
        ) from error


def publish_release(manifest, observations, registry, paths):
    """Write a new release; manifest is the last commit marker. Never replace an old release.

    An exclusive per-version lock covers cooperating writers on Windows/POSIX. A crash
    may leave a lock or uncommitted directory; callers must inspect it, never auto-overwrite.
    """
    payload = manifest.to_dict()
    version = manifest.dataset_version

    if not VERSION_PATTERN.fullmatch(version):
        raise DataValidationError(
            [ValidationIssue("dataset_version", "INVALID_VERSION", "Invalid release path")]
        )
    observations = tuple(observations)
    catalog = {
        s["record_ref"]: {k: v for k, v in s.items() if k != "record_ref"}
        for s in payload["sources"]
    }
    expected = create_manifest(
        observations,
        registry,
        source_catalog=catalog,
        created_at=payload["created_at"],
        code_commit=payload["code_commit"],
        processing_parameters=payload["processing_parameters"],
    )
    if expected.to_dict() != payload:
        raise DataValidationError(
            [
                ValidationIssue(
                    "manifest", "CONTENT_MISMATCH", "Manifest does not match release content"
                )
            ]
        )
    paths.ensure_directories()
    target = paths.processed / version
    marker = paths.manifests / (version + ".json")
    lock = paths.manifests / (version + ".lock")
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise ReleaseExistsError(f"Release {version} is locked") from error
    os.close(lock_fd)
    published = False
    marker_created = False
    try:
        if target.exists() or marker.exists():
            raise ReleaseExistsError(f"Release {version} already exists; choose a new version")
        with tempfile.TemporaryDirectory(prefix=".staging-", dir=paths.processed) as temp:
            staging = Path(temp) / "release"
            staging.mkdir()
            (staging / "observations.jsonl").write_bytes(observation_bytes(observations))
            (staging / "registry.json").write_bytes(canonical_bytes(registry.to_dict()))
            os.rename(staging, target)
            published = True
        # Exclusive create even if an external writer unexpectedly creates a marker.
        with marker.open("xb") as stream:
            marker_created = True
            stream.write(canonical_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if marker_created:
            marker.unlink()
        if published:
            shutil.rmtree(target)
        raise
    finally:
        lock.unlink()
    return marker
