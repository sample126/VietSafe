"""Standard-library SRTM HGT point-sample reader; no download or road sampling."""

import argparse
import hashlib
import math
import re
import struct
from pathlib import Path

from ..environment import EnvironmentalGrid, EnvironmentInputError, PROCESSING_VERSION, require
from .environment_json import emit

MAX_HGT_BYTES = 3601 * 3601 * 2


def tile_coordinates(name):
    """Southwest tile coordinate from an exact HGT basename."""
    require(isinstance(name, str), "Expected HGT tile name")
    match = re.fullmatch(r"([NS])(\d{2})([EW])(\d{3})\.hgt", name)
    require(match is not None, "Expected tile name such as N21E105.hgt")
    north, lat, east, lon = match.groups()
    lat, lon = int(lat) * (1 if north == "N" else -1), int(lon) * (1 if east == "E" else -1)
    require(-90 <= lat < 90 and -180 <= lon < 180, "Tile extent outside WGS84")
    return lat, lon


def read_hgt(path, *, product_version, source_uri, fixture_tile=None,
             observed_at=None, available_at=None):
    """Read uncompressed big-endian int16 HGT. Mini grids require explicit fixture_tile.

    Production supports SRTM1 (3601) and SRTM3 (1201) square tiles only.
    HGT samples include shared degree boundaries, not half-cell-offset centers.
    """
    path = Path(path)
    require(fixture_tile is None or isinstance(fixture_tile, str), "Invalid fixture tile")
    south, west = tile_coordinates(fixture_tile if fixture_tile is not None else path.name)
    with path.open("rb") as stream:
        raw = stream.read(MAX_HGT_BYTES + 1)
    require(0 < len(raw) <= MAX_HGT_BYTES and len(raw) % 2 == 0, "Invalid HGT byte count")
    size = math.isqrt(len(raw) // 2)
    require(size >= 2 and size * size * 2 == len(raw), "HGT must be a square sample raster")
    if fixture_tile is None:
        require(size in (1201, 3601), "Production HGT requires 1201 or 3601 samples per side")
    else:
        require(size <= 32, "Mini fixture must be at most 32 samples per side")
    values = iter(value[0] for value in struct.iter_unpack(">h", raw))
    rows = tuple(tuple(None if (value := next(values)) == -32768 else value
                       for _ in range(size)) for _ in range(size))
    metadata = {
        "processing_version": PROCESSING_VERSION, "original_variable": "elevation",
        "original_units": "m", "crs": "EPSG:4326", "grid_registration": "point",
        "temporal_semantics": "static", "original_nodata": -32768,
        "reference": fixture_tile if fixture_tile is not None else path.name,
        "vertical_datum": "EGM96" if fixture_tile is None else "not_applicable_synthetic",
        "is_test_fixture": fixture_tile is not None,
    }
    if fixture_tile is not None:
        metadata["fixture_notice"] = "TEST FIXTURE — NOT A REAL SRTM TILE"
    return EnvironmentalGrid(
        source_type="dem", product="SRTM-HGT" if fixture_tile is None else "SYNTHETIC-HGT",
        product_version=product_version, variable="elevation", units="m", rows=size, cols=size,
        origin_lat=south + 1, origin_lon=west, lat_step=-1 / (size - 1), lon_step=1 / (size - 1),
        values=rows, nodata=None, observed_at=observed_at, available_at=available_at,
        source_uri=source_uri, raw_checksum=hashlib.sha256(raw).hexdigest(), metadata=metadata,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline SRTM/HGT reader; no download")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", help="New output file; never overwrite")
    parser.add_argument("--product-version", required=True, help="Version from source metadata")
    parser.add_argument("--source-uri", required=True, help="Stable source URI/reference")
    parser.add_argument("--fixture-tile", help="Explicit mini TEST FIXTURE tile, e.g. N21E105.hgt")
    parser.add_argument("--observed-at")
    parser.add_argument("--available-at")
    args = parser.parse_args(argv)
    try:
        emit(read_hgt(args.input, product_version=args.product_version, source_uri=args.source_uri,
                      fixture_tile=args.fixture_tile, observed_at=args.observed_at,
                      available_at=args.available_at), args.output)
    except (EnvironmentInputError, OSError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
