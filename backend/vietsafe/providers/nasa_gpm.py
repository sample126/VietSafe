"""NASA GPM IMERG Early Run rainfall retrieval and regional grid extraction."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
import json
import math
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
    urlopen,
)

try:
    import h5py
    import numpy as np
except ImportError:
    h5py = None
    np = None


CMR_URL = 'https://cmr.earthdata.nasa.gov/search/granules.json'
CMR_SHORT_NAME = 'GPM_3IMERGHHE'
CMR_VERSION = '07'
COLLECTION_ID = 'C2723758340-GES_DISC'
MAP_BOUNDS = {'south': 20.75, 'west': 105.50, 'north': 21.40, 'east': 106.40}
CACHE_SECONDS = 30 * 60
MAX_GRANULE_BYTES = 100 * 1024 * 1024

_cache_lock = threading.Lock()
_cached_grid = None
_cached_at = 0.0


class GpmUnavailable(RuntimeError):
    """An actionable NASA data access or processing error."""


class _EarthdataRedirectHandler(HTTPRedirectHandler):
    def __init__(self, token):
        super().__init__()
        self.token = token

    def http_request(self, request):
        if _is_earthdata_host(request.full_url):
            request.add_unredirected_header('Authorization', f'Bearer {self.token}')
        return request

    https_request = http_request


def _is_earthdata_host(url):
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ''
    return host == 'earthdata.nasa.gov' or host.endswith('.earthdata.nasa.gov')


def _earthdata_opener(token):
    return build_opener(_EarthdataRedirectHandler(token))


def _open_url(request, token=None, timeout=30):
    try:
        if token:
            return _earthdata_opener(token).open(request, timeout=timeout)
        return urlopen(request, timeout=timeout)
    except HTTPError as error:
        if error.code in (401, 403):
            raise GpmUnavailable(
                'NASA GES DISC từ chối truy cập. Kiểm tra NASA_EARTHDATA_TOKEN '
                'và quyền truy cập dữ liệu GPM trên Earthdata Login.'
            ) from error
        raise GpmUnavailable(f'NASA GPM trả về HTTP {error.code}.') from error
    except (URLError, TimeoutError) as error:
        raise GpmUnavailable(f'Không kết nối được dịch vụ NASA GPM: {error}.') from error


def _latest_granule(token):
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=36)
    query = urlencode({
        'short_name': CMR_SHORT_NAME,
        'version': CMR_VERSION,
        'temporal': f'{start:%Y-%m-%dT%H:%M:%SZ},{now:%Y-%m-%dT%H:%M:%SZ}',
        'page_size': 5,
        'sort_key': '-start_date',
    })
    request = Request(
        f'{CMR_URL}?{query}',
        headers={'Accept': 'application/json', 'User-Agent': 'VietSafe/1.0'},
    )
    with _open_url(request, timeout=30) as response:
        metadata = json.loads(response.read().decode('utf-8'))
    entries = metadata.get('feed', {}).get('entry', [])
    for entry in entries:
        links = entry.get('links', [])
        data_link = next((
            link.get('href') for link in links
            if link.get('rel') == 'http://esipfed.org/ns/fedsearch/1.1/data#'
            and link.get('href', '').startswith('https://data.gesdisc.earthdata.nasa.gov/')
        ), None)
        if data_link and entry.get('time_start'):
            return data_link, entry
    raise GpmUnavailable(
        'CMR chưa liệt kê granule IMERG Early Run trong 36 giờ gần nhất. '
        'Thử tải lại sau; không thay bằng mưa mô phỏng.'
    )


def _download_granule(url, token):
    request = Request(
        url,
        headers={
            'Accept': 'application/octet-stream',
            'User-Agent': 'VietSafe/1.0',
        },
    )
    with _open_url(request, token=token, timeout=90) as response:
        payload = response.read(MAX_GRANULE_BYTES + 1)
    if len(payload) > MAX_GRANULE_BYTES:
        raise GpmUnavailable('Granule NASA GPM vượt giới hạn tải 100 MB.')
    if not payload:
        raise GpmUnavailable('NASA GPM trả về granule rỗng.')
    return payload


def _read_grid(payload, entry):
    if h5py is None or np is None:
        raise GpmUnavailable(
            'Thiếu thư viện đọc HDF5. Cài dependencies bằng: pip install -r requirements-optional.txt.'
        )
    try:
        with h5py.File(BytesIO(payload), 'r') as granule:
            latitudes = np.asarray(granule['Grid/lat'][:], dtype=float).reshape(-1)
            longitudes = np.asarray(granule['Grid/lon'][:], dtype=float).reshape(-1)
            precipitation = granule['Grid/precipitation']
            values = np.asarray(precipitation[:], dtype=float).squeeze()
            units = precipitation.attrs.get('units', 'mm/hr')
            if isinstance(units, bytes):
                units = units.decode('ascii', errors='replace')
            fill_value = precipitation.attrs.get('_FillValue')
            if fill_value is not None:
                fill_value = float(np.asarray(fill_value).reshape(-1)[0])

        if values.shape == (len(longitudes), len(latitudes)) and values.shape != (len(latitudes), len(longitudes)):
            values = values.T
        elif values.shape != (len(latitudes), len(longitudes)):
            raise GpmUnavailable(
                f'Kích thước lưới IMERG không khớp trục lat/lon: {values.shape}.'
            )
        if len(latitudes) < 2 or len(longitudes) < 2:
            raise GpmUnavailable('Granule IMERG thiếu trục tọa độ lat/lon.')

        lat_step = float(np.median(np.abs(np.diff(latitudes))))
        lon_step = float(np.median(np.abs(np.diff(longitudes))))
        bounds = MAP_BOUNDS
        lat_indices = np.flatnonzero(
            (latitudes >= bounds['south'] - lat_step / 2)
            & (latitudes <= bounds['north'] + lat_step / 2)
        )
        lon_indices = np.flatnonzero(
            (longitudes >= bounds['west'] - lon_step / 2)
            & (longitudes <= bounds['east'] + lon_step / 2)
        )
        cells = []
        for row in lat_indices:
            for column in lon_indices:
                value = float(values[row, column])
                if not math.isfinite(value) or (fill_value is not None and value == fill_value) or value < 0:
                    rainfall = None
                else:
                    rainfall = round(value, 3)
                lat = float(latitudes[row])
                lon = float(longitudes[column])
                cells.append({
                    'lat': round(lat, 4),
                    'lng': round(lon, 4),
                    'south': round(lat - lat_step / 2, 4),
                    'north': round(lat + lat_step / 2, 4),
                    'west': round(lon - lon_step / 2, 4),
                    'east': round(lon + lon_step / 2, 4),
                    'rainfall_mm_hr': rainfall,
                })
        if not cells:
            raise GpmUnavailable('Granule IMERG không có ô dữ liệu trong vùng bản đồ.')
        return {
            'product': 'GPM IMERG Early Run V07 (GPM_3IMERGHHE)',
            'variable': 'Grid/precipitation',
            'units': str(units),
            'resolution_degrees': round(max(lat_step, lon_step), 4),
            'resolution_km_approx': round(lat_step * 111.0, 1),
            'time_start': entry['time_start'],
            'time_end': entry.get('time_end'),
            'granule': entry.get('title'),
            'source_url': 'https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGHHE_07/summary',
            'attribution': 'NASA GPM IMERG; NASA GES DISC',
            'bounds': bounds,
            'cells': cells,
            'fetched_at': datetime.now(timezone.utc).isoformat(),
        }
    except GpmUnavailable:
        raise
    except (KeyError, OSError, ValueError, TypeError) as error:
        raise GpmUnavailable(f'Không thể đọc lưới mưa của granule NASA GPM: {error}.') from error


def get_latest_rainfall(force=False):
    """Return a cached regional IMERG grid, refreshing at most every 30 minutes."""
    global _cached_grid, _cached_at
    token = os.environ.get('NASA_EARTHDATA_TOKEN', '').strip()
    if not token:
        raise GpmUnavailable(
            'Thiếu NASA_EARTHDATA_TOKEN. Tạo token trong NASA Earthdata Login, '
            'đặt biến môi trường cho máy chủ VietSafe rồi khởi động lại.'
        )
    if h5py is None or np is None:
        raise GpmUnavailable('Thiếu h5py/numpy để đọc HDF5 NASA. Cài: pip install -r requirements-optional.txt')
    with _cache_lock:
        if _cached_grid and not force and time.time() - _cached_at < CACHE_SECONDS:
            return _cached_grid
        try:
            url, entry = _latest_granule(token)
            payload = _download_granule(url, token)
            grid = _read_grid(payload, entry)
        except GpmUnavailable:
            if _cached_grid and time.time() - _cached_at < 2 * 60 * 60:
                stale = dict(_cached_grid)
                stale['stale'] = True
                stale['warning'] = 'Không lấy được bản GPM mới; đang dùng granule đã lưu trong bộ nhớ.'
                return stale
            raise
        _cached_grid = grid
        _cached_at = time.time()
        return grid


def _reset_cache_for_tests():
    global _cached_grid, _cached_at
    with _cache_lock:
        _cached_grid = None
        _cached_at = 0.0
