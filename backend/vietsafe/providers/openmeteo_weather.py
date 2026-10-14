"""Open-Meteo forecast adapter. These are model forecasts, never measured flood depth."""
import json
import math
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

_CACHE = {}
_LOCK = threading.Lock()

class WeatherUnavailable(RuntimeError):
    pass


def get_rain_forecast(latitude, longitude, hours=24):
    if not (math.isfinite(latitude) and math.isfinite(longitude) and -90 <= latitude <= 90 and -180 <= longitude <= 180):
        raise ValueError('Tọa độ không hợp lệ.')
    if not isinstance(hours, int) or not 1 <= hours <= 48:
        raise ValueError('Số giờ phải từ 1 đến 48.')
    key = (round(latitude, 3), round(longitude, 3))
    current_hour = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).strftime('%Y-%m-%dT%H:00')
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < 900:
            upcoming = [row for row in hit[1]['hours'] if row['time'] >= current_hour]
            if len(upcoming) >= hours:
                return {**hit[1], 'hours': upcoming[:hours], 'hours_requested':hours}
    params = {
        'latitude': latitude, 'longitude': longitude,
        'hourly': 'precipitation,rain,precipitation_probability',
        'forecast_days': 3, 'timezone': 'Asia/Ho_Chi_Minh',
    }
    url = 'https://api.open-meteo.com/v1/forecast?' + urlencode(params)
    try:
        with urlopen(Request(url, headers={'User-Agent':'VietSafe/1.1'}), timeout=12) as response:
            if int(response.headers.get('Content-Length', '0')) > 1_000_000:
                raise WeatherUnavailable('Phản hồi thời tiết quá lớn.')
            raw = response.read(1_000_001)
            if len(raw) > 1_000_000:
                raise WeatherUnavailable('Phản hồi thời tiết quá lớn.')
            data = json.loads(raw)
        hourly = data['hourly']
        times = hourly['time']
        rows = []
        for i, stamp in enumerate(times):
            rows.append({'time': stamp, 'precipitation_mm': hourly['precipitation'][i],
                         'rain_mm': hourly['rain'][i],
                         'probability_percent': hourly['precipitation_probability'][i]})
        result = {'source':'Open-Meteo', 'kind':'weather_forecast_not_flood_observation',
                  'latitude':latitude, 'longitude':longitude,
                  'retrieved_at':time.time(), 'units':{'precipitation':'mm', 'probability':'%'},
                  'hours':rows}
    except (HTTPError, URLError, TimeoutError, KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError) as exc:
        if isinstance(exc, HTTPError):
            reason = f'HTTP {exc.code} từ Open-Meteo'
        elif isinstance(exc, (URLError, TimeoutError)):
            reason = 'Không kết nối được Open-Meteo; kiểm tra Internet, DNS hoặc proxy của máy chạy Python'
        else:
            reason = 'Dữ liệu Open-Meteo không hợp lệ hoặc thiếu trường dự báo'
        raise WeatherUnavailable(reason) from exc
    with _LOCK:
        _CACHE[key] = (time.time(), result)
    upcoming = [row for row in rows if row['time'] >= current_hour]
    return {**result, 'hours': upcoming[:hours], 'hours_requested':hours}
