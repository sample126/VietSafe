"""Six evidence-based features; exact rain windows, no filling/scaling/network."""

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..alignment import ALIGNMENT_VERSION, AlignmentResult
from ..environment import _freeze, _thaw, utc_timestamp
from ..processing.temporal_alignment import canonical_timestamp
from ..registry import canonical_bytes, checksum, finite_number

FEATURE_VERSION = 'features-v1'
FEATURE_NAMES = ('precipitation_rate_mm_h', 'rain_30m_mm', 'rain_1h_mm',
                 'rain_3h_mm', 'soil_moisture', 'elevation_m')
FEATURE_UNITS = ('mm/h', 'mm', 'mm', 'mm', 'm3/m3', 'm')
STEP = timedelta(minutes=30)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dt(value):
    return datetime.fromisoformat(utc_timestamp(value).replace('Z', '+00:00'))


def shift(value, steps):
    return (dt(value) + steps * STEP).isoformat().replace('+00:00', 'Z')


@dataclass(frozen=True)
class RoadFeatureRow:
    road_id: str
    network_version: str
    timestamp: str
    as_of: str
    values: tuple
    missing_reasons: tuple
    provenance: dict

    def __post_init__(self):
        object.__setattr__(self, 'timestamp', canonical_timestamp(self.timestamp))
        object.__setattr__(self, 'as_of', utc_timestamp(self.as_of))
        require(dt(self.as_of) >= dt(self.timestamp), 'Feature as_of precedes timestamp')
        require(isinstance(self.road_id, str) and self.road_id and
                isinstance(self.network_version, str) and self.network_version, 'Missing row identity')
        values, reasons = tuple(self.values), tuple(self.missing_reasons)
        require(len(values) == len(reasons) == len(FEATURE_NAMES), 'Invalid feature shape')
        for index, (value, reason) in enumerate(zip(values, reasons)):
            require(value is None or finite_number(value), 'Feature must be finite or null')
            require((value is None and isinstance(reason, str) and bool(reason)) or
                    (value is not None and reason is None), 'Missing reason/value mismatch')
            if value is not None:
                require(index >= 4 or value >= 0, 'Negative precipitation feature')
                require(index != 4 or 0 <= value <= 1, 'Invalid soil moisture')
        require(isinstance(self.provenance, Mapping), 'Missing feature provenance')
        require(self.provenance.get('feature_version') == FEATURE_VERSION and
                self.provenance.get('alignment_version') == ALIGNMENT_VERSION,
                'Unsupported feature/alignment version')
        provenance = _thaw(self.provenance)
        canonical_bytes(provenance)
        object.__setattr__(self, 'values', values)
        object.__setattr__(self, 'missing_reasons', reasons)
        object.__setattr__(self, 'provenance', _freeze(provenance))

    @property
    def mask(self):
        return tuple(value is not None for value in self.values)

    def to_dict(self):
        return dict(road_id=self.road_id, network_version=self.network_version,
                    timestamp=self.timestamp, as_of=self.as_of, feature_version=FEATURE_VERSION,
                    features=dict(zip(FEATURE_NAMES, self.values)),
                    mask=dict(zip(FEATURE_NAMES, self.mask)),
                    missing_reasons=dict(zip(FEATURE_NAMES, self.missing_reasons)),
                    provenance=_thaw(self.provenance))

    def checksum(self):
        return checksum(self.to_dict())


def _validate_record(record, registry, static):
    require(isinstance(record, dict), 'Expected serialized aligned record')
    require(record.get('network_version') == registry.network_version and
            registry.get(record.get('road_id')) is not None, 'Aligned road/network mismatch')
    require(record.get('alignment_version') == ALIGNMENT_VERSION, 'Alignment version mismatch')
    source = record.get('source_type')
    require(source in (('dem',) if static else ('gpm', 'smap')), 'Wrong aligned source type')
    variable, units = {'dem': ('elevation', 'm'), 'gpm': ('precipitation_rate', 'mm/h'),
                       'smap': ('soil_moisture', 'm3/m3')}[source]
    require((record.get('variable'), record.get('units')) == (variable, units), 'Aligned unit/variable mismatch')
    value = record.get('value')
    require(value is None or finite_number(value), 'Non-finite/invalid aligned value')
    if value is not None:
        require(source != 'gpm' or value >= 0, 'Negative rate')
        require(source != 'smap' or 0 <= value <= 1, 'Invalid soil moisture')
        require(record.get('missing_reason') is None, 'Unusable record exposes value')
        for name in ('raw_checksum', 'grid_checksum'):
            require(isinstance(record.get(name), str) and
                    re.fullmatch('[0-9a-f]{64}', record[name]), 'Missing source checksum')
        for name in ('product', 'product_version', 'source_uri'):
            require(isinstance(record.get(name), str) and record[name], 'Missing source provenance')
    else:
        require(isinstance(record.get('missing_reason'), str) and record['missing_reason'],
                'Null aligned value requires missing_reason')
    if static:
        require(record.get('timestamp') is None and record.get('as_of') is None, 'DEM must remain static')
    else:
        stamp = canonical_timestamp(record.get('timestamp'))
        require(dt(record.get('as_of')) >= dt(stamp), 'Invalid aligned as_of')
        if value is not None:
            dt(record.get('source_observed_at'))
            dt(record.get('source_available_at'))
    canonical_bytes(record)


