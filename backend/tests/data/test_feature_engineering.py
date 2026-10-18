import copy
import unittest
from unittest.mock import patch

from tests.data.feature_helpers import fixture, feature_rows
from vietsafe.data_pipeline.features.engineering import build_features, FEATURE_NAMES, shift


class FeatureEngineeringTests(unittest.TestCase):
    def setUp(self):
        self.registry,self.aligned,_ = fixture()
        self.times = sorted({r['timestamp'] for r in self.aligned['dynamic']})
        self.rows = {(r.timestamp,r.road_id):r for r in feature_rows()}

    def test_rate_and_half_hour_amount(self):
        row = self.rows[self.times[0],'HN-001']
        self.assertEqual(row.values[:2],(2,1))

    def test_one_hour_exact_two_bins(self):
        self.assertIsNone(self.rows[self.times[0],'HN-001'].values[2])
        self.assertEqual(self.rows[self.times[1],'HN-001'].values[2],2)

    def test_three_hour_exact_six_bins(self):
        self.assertIsNone(self.rows[self.times[4],'HN-001'].values[3])
        row = self.rows[self.times[5],'HN-001']
        self.assertEqual(row.values[3],6)
        bins=row.to_dict()['provenance']['rain_bins']['rain_3h_mm']
        self.assertEqual([b['timestamp'] for b in bins],self.times[:6])

    def test_zero_vs_missing_masks(self):
        zero=self.rows[self.times[0],'HN-002']
        self.assertEqual(zero.values[:2],(0,0))
        self.assertEqual(zero.mask[:2],(True,True))
        missing=self.rows[self.times[4],'HN-002']
        self.assertIsNone(missing.values[0])
        self.assertFalse(missing.mask[0])
        self.assertIsNotNone(missing.missing_reasons[0])

    def test_missing_bin_blocks_window(self):
        row=self.rows[self.times[5],'HN-002']
        self.assertIsNone(row.values[2])
        self.assertIsNone(row.values[3])

    def test_soil_no_carry_forward(self):
        row=self.rows[self.times[2],'HN-002']
        self.assertIsNone(row.values[4])
        self.assertFalse(row.mask[4])
        self.assertEqual(self.rows[self.times[0],'HN-001'].values[4],0)

    def test_elevation_static_join(self):
        for t in self.times:
            self.assertEqual(self.rows[t,'HN-001'].values[5],0)
            self.assertEqual(self.rows[t,'HN-002'].values[5],10)
        self.assertEqual(self.rows[self.times[0],'HN-001'].provenance['elevation_policy'],
                         'static-road-network-join-v1')

    def test_wrong_interval_not_accumulated(self):
        for record in self.aligned['dynamic']:
            if record['timestamp']==self.times[0] and record['source_type']=='gpm':
                record['source_metadata']['interval_start']=shift(self.times[0],-2)
        row=build_features(self.registry,self.aligned,as_of=self.times[0])[0]
        self.assertEqual(row.values[0],2)
        self.assertIsNone(row.values[1])
        self.assertEqual(row.provenance['rain_bins']['rain_30m_mm'][0]['missing_reason'],
                         'GPM_INTERVAL_NOT_30_MINUTES')

    def test_order_independence(self):
        before=build_features(self.registry,self.aligned,as_of=self.times[-1])
        self.aligned['dynamic'].reverse();self.aligned['static'].reverse()
        after=build_features(self.registry,self.aligned,as_of=self.times[-1])
        self.assertEqual([r.to_dict() for r in before],[r.to_dict() for r in after])
        self.assertEqual([(r.timestamp,r.road_id) for r in after],sorted((r.timestamp,r.road_id) for r in after))

    def test_aligned_backfill_not_reinterpreted(self):
        for r in self.aligned['dynamic']:
            if r['timestamp']==self.times[0]:r['as_of']=self.times[4]
        rows=build_features(self.registry,self.aligned,as_of=self.times[0])
        self.assertTrue(all(r.values[0] is None and r.values[4] is None for r in rows))

    def test_source_available_after_as_of_blocked(self):
        for r in self.aligned['dynamic']:
            if r['timestamp']==self.times[0]:r['source_available_at']=self.times[4]
        rows=build_features(self.registry,self.aligned,as_of=self.times[0])
        self.assertTrue(all(r.values[0] is None for r in rows))

    def test_future_observed_blocked(self):
        for r in self.aligned['dynamic']:
            if r['timestamp']==self.times[0]:r['source_observed_at']=self.times[1]
        rows=build_features(self.registry,self.aligned,as_of=self.times[0])
        self.assertTrue(all(r.values[0] is None for r in rows))

    def test_multiple_products_masked_not_chosen(self):
        record=copy.deepcopy(self.aligned['dynamic'][0]);record['product']='OTHER'
        self.aligned['dynamic'].append(record)
        row=build_features(self.registry,self.aligned,as_of=self.times[0])[0]
        self.assertIsNone(row.values[0])
        self.assertEqual(row.missing_reasons[0],'MULTIPLE_SOURCE_CANDIDATES')

    def test_invalid_registry_and_nonfinite(self):
        bad=copy.deepcopy(self.aligned);bad['registry_checksum']='0'*64
        with self.assertRaises(ValueError):build_features(self.registry,bad,as_of=self.times[-1])
        self.aligned['dynamic'][0]['value']=float('nan')
        with self.assertRaises(ValueError):build_features(self.registry,self.aligned,as_of=self.times[-1])

    def test_no_network_or_input_mutation(self):
        before=copy.deepcopy(self.aligned)
        with patch('socket.socket',side_effect=AssertionError('offline')):
            build_features(self.registry,self.aligned,as_of=self.times[-1])
        self.assertEqual(before,self.aligned)
        self.assertEqual(FEATURE_NAMES,('precipitation_rate_mm_h','rain_30m_mm','rain_1h_mm',
                                       'rain_3h_mm','soil_moisture','elevation_m'))
