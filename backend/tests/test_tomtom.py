import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2] / 'backend'))
from vietsafe import auth, config, db, reports, service
from vietsafe.core.engine import build_snapshot, calculate_routes
from vietsafe.core.network import NODES, ROADS, nearest_road, road_midpoint
from vietsafe.web.server import Handler, ThreadingHTTPServer
from vietsafe.providers import tomtom_traffic, nasa_gpm, openmeteo_weather

from email.message import Message
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch



FLOW_RESPONSE = {
    'flowSegmentData': {
        'frc': 'FRC2',
        'currentSpeed': 18,
        'freeFlowSpeed': 45,
        'currentTravelTime': 120,
        'freeFlowTravelTime': 48,
        'confidence': 0.91,
        'roadClosure': False,
        'coordinates': {
            'coordinate': [
                {'latitude': 21.0, 'longitude': 105.8},
                {'latitude': 21.001, 'longitude': 105.801},
            ],
        },
    },
}


class MockResponse(BytesIO):
    def __init__(self, payload, content_type):
        super().__init__(payload)
        self.headers = Message()
        self.headers['Content-Type'] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class TomTomTrafficTests(unittest.TestCase):
    def setUp(self):
        tomtom_traffic._reset_cache_for_tests()
        self.previous_key = os.environ.get('TOMTOM_API_KEY')
        os.environ['TOMTOM_API_KEY'] = 'test-server-key'

    def tearDown(self):
        tomtom_traffic._reset_cache_for_tests()
        if self.previous_key is None:
            os.environ.pop('TOMTOM_API_KEY', None)
        else:
            os.environ['TOMTOM_API_KEY'] = self.previous_key

    def test_parses_current_and_free_flow_with_road_geometry(self):
        result = tomtom_traffic._parse_flow_segment(FLOW_RESPONSE)
        self.assertEqual(result['current_speed_kmh'], 18)
        self.assertEqual(result['free_flow_speed_kmh'], 45)
        self.assertEqual(result['speed_ratio'], 0.4)
        self.assertEqual(result['confidence'], 0.91)
        self.assertEqual(result['road_class'], 'FRC2')
        self.assertEqual(result['coordinates'], [[21.0, 105.8], [21.001, 105.801]])
        self.assertFalse(result['road_closure'])

    def test_fetches_flow_tile_server_side_and_caches_it(self):
        tile = b'\x89PNG\r\n\x1a\nmock-tomtom-tile'
        with patch.object(
            tomtom_traffic,
            'urlopen',
            return_value=MockResponse(tile, 'image/png'),
        ) as request:
            result = tomtom_traffic.get_flow_tile(15, 5241, 12661)
            cached = tomtom_traffic.get_flow_tile(15, 5241, 12661)

        self.assertEqual(result, tile)
        self.assertEqual(cached, tile)
        self.assertEqual(request.call_count, 1)
        url = request.call_args.args[0].full_url
        self.assertIn('/tile/flow/relative/15/5241/12661.png?', url)
        self.assertEqual(parse_qs(urlparse(url).query), {
            'key': ['test-server-key'],
            'thickness': ['8'],
        })

    def test_fetches_clicked_segment_and_caches_it(self):
        with patch.object(
            tomtom_traffic,
            'urlopen',
            return_value=MockResponse(json.dumps(FLOW_RESPONSE).encode(), 'application/json'),
        ) as request:
            result = tomtom_traffic.get_flow_segment(21.0, 105.8, 16)
            cached = tomtom_traffic.get_flow_segment(21.0, 105.8, 16)

        self.assertEqual(result, cached)
        self.assertEqual(request.call_count, 1)
        url = request.call_args.args[0].full_url
        query = parse_qs(urlparse(url).query)
        self.assertEqual(query['key'], ['test-server-key'])
        self.assertEqual(query['point'], ['21.000000,105.800000'])
        self.assertIn('/flowSegmentData/absolute/16/json?', url)
        self.assertEqual(result['coordinates'], [[21.0, 105.8], [21.001, 105.801]])
        self.assertNotIn('test-server-key', json.dumps(result))

    def test_reverse_geocodes_and_caches_road_name(self):
        response = {'addresses': [{'address': {'streetName': 'Hoàng Diệu'}}]}
        with patch.object(
            tomtom_traffic,
            'urlopen',
            return_value=MockResponse(json.dumps(response).encode(), 'application/json'),
        ) as request:
            name = tomtom_traffic.get_road_name(21.0, 105.8)
            cached = tomtom_traffic.get_road_name(21.0, 105.8)

        self.assertEqual(name, 'Hoàng Diệu')
        self.assertEqual(cached, name)
        self.assertEqual(request.call_count, 1)
        url = request.call_args.args[0].full_url
        self.assertIn('/search/2/reverseGeocode/21.000000,105.800000.json?', url)
        self.assertEqual(parse_qs(urlparse(url).query), {
            'key': ['test-server-key'],
            'language': ['vi-VN'],
            'radius': ['50'],
        })

    def test_reverse_geocode_returns_no_name_when_street_is_missing(self):
        response = {'addresses': [{'address': {'municipality': 'Hà Nội'}}]}
        with patch.object(
            tomtom_traffic,
            'urlopen',
            return_value=MockResponse(json.dumps(response).encode(), 'application/json'),
        ):
            self.assertIsNone(tomtom_traffic.get_road_name(21.0, 105.8))

    def test_nominatim_reverse_geocodes_and_caches_road_name(self):
        response = {'address': {'city': 'Hà Nội', 'road': 'Phố Hoàng Diệu'}}
        with patch.object(
            tomtom_traffic,
            'urlopen',
            return_value=MockResponse(json.dumps(response).encode(), 'application/json'),
        ) as request:
            name = tomtom_traffic.get_osm_road_name(21.0, 105.8)
            cached = tomtom_traffic.get_osm_road_name(21.0, 105.8)

        self.assertEqual(name, 'Phố Hoàng Diệu')
        self.assertEqual(cached, name)
        self.assertEqual(request.call_count, 1)
        req = request.call_args.args[0]
        self.assertEqual(urlparse(req.full_url).scheme, 'https')
        self.assertEqual(urlparse(req.full_url).netloc, 'nominatim.openstreetmap.org')
        self.assertEqual(parse_qs(urlparse(req.full_url).query), {
            'lat': ['21.000000'],
            'lon': ['105.800000'],
            'format': ['jsonv2'],
            'addressdetails': ['1'],
            'zoom': ['18'],
            'accept-language': ['vi'],
        })
        self.assertIn('VietSafe/1.0', req.get_header('User-agent'))

    def test_tomtom_forbidden_reverse_geocode_has_distinct_error(self):
        error = HTTPError(
            tomtom_traffic.REVERSE_GEOCODE_URL,
            403,
            'Forbidden',
            {},
            None,
        )
        with patch.object(tomtom_traffic, 'urlopen', side_effect=error):
            with self.assertRaises(tomtom_traffic.TomTomPermissionDenied):
                tomtom_traffic.get_road_name(21.0, 105.8)

    def test_rejects_out_of_region_clicks_and_invalid_tile_coordinates(self):
        with self.assertRaisesRegex(tomtom_traffic.TomTomUnavailable, 'ngoài vùng'):
            tomtom_traffic.get_flow_segment(40.0, 10.0)
        with self.assertRaisesRegex(tomtom_traffic.TomTomUnavailable, 'nằm ngoài phạm vi'):
            tomtom_traffic.get_flow_tile(3, 8, 0)

    def test_missing_key_is_reported_without_network_request(self):
        os.environ.pop('TOMTOM_API_KEY')
        with patch.object(tomtom_traffic, 'urlopen') as request:
            with self.assertRaisesRegex(tomtom_traffic.TomTomUnavailable, 'TOMTOM_API_KEY'):
                tomtom_traffic.get_flow_tile(15, 1, 1)
            request.assert_not_called()

    def test_reports_quota_errors_without_leaking_the_api_key(self):
        error = HTTPError(
            tomtom_traffic.FLOW_TILES_URL,
            429,
            'Too Many Requests',
            {},
            None,
        )
        with patch.object(tomtom_traffic, 'urlopen', side_effect=error):
            with self.assertRaisesRegex(tomtom_traffic.TomTomUnavailable, 'hạn mức'):
                tomtom_traffic.get_flow_tile(15, 1, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