def _pick(records, timestamp, as_of, source):
    """One usable source only; no cross-product priority and no backfill reinterpretation."""
    usable, reasons = {}, set()
    for record in records:
        reason = record.get('missing_reason')
        if source != 'dem':
            if dt(record['as_of']) > dt(as_of):
                reasons.add('ALIGNED_AS_OF_AFTER_FEATURE_AS_OF')
                continue
            if record.get('source_observed_at') is not None and dt(record['source_observed_at']) > dt(timestamp):
                reasons.add('FUTURE_OBSERVATION')
                continue
            if record.get('source_available_at') is not None and dt(record['source_available_at']) > dt(as_of):
                reasons.add('NOT_AVAILABLE_AS_OF')
                continue
        elif record.get('source_available_at') is not None and dt(record['source_available_at']) > dt(as_of):
            reasons.add('STATIC_NOT_AVAILABLE_AS_OF')
            continue
        if reason:
            reasons.add(reason)
            continue
        if source != 'dem':
            if dt(record['source_observed_at']) != dt(timestamp):
                reasons.add('NO_EXACT_TEMPORAL_MATCH')
                continue
            if source == 'gpm':
                metadata = record.get('source_metadata') or {}
                try:
                    if dt(metadata['interval_end']) != dt(timestamp):
                        reasons.add('NO_EXACT_TEMPORAL_MATCH')
                        continue
                except (KeyError, ValueError, TypeError):
                    reasons.add('INVALID_GPM_INTERVAL')
                    continue
        # Ignore alignment snapshot time only when the evidence/value is identical.
        identity = {k: v for k, v in record.items() if k not in ('as_of',)}
        key = checksum(identity)
        if key not in usable or canonical_bytes(record) < canonical_bytes(usable[key]):
            usable[key] = record
    if len(usable) > 1:
        return None, 'MULTIPLE_SOURCE_CANDIDATES'
    if not usable:
        return None, '|'.join(sorted(reasons)) if reasons else 'NO_ALIGNED_RECORD'
    return next(iter(usable.values())), None


def build_features(registry, aligned, *, as_of):
    """Build one snapshot: one row per existing road/timestamp, as_of supplied explicitly.

    Accept AlignmentResult or its JSON object. No missing timestamp is synthesized.
    Rain windows use exact preceding bins, all selected at this same as_of.
    """
    as_of = utc_timestamp(as_of)
    document = aligned.to_dict() if isinstance(aligned, AlignmentResult) else aligned
    require(isinstance(document, dict) and document.get('alignment_version') == ALIGNMENT_VERSION,
            'Expected alignment-v1 result')
    require(document.get('network_version') == registry.network_version and
            document.get('registry_checksum') == registry.checksum, 'Registry snapshot mismatch')
    dynamic, static = {}, {}
    for kind, index in (('static', static), ('dynamic', dynamic)):
        require(isinstance(document.get(kind), list), 'Missing aligned records')
        for record in document[kind]:
            _validate_record(record, registry, kind == 'static')
            key = (record['road_id'], record['source_type']) if kind == 'static' else (
                record['road_id'], canonical_timestamp(record['timestamp']), record['source_type'])
            index.setdefault(key, []).append(record)
    keys = sorted({(stamp, road) for road, stamp, _ in dynamic if dt(stamp) <= dt(as_of)})
    selected = {}
    for road, stamp, source in dynamic:
        selected[(road, stamp, source)] = _pick(dynamic[(road, stamp, source)], stamp, as_of, source)

    def rate(road, stamp):
        return selected.get((road, stamp, 'gpm'), (None, 'NO_ALIGNED_RECORD'))

    def amount(road, stamp):
        record, reason = rate(road, stamp)
        if record is None:
            return None, reason, ()
        metadata = record['source_metadata']
        try:
            duration = dt(metadata['interval_end']) - dt(metadata['interval_start'])
        except (KeyError, ValueError, TypeError):
            return None, 'INVALID_GPM_INTERVAL', (checksum(record),)
        if duration != STEP:
            return None, 'GPM_INTERVAL_NOT_30_MINUTES', (checksum(record),)
        return record['value'] * .5, None, (checksum(record),)

    output = []
    for stamp, road in keys:
        current, reason = rate(road, stamp)
        values = [current['value'] if current else None]
        reasons = [reason]
        lineage = {FEATURE_NAMES[0]: [checksum(current)] if current else []}
        bins = {}
        for name, size in zip(FEATURE_NAMES[1:4], (1, 2, 6)):
            times = [shift(stamp, -offset) for offset in reversed(range(size))]
            amounts = [amount(road, time) for time in times]
            valid = all(value is not None for value, _, _ in amounts)
            try:
                total = math.fsum(value for value, _, _ in amounts) if valid else None
            except OverflowError:
                total = None
            values.append(total)
            reasons.append(None if total is not None else 'INCOMPLETE_RAIN_WINDOW' if not valid
                           else 'NUMERIC_OVERFLOW')
            lineage[name] = sorted({ref for _, _, refs in amounts for ref in refs})
            bins[name] = [{'timestamp': time, 'missing_reason': missing}
                          for time, (_, missing, _) in zip(times, amounts)]
        smap, smap_reason = selected.get((road, stamp, 'smap'), (None, 'NO_ALIGNED_RECORD'))
        dem, dem_reason = _pick(static.get((road, 'dem'), ()), stamp, as_of, 'dem')
        values.extend((smap['value'] if smap else None, dem['value'] if dem else None))
        reasons.extend((smap_reason, dem_reason))
        lineage['soil_moisture'] = [checksum(smap)] if smap else []
        lineage['elevation_m'] = [checksum(dem)] if dem else []
        output.append(RoadFeatureRow(road, registry.network_version, stamp, as_of, tuple(values),
                      tuple(reasons), dict(feature_version=FEATURE_VERSION, alignment_version=ALIGNMENT_VERSION,
                      registry_checksum=registry.checksum, source_record_checksums=lineage,
                      rain_bins=bins, rain_policy='exact-30m-complete-window-v1',
                      elevation_policy='static-road-network-join-v1')))
    return tuple(output)
