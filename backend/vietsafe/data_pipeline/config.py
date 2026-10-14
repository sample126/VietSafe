"""Portable paths; importing this module never creates directories."""

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[3] / "data"


@dataclass(frozen=True)
class DataPaths:
    root: Path

    def __post_init__(self):
        object.__setattr__(self, "root", Path(self.root).expanduser().resolve())

    @classmethod
    def from_env(cls):
        return cls(Path(os.environ.get("VIETSAFE_DATA_ROOT", DEFAULT_DATA_ROOT)))

    @property
    def raw(self):
        return self.root / "raw"

    @property
    def interim(self):
        return self.root / "interim"

    @property
    def processed(self):
        return self.root / "processed"

    @property
    def manifests(self):
        return self.root / "manifests"

    @property
    def registry(self):
        return self.root / "registry"

    @property
    def fixtures(self):
        return self.root / "fixtures"

    def ensure_directories(self):
        for path in (
            self.raw,
            self.interim,
            self.processed,
            self.manifests,
            self.registry,
            self.fixtures,
        ):
            path.mkdir(parents=True, exist_ok=True)


_DEFAULT_PATHS = DataPaths.from_env()
DATA_ROOT = _DEFAULT_PATHS.root
RAW_DIR = _DEFAULT_PATHS.raw
INTERIM_DIR = _DEFAULT_PATHS.interim
PROCESSED_DIR = _DEFAULT_PATHS.processed
MANIFEST_DIR = _DEFAULT_PATHS.manifests
NETWORK_REGISTRY_DIR = _DEFAULT_PATHS.registry
FIXTURE_DIR = _DEFAULT_PATHS.fixtures
