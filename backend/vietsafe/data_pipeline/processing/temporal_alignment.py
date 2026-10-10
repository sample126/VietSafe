"""Exact-bin dynamic alignment and explicit as-of availability gating; no filling."""

from datetime import datetime

from ..alignment import AlignedEnvironmentalValue, AlignmentInputError
from ..environment import EnvironmentInputError, utc_timestamp


def _utc(value):
    try:
        return utc_timestamp(value)
    except EnvironmentInputError as error:
        raise AlignmentInputError('INVALID_TIMESTAMP', str(error)) from error


def _datetime(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def canonical_timestamp(value):
    normalized = _utc(value)
    parsed = _datetime(normalized)
    if parsed.minute not in (0, 30) or parsed.second != 0 or parsed.microsecond != 0:
        raise AlignmentInputError('NON_CANONICAL_BIN', 'Expected a 30-minute bin end at :00/:30')
    return normalized


def validate_target(timestamp, as_of):
    timestamp, as_of = canonical_timestamp(timestamp), _utc(as_of)
    if _datetime(as_of) < _datetime(timestamp):
        raise AlignmentInputError('AS_OF_BEFORE_TIMESTAMP', 'as_of must be >= timestamp')
    return timestamp, as_of


def temporal_reason(grid, timestamp, as_of):
    """Priority: future observation, unavailable as-of, then exact-match mismatch."""
    timestamp, as_of = validate_target(timestamp, as_of)
    if grid.source_type == 'dem':
        raise AlignmentInputError('STATIC_SOURCE', 'DEM must use static alignment')
    target = _datetime(timestamp)
    observed, available = _datetime(grid.observed_at), _datetime(grid.available_at)
    if observed > target:
        return 'FUTURE_OBSERVATION'
    if available > _datetime(as_of):
        return 'NOT_AVAILABLE_AS_OF'
    if grid.source_type == 'gpm':
        end = _datetime(grid.metadata['interval_end'])
        if end != target or observed != end:
            return 'NO_EXACT_TEMPORAL_MATCH'
    elif observed != target:
        return 'NO_EXACT_TEMPORAL_MATCH'
    return None


def align_temporal(sample, timestamp, as_of, *, conflict=False):
    timestamp, as_of = validate_target(timestamp, as_of)
    if sample.source_type == 'dem':
        raise AlignmentInputError('STATIC_SOURCE', 'DEM must not be expanded into dynamic rows')
    grid = sample.grid
    reason = temporal_reason(grid, timestamp, as_of) if grid is not None else 'NO_SOURCE_GRID'
    reason = reason or ('SOURCE_CONFLICT' if conflict else None) or sample.missing_reason
    method = 'gpm-exact-interval-end-v1' if sample.source_type == 'gpm' else 'smap-exact-time-v1'
    return AlignedEnvironmentalValue(sample, timestamp, as_of, method,
                                     None if reason else sample.value, reason)


def align_static(sample):
    if sample.source_type != 'dem':
        raise AlignmentInputError('DYNAMIC_SOURCE', 'Only DEM is a static source')
    return AlignedEnvironmentalValue(sample, None, None, 'static-no-temporal-alignment-v1',
                                     sample.value, sample.missing_reason)
