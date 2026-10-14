import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2] / 'backend'))
from vietsafe import auth, config, db, reports, service
from vietsafe.core.engine import build_snapshot, calculate_routes
from vietsafe.core.network import NODES, ROADS, nearest_road, road_midpoint
from vietsafe.web.server import Handler, ThreadingHTTPServer
from vietsafe.providers import tomtom_traffic, nasa_gpm, openmeteo_weather

"""Local NASA credential configuration tests. Never embed live credentials in tests."""
from datetime import datetime, timezone
from pathlib import Path
import os
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from vietsafe.config import load_local_env
from scripts.kiem_tra_nasa import token_expiration
from vietsafe.config import load_local_env


class NasaConfigurationTests(unittest.TestCase):
    def test_load_env_token_and_honor_preexisting_environment(self):
        with TemporaryDirectory() as work:
            path = Path(work) / '.env'
            path.write_text('NASA_EARTHDATA_TOKEN=example-local-token\n', encoding='utf-8')
            with patch.dict(os.environ, {}, clear=True):
                load_local_env(path)
                self.assertEqual(os.environ['NASA_EARTHDATA_TOKEN'], 'example-local-token')
            with patch.dict(os.environ, {'NASA_EARTHDATA_TOKEN': 'preferred-process-token'}, clear=True):
                load_local_env(path)
                self.assertEqual(os.environ['NASA_EARTHDATA_TOKEN'], 'preferred-process-token')

    def test_jwt_expiration_is_read_without_exposing_token(self):
        # Expiry parser reads JWT metadata, without claiming to verify the signature.
        self.assertIsNone(token_expiration('invalid-token'))
        self.assertIsNone(token_expiration('a.invalid-payload.b'))
        self.assertIsNone(token_expiration('a.e30.b'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
