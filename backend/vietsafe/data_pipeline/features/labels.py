"""Generic supervised targets; never inferred from simulated application state."""

from dataclasses import dataclass
from collections.abc import Mapping

from ..environment import _freeze, _thaw, utc_timestamp
from ..processing.temporal_alignment import canonical_timestamp
from ..registry import ROAD_PATTERN, canonical_bytes, checksum, finite_number
from .engineering import dt, require


@dataclass(frozen=True)
class RoadTarget:
    road_id: str
    observed_at: str
    available_at: str
    target_name: str
    value: float | None
    units: str
    source_metadata: dict
    event_id: str | None = None

    def __post_init__(self):
        require(isinstance(self.road_id, str) and ROAD_PATTERN.fullmatch(self.road_id), 'Invalid target road ID')
        object.__setattr__(self, 'observed_at', canonical_timestamp(self.observed_at))
        object.__setattr__(self, 'available_at', utc_timestamp(self.available_at))
        require(dt(self.available_at) >= dt(self.observed_at), 'Label available_at precedes observation')
        require(isinstance(self.target_name, str) and self.target_name.strip(), 'Target name required')
        require(isinstance(self.units, str) and self.units.strip(), 'Target units required')
        require(self.value is None or finite_number(self.value), 'Target must be finite numeric or null')
        require(self.event_id is None or isinstance(self.event_id, str) and self.event_id.strip(), 'Invalid event ID')
        require(isinstance(self.source_metadata, Mapping) and
                self.source_metadata.get('data_kind') in ('synthetic', 'observed') and
                isinstance(self.source_metadata.get('source_uri'), str) and
                bool(self.source_metadata['source_uri']), 'Target provenance required')
        if self.source_metadata['data_kind'] == 'synthetic':
            require(self.source_metadata.get('fixture_notice') ==
                    'SYNTHETIC TEST FIXTURE — NOT PRODUCTION FLOOD GROUND TRUTH', 'Synthetic notice required')
        metadata = _thaw(self.source_metadata)
        canonical_bytes(metadata)
        object.__setattr__(self, 'source_metadata', _freeze(metadata))

    def to_dict(self):
        return dict(road_id=self.road_id, observed_at=self.observed_at, available_at=self.available_at,
                    target_name=self.target_name, value=self.value, units=self.units,
                    source_metadata=_thaw(self.source_metadata), event_id=self.event_id)

    def checksum(self):
        return checksum(self.to_dict())
