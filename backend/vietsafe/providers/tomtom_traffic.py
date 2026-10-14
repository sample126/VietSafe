"""TomTom traffic-flow tiles and clicked-road lookups."""
from collections import OrderedDict
from datetime import datetime, timezone
import json
import math
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


FLOW_TILES_URL = 'https://api.tomtom.com/traffic/map/4/tile/flow/relative'
FLOW_SEGMENT_URL = 'https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute'
REVERSE_GEOCODE_URL = 'https://api.tomtom.com/search/2/reverseGeocode'
NOMINATIM_REVERSE_URL = 'https://nominatim.openstreetmap.org/reverse'
MAX_TILE_BYTES = 2 * 1024 * 1024
MAX_SEGMENT_BYTES = 1024 * 1024
TILE_CACHE_SECONDS = 180
SEGMENT_CACHE_SECONDS = 300
MAX_CACHED_TILES = 256
MAX_CACHED_SEGMENTS = 256
_cache_lock = threading.Lock()
_tile_cache = OrderedDict()
_segment_cache = OrderedDict()
_road_name_cache = OrderedDict()
_osm_road_name_cache = OrderedDict()
_nominatim_rate_lock = threading.Lock()
_nominatim_last_request = 0.0


class TomTomUnavailable(RuntimeError):
    """An actionable TomTom traffic API or processing error."""


class TomTomPermissionDenied(TomTomUnavailable):
    """The configured TomTom key is not authorized for the requested API."""


class RoadNameUnavailable(RuntimeError):
    """An actionable OpenStreetMap reverse-geocoding error."""


def _api_key():
    api_key = os.environ.get('TOMTOM_API_KEY', '').strip()
    if not api_key:
        raise TomTomUnavailable(
            'Thiếu TOMTOM_API_KEY. Đặt biến môi trường cho máy chủ VietSafe rồi khởi động lại.'
        )
    return api_key


