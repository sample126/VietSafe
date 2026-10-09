"""Small deterministic fixtures; never touch the project's data output directories."""

import json
from pathlib import Path

from vietsafe.data_pipeline.adapters.demo import generate_demo_observations, load_demo_registry

REQUEST = json.loads(
    (Path(__file__).resolve().parents[3] / "data/fixtures/demo-request.json").read_text()
)
# Explicit test-only SHA. Real callers supply the checked-out code commit.
TEST_COMMIT = "a" * 40


def demo():
    registry = load_demo_registry()
    observations, catalog = generate_demo_observations(
        registry,
        dataset_version=REQUEST["dataset_version"],
        timestamp=REQUEST["timestamp"],
        as_of=REQUEST["as_of"],
    )
    return registry, observations, catalog
