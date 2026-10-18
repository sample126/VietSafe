import unittest
from dataclasses import replace

from tests.data.feature_helpers import dataset
from vietsafe.data_pipeline.features.split import chronological_split


class DatasetSplitTests(unittest.TestCase):
    def setUp(self):
        self.dataset=dataset(lookback_steps=1)

    def test_chronological_no_randomization(self):
        result=chronological_split(self.dataset,train_ratio=.5,validation_ratio=.25,test_ratio=.25,
                                   preserve_events=False,purge_overlap=False).to_dict()
        train,val,test=(result[name] for name in ('train','validation','test'))
        self.assertEqual((len(train),len(val),len(test)),(6,3,3))
        self.assertLess(train[-1]['target_time'],val[0]['target_time'])
        self.assertLess(val[-1]['target_time'],test[0]['target_time'])
        self.assertEqual([s['target_time'] for s in train+val+test],sorted(s['target_time'] for s in train+val+test))

    def test_order_independent_checksum(self):
        a=chronological_split(self.dataset)
        b=chronological_split(replace(self.dataset,samples=tuple(reversed(self.dataset.samples))))
        self.assertEqual(a.to_dict(),b.to_dict())
        self.assertEqual(a.checksum(),b.checksum())

    def test_no_sample_overlap(self):
        result=chronological_split(self.dataset).to_dict()
        checks=[s['sample_checksum'] for name in ('train','validation','test') for s in result[name]]
        self.assertEqual(len(checks),len(set(checks)))

    def test_ratios_validation(self):
        for ratios in ((.5,.5,.5),(-.1,.5,.6),(True,0,0),(float('nan'),0,1)):
            with self.subTest(ratios=ratios),self.assertRaises(ValueError):
                chronological_split(self.dataset,train_ratio=ratios[0],validation_ratio=ratios[1],test_ratio=ratios[2])

    def test_events_preserved(self):
        result=chronological_split(self.dataset,purge_overlap=False).to_dict()
        placement={}
        for name in ('train','validation','test'):
            for sample in result[name]:
                for event in sample['event_ids']:
                    self.assertIn(placement.get(event,name),(name,))
                    placement[event]=name

    def test_boundary_history_purged(self):
        result=chronological_split(self.dataset,train_ratio=.5,validation_ratio=.25,test_ratio=.25,
                                   preserve_events=False).to_dict()
        self.assertTrue(result['purged'])
        lookup={s.checksum():s for s in self.dataset.samples}
        prior=None
        for name in ('train','validation','test'):
            part=result[name]
            if prior:
                self.assertTrue(all(lookup[s['sample_checksum']].history_timestamps[0]>prior for s in part))
            if part:prior=max(s['target_time'] for s in part)

    def test_target_time_ties_never_split(self):
        original=self.dataset.samples
        tied=replace(original[1],target_time=original[0].target_time)
        changed=replace(self.dataset,samples=(original[0],tied,*original[2:]))
        result=chronological_split(changed,train_ratio=1/12,validation_ratio=5/12,test_ratio=.5,
                                   preserve_events=False,purge_overlap=False).to_dict()
        partitions=[name for name in ('train','validation','test') if any(
            s['target_time']==original[0].target_time for s in result[name])]
        self.assertEqual(len(partitions),1)

    def test_long_event_may_force_empty_partition(self):
        samples=tuple(replace(s,event_ids=('one-event',)) for s in self.dataset.samples)
        result=chronological_split(replace(self.dataset,samples=samples),purge_overlap=False).to_dict()
        self.assertEqual(sum(bool(result[n]) for n in ('train','validation','test')),1)

    def test_empty_dataset(self):
        result=chronological_split(replace(self.dataset,samples=())).to_dict()
        self.assertTrue(all(result[n]==[] for n in ('train','validation','test')))