def _read_tomtom(url, limit, timeout=12):
    request = Request(
        url,
        headers={'Accept': 'application/json, image/png', 'User-Agent': 'VietSafe/1.0'},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(limit + 1)
            content_type = response.headers.get_content_type()
    except HTTPError as error:
        if error.code in (401, 403):
            raise TomTomPermissionDenied(
                'TomTom từ chối API key. Kiểm tra quyền API cần thiết của key.'
            ) from error
        if error.code == 429:
            raise TomTomUnavailable(
                'TomTom đã giới hạn lưu lượng API. Kiểm tra hạn mức gói dịch vụ.'
            ) from error
        raise TomTomUnavailable(f'TomTom API trả về HTTP {error.code}.') from error
    except (URLError, TimeoutError) as error:
        raise TomTomUnavailable(f'Không kết nối được TomTom API: {error}.') from error
    if len(payload) > limit:
        raise TomTomUnavailable('Phản hồi TomTom vượt giới hạn dung lượng.')
    return payload, content_type


def _cache_get(cache, key, max_age):
    with _cache_lock:
        entry = cache.get(key)
        if not entry:
            return None
        created_at, value = entry
        if time.monotonic() - created_at >= max_age:
            del cache[key]
            return None
        cache.move_to_end(key)
        return value


def _cache_set(cache, key, value, max_entries):
    with _cache_lock:
        cache[key] = (time.monotonic(), value)
        cache.move_to_end(key)
        while len(cache) > max_entries:
            cache.popitem(last=False)


def get_flow_tile(zoom, x, y):
    """Return a TomTom raster flow tile for a validated Web Mercator tile coordinate."""
    if type(zoom) is not int or type(x) is not int or type(y) is not int:
        raise TomTomUnavailable('Tọa độ ô bản đồ TomTom không hợp lệ.')
    if not 0 <= zoom <= 22:
        raise TomTomUnavailable('Mức phóng đại ô TomTom phải nằm trong khoảng 0–22.')
    tile_count = 1 << zoom
    if not 0 <= x < tile_count or not 0 <= y < tile_count:
        raise TomTomUnavailable('Tọa độ ô bản đồ TomTom nằm ngoài phạm vi.')
    api_key = _api_key()
    cache_key = (zoom, x, y)
    cached = _cache_get(_tile_cache, cache_key, TILE_CACHE_SECONDS)
    if cached is not None:
        return cached

    url = f'{FLOW_TILES_URL}/{zoom}/{x}/{y}.png?{urlencode({"key": api_key, "thickness": 8})}'
    payload, content_type = _read_tomtom(url, MAX_TILE_BYTES, timeout=15)
    if content_type != 'image/png' or not payload.startswith(b'\x89PNG\r\n\x1a\n'):
        raise TomTomUnavailable('TomTom trả về ô giao thông không phải ảnh PNG hợp lệ.')
    _cache_set(_tile_cache, cache_key, payload, MAX_CACHED_TILES)
    return payload


def _parse_flow_segment(payload):
    segment = payload.get('flowSegmentData', payload)
    if not isinstance(segment, dict):
        raise TomTomUnavailable('TomTom trả về dữ liệu đoạn đường không hợp lệ.')
    try:
        current_speed = float(segment['currentSpeed'])
        free_flow_speed = float(segment['freeFlowSpeed'])
        confidence = float(segment['confidence'])
        current_travel_time = int(segment['currentTravelTime'])
        free_flow_travel_time = int(segment['freeFlowTravelTime'])
    except (KeyError, TypeError, ValueError) as error:
        raise TomTomUnavailable('TomTom không trả đủ thông tin tốc độ của đoạn đường.') from error
    if (
        not math.isfinite(current_speed)
        or not math.isfinite(free_flow_speed)
        or not math.isfinite(confidence)
        or current_speed < 0
        or free_flow_speed < 0
        or not 0 <= confidence <= 1
    ):
        raise TomTomUnavailable('TomTom trả về giá trị tốc độ hoặc độ tin cậy không hợp lệ.')

    coordinates = segment.get('coordinates', {}).get('coordinate', [])
    if isinstance(coordinates, dict):
        coordinates = [coordinates]
    geometry = []
    if isinstance(coordinates, list):
        for coordinate in coordinates[:5000]:
            try:
                lat = float(coordinate['latitude'])
                lng = float(coordinate['longitude'])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(lat) and math.isfinite(lng) and -90 <= lat <= 90 and -180 <= lng <= 180:
                geometry.append([lat, lng])

    road_closure = segment.get('roadClosure', False)
    if not isinstance(road_closure, bool):
        road_closure = str(road_closure).lower() == 'true'
    return {
        'current_speed_kmh': round(current_speed, 1),
        'free_flow_speed_kmh': round(free_flow_speed, 1),
        'current_travel_time_seconds': current_travel_time,
        'free_flow_travel_time_seconds': free_flow_travel_time,
        'speed_ratio': round(current_speed / free_flow_speed, 3) if free_flow_speed else 0,
        'confidence': round(confidence, 3),
        'road_closure': road_closure,
        'road_class': str(segment.get('frc', '')),
        'coordinates': geometry,
    }


def get_flow_segment(latitude, longitude, zoom=15):
    """Look up the current TomTom flow segment nearest a user-selected coordinate."""
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise TomTomUnavailable('Tọa độ vị trí phải là số.')
    if (
        not math.isfinite(latitude) or not math.isfinite(longitude)
        or not 20.75 <= latitude <= 21.40 or not 105.50 <= longitude <= 106.40
    ):
        raise TomTomUnavailable('Vị trí được chọn nằm ngoài vùng bản đồ Hà Nội–Bắc Ninh.')
    if type(zoom) is not int or not 0 <= zoom <= 22:
        raise TomTomUnavailable('Mức phóng đại bản đồ không hợp lệ.')

    api_key = _api_key()
    cache_key = (round(latitude, 4), round(longitude, 4), zoom)
    cached = _cache_get(_segment_cache, cache_key, SEGMENT_CACHE_SECONDS)
    if cached is not None:
        return cached

    params = urlencode({
        'key': api_key,
        'point': f'{latitude:.6f},{longitude:.6f}',
        'unit': 'kmph',
    })
    url = f'{FLOW_SEGMENT_URL}/{zoom}/json?{params}'
    payload, content_type = _read_tomtom(url, MAX_SEGMENT_BYTES)
    if content_type != 'application/json':
        raise TomTomUnavailable('TomTom trả về định dạng không phải JSON.')
    try:
        result = _parse_flow_segment(json.loads(payload.decode('utf-8')))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TomTomUnavailable('TomTom trả về dữ liệu JSON không đọc được.') from error
    if not result['coordinates']:
        raise TomTomUnavailable('TomTom không trả hình học cho đoạn đường ở vị trí này.')

    result.update({
        'provider': 'TomTom Traffic Flow Segment Data API v4',
        'sampled_at': datetime.now(timezone.utc).isoformat(),
        'query_point': {'latitude': latitude, 'longitude': longitude},
    })
    _cache_set(_segment_cache, cache_key, result, MAX_CACHED_SEGMENTS)
    return result


def get_road_name(latitude, longitude):
    """Return the TomTom street name nearest a validated map coordinate."""
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise TomTomUnavailable('Tọa độ tra cứu tên đường phải là số.')
    if (
        not math.isfinite(latitude) or not math.isfinite(longitude)
        or not 20.75 <= latitude <= 21.40 or not 105.50 <= longitude <= 106.40
    ):
        raise TomTomUnavailable('Vị trí được chọn nằm ngoài vùng bản đồ Hà Nội–Bắc Ninh.')

    cache_key = (round(latitude, 4), round(longitude, 4))
    cached = _cache_get(_road_name_cache, cache_key, SEGMENT_CACHE_SECONDS)
    if cached is not None:
        return cached

    params = urlencode({
        'key': _api_key(),
        'language': 'vi-VN',
        'radius': 50,
    })
    url = f'{REVERSE_GEOCODE_URL}/{latitude:.6f},{longitude:.6f}.json?{params}'
    payload, content_type = _read_tomtom(url, MAX_SEGMENT_BYTES)
    if content_type != 'application/json':
        raise TomTomUnavailable('TomTom trả về định dạng tra cứu tên đường không phải JSON.')
    try:
        data = json.loads(payload.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TomTomUnavailable('TomTom trả về dữ liệu tên đường không đọc được.') from error
    if not isinstance(data, dict):
        raise TomTomUnavailable('TomTom trả về dữ liệu tên đường không hợp lệ.')
    addresses = data.get('addresses', [])
    street_name = None
    if isinstance(addresses, list):
        for item in addresses:
            address = item.get('address') if isinstance(item, dict) else None
            if isinstance(address, dict) and isinstance(address.get('streetName'), str):
                street_name = address['streetName'].strip() or None
                if street_name:
                    break
    _cache_set(_road_name_cache, cache_key, street_name, MAX_CACHED_SEGMENTS)
    return street_name


def get_osm_road_name(latitude, longitude):
    """Return a road name from Nominatim, respecting its one-request-per-second policy."""
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise RoadNameUnavailable('Tọa độ tra cứu tên đường phải là số.')
    if (
        not math.isfinite(latitude) or not math.isfinite(longitude)
        or not 20.75 <= latitude <= 21.40 or not 105.50 <= longitude <= 106.40
    ):
        raise RoadNameUnavailable('Vị trí được chọn nằm ngoài vùng bản đồ Hà Nội–Bắc Ninh.')

    cache_key = (round(latitude, 4), round(longitude, 4))
    cached = _cache_get(_osm_road_name_cache, cache_key, SEGMENT_CACHE_SECONDS)
    if cached is not None:
        return cached

    global _nominatim_last_request
    with _nominatim_rate_lock:
        wait_seconds = 1.0 - (time.monotonic() - _nominatim_last_request)
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        _nominatim_last_request = time.monotonic()

    params = urlencode({
        'lat': f'{latitude:.6f}',
        'lon': f'{longitude:.6f}',
        'format': 'jsonv2',
        'addressdetails': 1,
        'zoom': 18,
        'accept-language': 'vi',
    })
    request = Request(
        f'{NOMINATIM_REVERSE_URL}?{params}',
        headers={'Accept': 'application/json', 'User-Agent': 'VietSafe/1.0 (local traffic map)'},
    )
    try:
        with urlopen(request, timeout=12) as response:
            payload = response.read(MAX_SEGMENT_BYTES + 1)
            content_type = response.headers.get_content_type()
    except HTTPError as error:
        raise RoadNameUnavailable(
            f'OpenStreetMap Nominatim trả về HTTP {error.code}.'
        ) from error
    except (URLError, TimeoutError) as error:
        raise RoadNameUnavailable(
            f'Không kết nối được OpenStreetMap Nominatim: {error}.'
        ) from error
    if len(payload) > MAX_SEGMENT_BYTES:
        raise RoadNameUnavailable('Phản hồi OpenStreetMap Nominatim vượt giới hạn dung lượng.')
    if content_type != 'application/json':
        raise RoadNameUnavailable('OpenStreetMap Nominatim trả về dữ liệu không phải JSON.')
    try:
        data = json.loads(payload.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RoadNameUnavailable('OpenStreetMap Nominatim trả về JSON không đọc được.') from error
    if not isinstance(data, dict):
        raise RoadNameUnavailable('OpenStreetMap Nominatim trả về dữ liệu không hợp lệ.')

    address = data.get('address')
    street_name = None
    if isinstance(address, dict):
        for key in (
            'road', 'pedestrian', 'residential', 'footway', 'path',
            'living_street', 'service', 'tertiary', 'secondary', 'primary',
            'trunk', 'motorway', 'unclassified',
        ):
            value = address.get(key)
            if isinstance(value, str) and value.strip():
                street_name = value.strip()
                break
    if street_name:
        _cache_set(_osm_road_name_cache, cache_key, street_name, MAX_CACHED_SEGMENTS)
    return street_name


def _reset_cache_for_tests():
    global _nominatim_last_request
    with _cache_lock:
        _tile_cache.clear()
        _segment_cache.clear()
        _road_name_cache.clear()
        _osm_road_name_cache.clear()
    with _nominatim_rate_lock:
        _nominatim_last_request = 0.0
