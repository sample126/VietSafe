"""Representative point to nearest center in grid coordinate space, offline only."""

from fractions import Fraction

from ..alignment import AlignmentInputError, RoadGridSample
from ..registry import finite_number


def nearest_cell(grid, latitude, longitude):
    """Inclusive half-cell coverage; ties choose smaller row/col (north/west).

    Decimal representations are compared as exact rationals: no banker's rounding,
    epsilon-dependent tie or accidental negative index. Not geodesic interpolation.
    """
    if grid.metadata.get('crs') != 'EPSG:4326':
        raise AlignmentInputError('UNSUPPORTED_CRS', 'Only EPSG:4326 is supported')
    if not (finite_number(latitude) and finite_number(longitude) and
            -90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise AlignmentInputError('INVALID_POINT', 'Expected finite WGS84 latitude/longitude')
    indexes = []
    for point, origin, step, count in (
        (latitude, grid.origin_lat, grid.lat_step, grid.rows),
        (longitude, grid.origin_lon, grid.lon_step, grid.cols),
    ):
        coordinate = (Fraction(str(point)) - Fraction(str(origin))) / Fraction(str(step))
        if coordinate < Fraction(-1, 2) or coordinate > count - Fraction(1, 2):
            raise AlignmentInputError('OUTSIDE_GRID', 'Point outside half-cell grid coverage')
        lower = coordinate.numerator // coordinate.denominator
        index = lower + (coordinate - lower > Fraction(1, 2))
        # Only an already-in-coverage outer boundary may resolve to an edge cell.
        indexes.append(min(count - 1, max(0, index)))
    return tuple(indexes)


def sample_road(road, grid, *, source_type=None, grid_checksum=None):
    lat, lon = road.representative_point()
    common = dict(road_id=road.road_id, network_version=road.network_version,
                  source_type=grid.source_type if grid is not None else source_type,
                  road_lat=lat, road_lon=lon, grid=grid)
    if grid is None:
        return RoadGridSample(**common, missing_reason='NO_SOURCE_GRID')
    digest = grid_checksum if grid_checksum is not None else grid.checksum()
    try:
        row, col = nearest_cell(grid, lat, lon)
    except AlignmentInputError as error:
        return RoadGridSample(**common, missing_reason=error.code, grid_checksum=digest)
    cell_lat, cell_lon = grid.cell_center(row, col)
    value = grid.values[row][col]
    return RoadGridSample(**common, grid_row=row, grid_col=col, cell_lat=cell_lat,
                          cell_lon=cell_lon, value=value, grid_checksum=digest,
                          missing_reason='GRID_NODATA' if value is None else None)


def align_spatial(registry, grid):
    digest = grid.checksum()
    return tuple(sample_road(road, grid, grid_checksum=digest)
                 for road in sorted(registry, key=lambda road: road.road_id))
