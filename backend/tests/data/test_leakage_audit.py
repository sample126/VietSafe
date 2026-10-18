import unittest

from tests.data.feature_helpers import fixture,feature_rows,dataset
from tests.data.test_quality_audit import codes
from vietsafe.data_pipeline.audit import audit_artifacts
from vietsafe.data_pipeline.features.split import chronological_split


class LeakageAuditTests(unittest.TestCase):
    def test_valid_feature_timeline(self):
        reg,aligned,_=fixture()
        report=audit_artifacts(reg,alignment=aligned,feature_rows=feature_rows())
        self.assertNotIn('FEATURE_LEAKAGE',codes(report))

    def test_source_available_after_as_of(self):
        reg,aligned,_=fixture()
        aligned['dynamic'][0]['source_available_at']='2026-10-09T00:00:00Z'
        self.assertIn('FEATURE_LEAKAGE',codes(audit_artifacts(reg,alignment=aligned)))

    def test_future_source_observation(self):
        reg,aligned,_=fixture()
        aligned['dynamic'][0]['source_observed_at']='2026-10-09T00:00:00Z'
        self.assertIn('FEATURE_LEAKAGE',codes(audit_artifacts(reg,alignment=aligned)))

    def test_feature_as_of_after_issue_context(self):
        reg,_,_=fixture()
        report=audit_artifacts(reg,feature_rows=feature_rows(),issue_time=feature_rows()[0].timestamp)
        self.assertIn('FEATURE_LEAKAGE',codes(report))

    def test_dataset_future_feature_snapshot(self):
        reg,_,labels=fixture();doc=dataset().to_dict()
        doc['samples'][0]['feature_as_of'][0][0]='2026-10-09T00:00:00Z'
        self.assertIn('FEATURE_LEAKAGE',codes(audit_artifacts(reg,feature_rows=feature_rows(),dataset=doc,labels=labels)))

    def test_target_in_feature_names(self):
        reg,_,_=fixture();doc=dataset().to_dict()
        doc['feature_names'][0]=doc['target_name']
        self.assertIn('TARGET_LEAKAGE',codes(audit_artifacts(reg,dataset=doc)))

    def test_target_value_injected_into_x(self):
        reg,_,labels=fixture();doc=dataset().to_dict()
        doc['samples'][0]['X'][0][0][0]=doc['samples'][0]['y'][0]
        report=audit_artifacts(reg,feature_rows=feature_rows(),dataset=doc,labels=labels)
        self.assertIn('TARGET_LEAKAGE',codes(report))

    def test_equal_legitimate_zero_is_not_target_leakage(self):
        # Numeric equality alone is insufficient: the X still matches its feature evidence.
        reg,_,_=fixture();doc=dataset().to_dict();doc['samples'][0]['y']=[0,0]
        report=audit_artifacts(reg,feature_rows=feature_rows(),dataset=doc)
        self.assertNotIn('TARGET_LEAKAGE',codes(report))

    def test_target_before_or_equal_issue(self):
        for mode in ('equal','before'):
            reg,_,_=fixture();doc=dataset().to_dict();sample=doc['samples'][0]
            sample['target_time']=sample['issue_time'] if mode=='equal' else sample['history_timestamps'][0]
            self.assertIn('TARGET_LEAKAGE',codes(audit_artifacts(reg,dataset=doc)))

    def test_split_chronology_violation(self):
        reg,_,_=fixture();built=dataset(lookback_steps=1)
        split=chronological_split(built,preserve_events=False,purge_overlap=False).to_dict()
        split['train'],split['test']=split['test'],split['train']
        self.assertIn('SPLIT_CHRONOLOGY',codes(audit_artifacts(reg,dataset=built,split=split)))

    def test_split_duplicate_event_and_overlap(self):
        reg,_,_=fixture();built=dataset(lookback_steps=1)
        split=chronological_split(built,preserve_events=False,purge_overlap=False).to_dict()
        split['validation'].append(split['train'][0])
        self.assertIn('SPLIT_DUPLICATE',codes(audit_artifacts(reg,dataset=built,split=split)))
        split=chronological_split(built,train_ratio=.5,validation_ratio=.25,test_ratio=.25,
                                  preserve_events=False,purge_overlap=False).to_dict()
        split['preserve_events']=True
        self.assertIn('EVENT_SPLIT',codes(audit_artifacts(reg,dataset=built,split=split)))
        split['purge_overlap']=True
        self.assertIn('SPLIT_OVERLAP',codes(audit_artifacts(reg,dataset=built,split=split)))

    def test_empty_split_warning_not_error(self):
        reg,_,_=fixture();built=dataset()
        split=chronological_split(built)
        report=audit_artifacts(reg,feature_rows=feature_rows(),dataset=built,split=split)
        self.assertIn('EMPTY_SPLIT',codes(report))
        self.assertEqual(report.to_dict()['errors'],0)
