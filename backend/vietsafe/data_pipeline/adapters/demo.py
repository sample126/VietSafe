"""Read the existing hand-authored network; never call Forecast, HTTP or providers."""

from dataclasses import asdict
from datetime import timedelta

from ...core.network import ROADS
from ..models import QualityFlag, RoadObservation, SourceMetadata
from ..quality import FEATURE_FIELDS, SCHEMA_VERSION, SOURCE_FIELDS, STATIC_FIELDS, QualityReason
from ..registry import RoadRegistry, RoadSegment, checksum
from ..validation import parse_utc

RECIPE_VERSION = "demo-network-1"


def load_demo_registry():
    """Fingerprint network contents and ID assignments, independent of input list order."""
    version = "hanoi-demo-" + checksum(sorted(ROADS, key=lambda r: r["id"]))[:16]
    return RoadRegistry(
        version,
        [
            RoadSegment(
                road_id=r["id"],
                network_version=version,
                source_type="demo",
                source_id="core/network.py#" + r["id"],
                name=r["name"],
                coordinates=tuple(tuple(c) for c in r["coordinates"]),
                endpoint_a=r["a"],
                endpoint_b=r["b"],
                length_km=r["length_km"],
                directionality="both",
            )
            for r in ROADS
        ],
    )


def generate_demo_observations(registry, *, dataset_version, timestamp, as_of):
    """One synthetic dry-bin record per road; missing NASA/DEM/history stays None.

    Speed is held at 80% of the demo free speed for this synthetic bin. It is not
    a measured bin average or the current app snapshot. Unknown demo roads stay unknown.
    """
    end = parse_utc(timestamp)
    valid_until = (end + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = {r["id"]: r for r in ROADS}
    observations, catalog = [], {}
    for segment in registry:
        original = rows[segment.road_id]
        lat, lon = segment.representative_point()
        values = dict.fromkeys(FEATURE_FIELDS)
        values.update(latitude=lat, longitude=lon, free_flow_speed=original["free_speed"])
        if original["seed_event"] != "unknown":
            values.update(
                traffic_speed=round(original["free_speed"] * 0.8, 1),
                current_flood_depth=0.0,
                flood_status=False,
            )
        flags = []
        for field in SOURCE_FIELDS:
            if values[field] is not None:
                reason, detail = (
                    QualityReason.DEMO_VALUE,
                    "Synthetic network demo, not NASA/OSM or measured traffic.",
                )
            else:
                reason = (
                    QualityReason.MISSING_GPM
                    if field.startswith("rainfall_")
                    else QualityReason.MISSING_SMAP
                    if field == "soil_moisture"
                    else QualityReason.MISSING_TRAFFIC
                    if field == "traffic_speed"
                    else QualityReason.MISSING_FEATURE
                )
                detail = "Source not collected in Data-02; value remains null."
            flags.append(QualityFlag.for_reason(field, reason, detail))
        sources = []
        for kind in ("static", "dynamic"):
            names = tuple(
                f
                for f in SOURCE_FIELDS
                if values[f] is not None and ((f in STATIC_FIELDS) == (kind == "static"))
            )
            if not names:
                continue
            raw_input = {
                "road_id": segment.road_id,
                "registry_checksum": registry.checksum,
                "recipe": RECIPE_VERSION,
                "timestamp": timestamp,
                "values": {f: values[f] for f in names},
            }
            digest = checksum(raw_input)
            reference = "demo:sha256:" + digest
            src = SourceMetadata(
                names,
                "demo",
                "hand-authored-hanoi-network",
                RECIPE_VERSION,
                reference,
                timestamp,
                timestamp,
                None if kind == "static" else valid_until,
                "simulated",
            )
            catalog[reference] = dict(
                asdict(src),
                fields=list(names),
                checksum=digest,
                input=raw_input,
                retrieved_at=timestamp,
                license="MIT",
                source_path="backend/vietsafe/core/network.py",
            )
            sources.append(src)
        observations.append(
            RoadObservation(
                schema_version=SCHEMA_VERSION,
                dataset_version=dataset_version,
                network_version=registry.network_version,
                road_id=segment.road_id,
                timestamp=timestamp,
                as_of=as_of,
                data_mode="demo",
                **values,
                source=tuple(sources),
                quality_score=0.0,
                quality_flags=tuple(flags),
            )
        )
    return tuple(observations), dict(sorted(catalog.items()))
