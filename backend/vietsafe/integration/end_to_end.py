"""Contract-only offline orchestration; never a prediction/runtime provider."""

from dataclasses import dataclass

from ..data_pipeline.registry import RoadRegistry
from .api_contracts import ArtifactApiBundle
from .api_projection import build_artifact_api_bundle
from .context_contracts import IntegrationContext
from .context_guard import build_integration_context
from .contracts import ForecastOutput, require, sequence
from .map_contracts import MapNetwork
from .registry_map import build_map_network
from .registry_routing import build_routing_network
from .routing_contracts import RoutingNetwork


@dataclass(frozen=True)
class ContractPipelineResult:
    """Frozen typed artifacts; forecast containers are immutable tuples."""
    routing_network: RoutingNetwork
    map_network: MapNetwork
    forecasts: tuple[ForecastOutput, ...]
    context: IntegrationContext
    api_bundle: ArtifactApiBundle


def run_contract_pipeline(*, registry, mode, generated_at, forecasts=()):
    """Compose existing validated contracts without IO or generated predictions.

    Registry must be a RoadRegistry. Optional forecasts are caller-supplied
    ForecastOutput objects or serialized contract dictionaries, never a model.
    Test synthetic fixtures belong in tests, not this production package.
    """
    require(isinstance(registry, RoadRegistry), 'registry', 'RoadRegistry required')
    sequence(forecasts, 'forecasts')
    validated = tuple(sorted(
        (ForecastOutput(f.to_dict() if isinstance(f, ForecastOutput) else f) for f in forecasts),
        key=lambda f: f.to_dict()['horizon_minutes']))
    routing = build_routing_network(registry)
    map_network = build_map_network(registry)
    context = build_integration_context(mode=mode, map_network=map_network,
                                         routing_network=routing, forecasts=validated)
    bundle = build_artifact_api_bundle(context=context, map_network=map_network,
                                       forecasts=validated, generated_at=generated_at)
    return ContractPipelineResult(routing, map_network, validated, context, bundle)
