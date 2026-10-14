"""Intermediate alignment records, distinct from RoadObservation/feature rows."""

from dataclasses import dataclass

from .environment import EnvironmentalGrid, VARIABLES, _thaw
from .registry import canonical_bytes, checksum

ALIGNMENT_VERSION = 'alignment-v1'
SPATIAL_METHOD = 'representative-point-nearest-cell-v1'


class AlignmentInputError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class RoadGridSample:
    road_id: str
    network_version: str
    source_type: str
    road_lat: float
    road_lon: float
    grid: EnvironmentalGrid | None = None
    grid_row: int | None = None
    grid_col: int | None = None
    cell_lat: float | None = None
    cell_lon: float | None = None
    value: float | None = None
    missing_reason: str | None = None
    grid_checksum: str | None = None

    def to_dict(self):
        grid = self.grid
        variable, units = VARIABLES[self.source_type]
        return dict(
            road_id=self.road_id, network_version=self.network_version,
            source_type=self.source_type, variable=variable, units=units,
            product=grid.product if grid else None,
            product_version=grid.product_version if grid else None,
            source_observed_at=grid.observed_at if grid else None,
            source_available_at=grid.available_at if grid else None,
            source_uri=grid.source_uri if grid else None,
            raw_checksum=grid.raw_checksum if grid else None,
            # Copy only provenance, not the entire raster for every road record.
            source_metadata=_thaw(grid.metadata) if grid else None,
            grid_checksum=self.grid_checksum,
            spatial_method=SPATIAL_METHOD,
            road_lat=self.road_lat, road_lon=self.road_lon,
            grid_row=self.grid_row, grid_col=self.grid_col,
            cell_lat=self.cell_lat, cell_lon=self.cell_lon,
            value=self.value, missing_reason=self.missing_reason,
        )


@dataclass(frozen=True)
class AlignedEnvironmentalValue:
    sample: RoadGridSample
    timestamp: str | None
    as_of: str | None
    temporal_method: str
    value: float | None
    missing_reason: str | None

    def to_dict(self):
        return dict(self.sample.to_dict(), timestamp=self.timestamp, as_of=self.as_of,
                    temporal_method=self.temporal_method, value=self.value,
                    missing_reason=self.missing_reason, alignment_version=ALIGNMENT_VERSION)


@dataclass(frozen=True)
class AlignmentIssue:
    code: str
    road_id: str
    source_type: str
    timestamp: str | None
    as_of: str | None
    grid_checksum: str | None

    def to_dict(self):
        return dict(code=self.code, road_id=self.road_id, source_type=self.source_type,
                    timestamp=self.timestamp, as_of=self.as_of, grid_checksum=self.grid_checksum)


def record_key(record):
    value = record.to_dict()
    return (value['timestamp'] or '', value['road_id'], value['variable'],
            value['source_type'], canonical_bytes(value))


@dataclass(frozen=True)
class AlignmentResult:
    network_version: str
    registry_checksum: str
    static: tuple[AlignedEnvironmentalValue, ...]
    dynamic: tuple[AlignedEnvironmentalValue, ...]
    issues: tuple[AlignmentIssue, ...]

    def __post_init__(self):
        object.__setattr__(self, 'static', tuple(sorted(self.static, key=record_key)))
        object.__setattr__(self, 'dynamic', tuple(sorted(self.dynamic, key=record_key)))
        object.__setattr__(self, 'issues', tuple(sorted(
            self.issues, key=lambda issue: canonical_bytes(issue.to_dict()))))

    def to_dict(self):
        return dict(network_version=self.network_version, registry_checksum=self.registry_checksum,
                    alignment_version=ALIGNMENT_VERSION,
                    static=[record.to_dict() for record in self.static],
                    dynamic=[record.to_dict() for record in self.dynamic],
                    issues=[issue.to_dict() for issue in self.issues],
                    summary=dict(static_count=len(self.static), dynamic_count=len(self.dynamic),
                                 issue_count=len(self.issues)))

    def to_json(self):
        return canonical_bytes(self.to_dict()).decode('utf-8')

    def checksum(self):
        return checksum(self.to_dict())
