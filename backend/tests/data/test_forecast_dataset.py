import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from tests.data.feature_helpers import fixture,feature_rows,dataset,NOTICE
from vietsafe.data_pipeline.features.engineering import FEATURE_NAMES,build_features,shift
from vietsafe.data_pipeline.features.dataset import build_dataset
from vietsafe.data_pipeline.features.split import chronological_split


class ForecastDatasetTests(unittest.TestCase):
    def test_shapes_mask_and_feature_names(self):
        built=dataset()
        sample=built.samples[0]
        self.assertEqual(len(sample.X),6)
        for values,masks in zip(sample.X,sample.X_mask):
            self.assertEqual(len(values),2)
            for row,mask in zip(values,masks):
                self.assertEqual(len(row),6)
                self.assertEqual(mask,tuple(value is not None for value in row))
        self.assertEqual(len(sample.y),2)
        self.assertEqual(built.to_dict()['feature_names'],list(FEATURE_NAMES))
        self.assertEqual(built.graph.road_ids,('HN-001','HN-002'))

    def test_horizons_and_target_shift(self):
        one,two=dataset(horizon_steps=1),dataset(horizon_steps=2)
        a,b=one.samples[0],two.samples[0]
        self.assertEqual(a.target_time,shift(a.issue_time,1))
        self.assertEqual(b.target_time,shift(b.issue_time,2))
        self.assertEqual(a.X,b.X)
        self.assertEqual(a.y,(160,161))
        self.assertEqual(b.y,(170,171))

    def test_labels_never_in_x(self):
        built=dataset()
        for sample in built.samples:
            self.assertTrue(all(value is None or value<100 for step in sample.X for row in step for value in row))
            self.assertTrue(all(value>=100 for value in sample.y))
            self.assertTrue(all(time>sample.issue_time for time in sample.label_available_at))

    def test_missing_features_not_zero_filled(self):
        sample=dataset().samples[0]
        self.assertIsNone(sample.X[4][1][0])
        self.assertFalse(sample.X_mask[4][1][0])
        self.assertEqual(sample.X[0][1][0],0)
        self.assertTrue(sample.X_mask[0][1][0])

    def test_insufficient_history_reported(self):
        built=dataset()
        excluded=built.to_dict()['excluded']
        self.assertEqual(len(excluded),5)
        self.assertTrue(all(x['reason']=='INSUFFICIENT_HISTORY' for x in excluded))
        self.assertEqual(len(built.samples),7)

    def test_missing_timestep_never_skipped(self):
        registry,_,labels=fixture()
        rows=feature_rows()
        missing_time=rows[4].timestamp
        kept=[r for r in rows if r.timestamp!=missing_time]
        built=build_dataset(registry,kept,labels,target_name='flood_depth_cm')
        for sample in built.samples:
            self.assertNotIn(missing_time,sample.history_timestamps)
            self.assertEqual(sample.history_timestamps,tuple(shift(sample.issue_time,o) for o in range(-5,1)))

    def test_missing_road_row_excludes_instead_of_fabricating(self):
        registry,_,labels=fixture()
        rows=feature_rows()[1:]
        built=build_dataset(registry,rows,labels,target_name='flood_depth_cm')
        self.assertNotIn(feature_rows()[10].timestamp,[s.issue_time for s in built.samples])

    def test_as_of_after_issue_rejected(self):
        registry,aligned,labels=fixture()
        last=max(r.timestamp for r in feature_rows())
        backfill=build_features(registry,aligned,as_of=last)
        earlier=shift(last,-1)
        built=build_dataset(registry,backfill,labels,target_name='flood_depth_cm',issue_times=[earlier])
        self.assertEqual(built.samples,())
        self.assertEqual(built.to_dict()['excluded'][0]['reason'],'INSUFFICIENT_HISTORY')

    def test_latest_eligible_snapshot_not_future(self):
        registry,_,labels=fixture()
        rows=feature_rows();old=rows[0]
        later=replace(old,as_of=shift(old.timestamp,4),values=(9,4.5,None,None,0,0))
        built=build_dataset(registry,[*rows,later],labels,target_name='flood_depth_cm',lookback_steps=1)
        self.assertEqual(built.samples[0].X[0][0][0],2)

    def test_label_eligibility_options(self):
        registry,_,_=fixture()
        required=build_dataset(registry,feature_rows(),target_name='generic',require_targets=True)
        optional=build_dataset(registry,feature_rows(),target_name='generic',require_targets=False)
        self.assertFalse(required.samples)
        self.assertEqual(len(optional.samples),7)
        self.assertTrue(all(s.y==(None,None) and s.y_mask==(False,False) for s in optional.samples))

    def test_conflicting_labels_not_last_wins(self):
        registry,_,labels=fixture()
        conflict=replace(labels[10],value=999)
        built=build_dataset(registry,feature_rows(),[*labels,conflict],target_name='flood_depth_cm',require_targets=False)
        sample=next(s for s in built.samples if s.target_time==conflict.observed_at)
        self.assertIsNone(sample.y[0])
        self.assertEqual(sample.y_missing_reasons[0],'TARGET_CONFLICT')

    def test_deterministic_serialization_and_input_order(self):
        registry,_,labels=fixture()
        a=dataset()
        b=build_dataset(registry,reversed(feature_rows()),reversed(labels),target_name='flood_depth_cm')
        self.assertEqual(a.to_json(),b.to_json())
        self.assertEqual(a.checksum(),b.checksum())
        self.assertEqual(json.loads(a.to_json())['schema'],'vietsafe.forecast-dataset.v1')
        self.assertEqual(a.to_dict()['timestep_minutes'],30)

    def test_invalid_configuration(self):
        for config in ({'lookback_steps':0},{'horizon_steps':0},{'horizon_steps':.5},{'lookback_steps':True}):
            with self.subTest(config=config),self.assertRaises(ValueError):dataset(**config)

    def test_generic_target_and_fixture_notice(self):
        _,_,labels=fixture()
        other=replace(labels[0],target_name='generic_sensor_value',units='unit')
        self.assertEqual(other.source_metadata['fixture_notice'],NOTICE)
        self.assertEqual(other.target_name,'generic_sensor_value')

    def test_bad_labels(self):
        _,_,labels=fixture()
        for changes in ({'road_id':'bad'},{'observed_at':'2026-10-08T00:30:00'},
                        {'available_at':'2026-10-07T00:00:00Z'},{'value':float('nan')},
                        {'value':True},{'target_name':''},{'source_metadata':{'data_kind':'synthetic','source_uri':'urn:test'}}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):replace(labels[0],**changes)

    def test_unknown_label_road_rejected(self):
        registry,_,labels=fixture()
        unknown=replace(labels[0],road_id='HN-003')
        with self.assertRaises(ValueError):
            build_dataset(registry,feature_rows(),[unknown],target_name='flood_depth_cm')

    def test_mixed_target_units_rejected(self):
        registry,_,labels=fixture()
        with self.assertRaises(ValueError):
            build_dataset(registry,feature_rows(),[*labels,replace(labels[0],units='m')],
                          target_name='flood_depth_cm')

    def test_conflicting_feature_snapshot_rejected(self):
        registry,_,labels=fixture()
        rows=feature_rows()
        changed=replace(rows[0],values=(9,4.5,None,None,0,0))
        with self.assertRaises(ValueError):
            build_dataset(registry,[*rows,changed],labels,target_name='flood_depth_cm')

    def test_identical_labels_deduplicated(self):
        registry,_,labels=fixture()
        expected=dataset()
        actual=build_dataset(registry,feature_rows(),[*labels,*labels],target_name='flood_depth_cm')
        self.assertEqual(expected.to_json(),actual.to_json())

    def test_complete_pipeline_offline(self):
        registry,aligned,labels=fixture()
        with patch('socket.socket',side_effect=AssertionError('offline')), \
                patch('urllib.request.urlopen',side_effect=AssertionError('offline')):
            stamps=sorted({r['timestamp'] for r in aligned['dynamic']})
            rows=[]
            for stamp in stamps:
                rows.extend(r for r in build_features(registry,aligned,as_of=stamp) if r.timestamp==stamp)
            built=build_dataset(registry,rows,labels,target_name='flood_depth_cm',lookback_steps=1)
            split=chronological_split(built)
        self.assertEqual(len(built.samples),12)
        self.assertEqual(split.to_dict()['dataset_checksum'],built.checksum())
