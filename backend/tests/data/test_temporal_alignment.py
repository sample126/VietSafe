import unittest

from tests.data.alignment_helpers import A, T, ROOT, grid, road
from vietsafe.data_pipeline.alignment import AlignmentInputError
from vietsafe.data_pipeline.ingestion.dem import read_hgt
from vietsafe.data_pipeline.processing.spatial_alignment import sample_road
from vietsafe.data_pipeline.processing.temporal_alignment import (
    canonical_timestamp, validate_target, align_temporal, align_static,
)


class TemporalAlignmentTests(unittest.TestCase):
    def test_canonical_bins(self):
        for value in (T, '2026-10-08T02:00:00Z'):
            self.assertEqual(canonical_timestamp(value), value)

    def test_reject_noncanonical(self):
        for value in ('2026-10-08T02:15:00Z', '2026-10-08T02:30:01Z',
                      '2026-10-08T02:30:00.001Z', '2026-10-08T02:30:00', None):
            with self.subTest(value=value), self.assertRaises(AlignmentInputError):
                canonical_timestamp(value)

    def test_offset_normalization(self):
        self.assertEqual(canonical_timestamp('2026-10-08T09:30:00+07:00'), T)

    def test_as_of_before_target_rejected(self):
        with self.assertRaises(AlignmentInputError) as caught:
            validate_target(T, '2026-10-08T02:29:59Z')
        self.assertEqual(caught.exception.code, 'AS_OF_BEFORE_TIMESTAMP')

    def test_as_of_need_not_be_bin(self):
        self.assertEqual(validate_target(T, '2026-10-08T04:01:12Z')[1], '2026-10-08T04:01:12Z')

    def test_future_observation(self):
        record = align_temporal(sample_road(road(), grid()), '2026-10-08T02:00:00Z', A)
        self.assertIsNone(record.value)
        self.assertEqual(record.missing_reason, 'FUTURE_OBSERVATION')

    def test_as_of_blocks_leakage(self):
        record = align_temporal(sample_road(road(), grid()), T, T)
        self.assertIsNone(record.value)
        self.assertEqual(record.missing_reason, 'NOT_AVAILABLE_AS_OF')
        self.assertIsNone(record.to_dict()['value'])
        self.assertEqual(record.to_dict()['source_available_at'], A)

    def test_backfill_preserves_real_availability(self):
        record = align_temporal(sample_road(road(), grid()), T, A)
        self.assertEqual(record.value, 0)
        self.assertIsNone(record.missing_reason)
        self.assertEqual(record.as_of, A)
        self.assertEqual(record.to_dict()['source_available_at'], A)

    def test_gpm_wrong_interval_end(self):
        record = align_temporal(sample_road(road(), grid()), '2026-10-08T03:00:00Z', A)
        self.assertEqual(record.missing_reason, 'NO_EXACT_TEMPORAL_MATCH')
        self.assertIsNone(record.value)

    def test_gpm_observed_must_equal_end(self):
        g = grid(observed_at='2026-10-08T02:15:00Z')
        record = align_temporal(sample_road(road(), g), T, A)
        self.assertEqual(record.missing_reason, 'NO_EXACT_TEMPORAL_MATCH')

    def test_gpm_keeps_rate_without_aggregation(self):
        sample = sample_road(road(21.032, 105.801), grid())
        record = align_temporal(sample, T, A)
        self.assertEqual(record.value, 1.5)
        self.assertEqual(record.to_dict()['units'], 'mm/h')
        self.assertEqual(record.to_dict()['variable'], 'precipitation_rate')

    def test_smap_exact_match(self):
        record = align_temporal(sample_road(road(), grid('smap')), T, A)
        self.assertEqual(record.value, 0)
        self.assertIsNone(record.missing_reason)

    def test_smap_no_carry_forward(self):
        record = align_temporal(sample_road(road(), grid('smap')), '2026-10-08T03:00:00Z', A)
        self.assertEqual(record.missing_reason, 'NO_EXACT_TEMPORAL_MATCH')
        self.assertIsNone(record.value)

    def test_smap_future_blocked(self):
        record = align_temporal(sample_road(road(), grid('smap')), '2026-10-08T02:00:00Z', A)
        self.assertEqual(record.missing_reason, 'FUTURE_OBSERVATION')

    def test_nodata_preserved(self):
        record = align_temporal(sample_road(road(21.032, 105.802), grid()), T, A)
        self.assertIsNone(record.value)
        self.assertEqual(record.missing_reason, 'GRID_NODATA')

    def test_dem_static_no_fake_time(self):
        dem = read_hgt(ROOT / 'environment/dem/N21E105-mini.hgt', product_version='fixture-v1',
                       source_uri='urn:vietsafe:fixture:dem', fixture_tile='N21E105.hgt')
        sample = sample_road(road(), dem)
        record = align_static(sample)
        self.assertIsNone(record.timestamp)
        self.assertIsNone(record.as_of)
        self.assertIsNone(record.to_dict()['source_observed_at'])
        with self.assertRaises(AlignmentInputError):
            align_temporal(sample, T, A)

    def test_dynamic_cannot_be_static(self):
        with self.assertRaises(AlignmentInputError):
            align_static(sample_road(road(), grid()))
