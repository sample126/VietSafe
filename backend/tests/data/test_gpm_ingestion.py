import unittest

from tests.data.environment_helpers import InterchangeChecks
from vietsafe.data_pipeline.ingestion.gpm import read_gpm


class GPMIngestionTests(InterchangeChecks, unittest.TestCase):
    source = 'gpm'
    units = 'mm/h'
    variable = 'precipitation_rate'
    loader = staticmethod(read_gpm)

    def test_negative_precipitation(self):
        self.payload['values'][0][0] = -0.001
        self.assert_invalid(self.payload)

    def test_interval_order_and_presence(self):
        for start in ('2026-10-08T02:30:00Z', '2026-10-08T03:00:00Z', None):
            self.payload['metadata']['interval_start'] = start
            self.assert_invalid(self.payload)

    def test_interval_timezone_normalization(self):
        self.payload['metadata']['interval_start'] = '2026-10-08T09:00:00+07:00'
        self.payload['metadata']['interval_end'] = '2026-10-08T09:30:00+07:00'
        grid = self.load_payload(self.payload)
        self.assertEqual(grid.metadata['interval_start'], '2026-10-08T02:00:00Z')
        self.assertEqual(grid.metadata['interval_end'], '2026-10-08T02:30:00Z')

    def test_time_interval_consistency(self):
        self.assert_invalid({**self.payload, 'observed_at': '2026-10-08T01:00:00Z'})
        self.assert_invalid({**self.payload, 'observed_at': '2026-10-08T02:00:00Z',
                             'available_at': '2026-10-08T02:10:00Z'})
