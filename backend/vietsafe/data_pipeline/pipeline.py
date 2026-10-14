"""Offline demo orchestration, deliberately not called from the application service."""

from dataclasses import dataclass
from pathlib import Path

from .adapters.demo import RECIPE_VERSION, generate_demo_observations, load_demo_registry
from .config import DataPaths
from .manifest import DatasetManifest, create_manifest, publish_release
from .models import RoadObservation
from .registry import RoadRegistry
from .validation import require_valid


@dataclass(frozen=True)
class PipelineResult:
    registry: RoadRegistry
    observations: tuple[RoadObservation, ...]
    manifest: DatasetManifest
    manifest_path: Path | None

    def summary(self):
        metadata = self.manifest.to_dict()
        return {
            key: metadata[key]
            for key in (
                "dataset_version",
                "schema_version",
                "network_version",
                "data_mode",
                "record_count",
                "time_range",
                "content_sha256",
            )
        }


def run_pipeline(
    *,
    dataset_version,
    timestamp,
    as_of,
    created_at,
    code_commit,
    paths: DataPaths | None = None,
    write=False,
):
    registry = load_demo_registry()
    observations, catalog = generate_demo_observations(
        registry, dataset_version=dataset_version, timestamp=timestamp, as_of=as_of
    )
    require_valid(observations, registry, source_catalog=catalog)
    manifest = create_manifest(
        observations,
        registry,
        source_catalog=catalog,
        created_at=created_at,
        code_commit=code_commit,
        processing_parameters={
            "adapter": RECIPE_VERSION,
            "timestep_minutes": 30,
            "synthetic_speed_fraction": 0.8,
            "weather_sources": "not_collected",
        },
    )
    marker = (
        publish_release(manifest, observations, registry, paths or DataPaths.from_env())
        if write
        else None
    )
    return PipelineResult(registry, observations, manifest, marker)
