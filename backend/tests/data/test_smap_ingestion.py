import unittest

from tests.data.environment_helpers import InterchangeChecks
from vietsafe.data_pipeline.ingestion.smap import read_smap


class SMAPIngestionTests(InterchangeChecks, unittest.TestCase):
    source = 'smap'
    units = 'm3/m3'
    variable = 'soil_moisture'
    loader = staticmethod(read_smap)

    def test_closed_range_endpoints(self):
        grid = self.loader(self.fixture)
        self.assertEqual(grid.values[0][0], 0)
        self.assertEqual(grid.values[1][2], 1)

    def test_out_of_range(self):
        for value in (-0.001, 1.001):
            self.payload['values'][0][0] = value
            self.assert_invalid(self.payload)
