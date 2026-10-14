import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2] / 'backend'))
from vietsafe import auth, config, db, reports, service
from vietsafe.core.engine import build_snapshot, calculate_routes
from vietsafe.core.network import NODES, ROADS, nearest_road, road_midpoint
from vietsafe.web.server import Handler, ThreadingHTTPServer
from vietsafe.providers import tomtom_traffic, nasa_gpm, openmeteo_weather

from io import BytesIO
from pathlib import Path
import sys
import unittest

try:
    import h5py
    import numpy as np
except ImportError:
    h5py = None
    np = None



@unittest.skipUnless(h5py is not None and np is not None, "Requires optional HDF5 packages")
class GpmGridTests(unittest.TestCase):
    def make_granule(self, precipitation, latitudes, longitudes):
        payload = BytesIO()
        with h5py.File(payload, 'w') as granule:
            grid = granule.create_group('Grid')
            grid.create_dataset('lat', data=latitudes)
            grid.create_dataset('lon', data=longitudes)
            rainfall = grid.create_dataset('precipitation', data=precipitation)
            rainfall.attrs['units'] = 'mm/hr'
            rainfall.attrs['_FillValue'] = -9999.9
        return payload.getvalue()

    def test_extracts_regional_imerg_cells_and_preserves_missing_values(self):
        payload = self.make_granule(
            np.array([[[1.25, 2.5], [3.75, -9999.9], [5.0, 6.0]]]),
            [21.0, 21.1, 21.2],
            [105.8, 105.9],
        )
        result = nasa_gpm._read_grid(payload, {
            'time_start': '2026-10-08T03:30:00.000Z',
            'time_end': '2026-10-08T03:59:59.000Z',
            'title': 'IMERG test granule',
        })
        self.assertEqual(result['product'], 'GPM IMERG Early Run V07 (GPM_3IMERGHHE)')
        self.assertEqual(result['units'], 'mm/hr')
        self.assertEqual(len(result['cells']), 6)
        cell = next(cell for cell in result['cells'] if cell['lat'] == 21.1 and cell['lng'] == 105.8)
        self.assertEqual(cell['rainfall_mm_hr'], 3.75)
        missing = next(cell for cell in result['cells'] if cell['lat'] == 21.1 and cell['lng'] == 105.9)
        self.assertIsNone(missing['rainfall_mm_hr'])

    def test_accepts_transposed_hdf_grid_and_single_time_dimension(self):
        payload = self.make_granule(
            np.array([[11.0, 12.0, 13.0], [21.0, 22.0, 23.0]]),
            [21.0, 21.1, 21.2],
            [105.8, 105.9],
        )
        result = nasa_gpm._read_grid(payload, {
            'time_start': '2026-10-08T03:30:00.000Z',
            'title': 'IMERG transposed test granule',
        })
        self.assertEqual(
            next(cell for cell in result['cells'] if cell['lat'] == 21.2 and cell['lng'] == 105.9)['rainfall_mm_hr'],
            23.0,
        )

    def test_missing_nasa_token_returns_actionable_error(self):
        previous = nasa_gpm.os.environ.pop('NASA_EARTHDATA_TOKEN', None)
        try:
            with self.assertRaisesRegex(nasa_gpm.GpmUnavailable, 'NASA_EARTHDATA_TOKEN'):
                nasa_gpm.get_latest_rainfall(force=True)
        finally:
            if previous is not None:
                nasa_gpm.os.environ['NASA_EARTHDATA_TOKEN'] = previous

    def test_earthdata_token_is_sent_only_to_nasa_hosts(self):
        earthdata_request = nasa_gpm.Request('https://data.gesdisc.earthdata.nasa.gov/file.h5')
        nasa_gpm._EarthdataRedirectHandler('test-token').http_request(earthdata_request)
        self.assertEqual(earthdata_request.get_header('Authorization'), 'Bearer test-token')

        other_request = nasa_gpm.Request('https://example.org/file.h5')
        nasa_gpm._EarthdataRedirectHandler('test-token').http_request(other_request)
        self.assertIsNone(other_request.get_header('Authorization'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
