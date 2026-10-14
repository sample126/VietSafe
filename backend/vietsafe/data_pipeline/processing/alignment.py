"""Offline alignment orchestration. Never creates features or runtime observations."""

from ..alignment import AlignmentInputError, AlignmentIssue, AlignmentResult
from ..environment import EnvironmentalGrid
from ..registry import RoadRegistry
from .spatial_alignment import sample_road
from .temporal_alignment import align_static, align_temporal, validate_target


def _sources(grids, source_type):
    """Dedup complete canonical payloads; quarantine conflicting observation identities."""
    groups = {}
    for grid in grids:
        if not isinstance(grid, EnvironmentalGrid) or grid.source_type != source_type:
            raise AlignmentInputError('INVALID_SOURCE', f'Expected {source_type} EnvironmentalGrid')
        key = (grid.source_type, grid.variable, grid.observed_at, grid.product, grid.product_version)
        groups.setdefault(key, {})[grid.checksum()] = grid
    result = []
    for key in sorted(groups):
        variants = groups[key]
        for digest, grid in sorted(variants.items()):
            result.append((grid, digest, len(variants) > 1))
    return result


def align_environment(registry, *, dem=None, gpm=(), smap=(), targets=()):
    """Align objects for (timestamp, as_of) pairs, retaining each source candidate.

    Distinct products remain separate; no implicit cross-product priority. Ineligible
    candidates have value=null and an explicit issue. Empty source lists yield a
    NO_SOURCE_GRID record per road/target. DEM is optional and emitted only once.
    """
    if not isinstance(registry, RoadRegistry):
        raise AlignmentInputError('INVALID_REGISTRY', 'Expected validated RoadRegistry')
    if dem is not None and (not isinstance(dem, EnvironmentalGrid) or dem.source_type != 'dem'):
        raise AlignmentInputError('INVALID_SOURCE', 'Expected DEM EnvironmentalGrid')
    normalized_targets = set()
    for target in targets:
        if not isinstance(target, (tuple, list)) or len(target) != 2:
            raise AlignmentInputError('INVALID_TARGET', 'Expected (timestamp, as_of) pairs')
        normalized_targets.add(validate_target(*target))
    sources = {'gpm': _sources(gpm, 'gpm'), 'smap': _sources(smap, 'smap')}
    static, dynamic = [], []
    dem_digest = dem.checksum() if dem is not None else None
    for road in registry:
        if dem is not None:
            static.append(align_static(sample_road(road, dem, grid_checksum=dem_digest)))
        for source_type, candidates in sources.items():
            for grid, digest, conflict in candidates or [(None, None, False)]:
                sample = sample_road(road, grid, source_type=source_type, grid_checksum=digest)
                for timestamp, as_of in sorted(normalized_targets):
                    dynamic.append(align_temporal(sample, timestamp, as_of, conflict=conflict))
    issues = tuple(AlignmentIssue(record.missing_reason, record.sample.road_id,
                                 record.sample.source_type, record.timestamp, record.as_of,
                                 record.sample.grid_checksum)
                   for record in static + dynamic if record.missing_reason)
    return AlignmentResult(registry.network_version, registry.checksum,
                           tuple(static), tuple(dynamic), issues)
