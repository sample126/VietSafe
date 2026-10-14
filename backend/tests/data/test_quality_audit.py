import copy
import hashlib
import json
import unittest

from tests.data.feature_helpers import fixture, feature_rows, dataset
from tests.data.alignment_helpers import grid, registry, road, T, A
from vietsafe.data_pipeline.audit import QualityIssue, audit_artifacts
from vietsafe.data_pipeline.end_to_end import build_fixture_artifacts
from vietsafe.data_pipeline.features.graph import build_graph
from vietsafe.data_pipeline.processing.alignment import align_environment


def codes(report):
    return {issue['code'] for issue in report.to_dict()['issues']}


class QualityAuditTests(unittest.TestCase):
    def test_valid_artifacts_report_and_severity(self):
        report=audit_artifacts(**build_fixture_artifacts())
        self.assertEqual(report.to_dict()['errors'],0)
        self.assertTrue(report.to_dict()['integrity_pass'])
        self.assertGreater(report.to_dict()['warnings'],0)
        self.assertIn('REGISTRY_VALIDATED',codes(report))
        with self.assertRaises(ValueError):QualityIssue('FATAL','x','x','x')

    def test_missingness_zero_not_missing(self):
        report=audit_artifacts(registry(),grids=[grid()]).to_dict()
        metric=next(m['value'] for m in report['metrics'] if m['name']=='missingness')
        self.assertEqual(metric,dict(count=9,available_count=8,missing_count=1,missing_ratio=1/9))
        summary=next(m['value'] for m in report['metrics'] if m['name']=='value_summary')
        self.assertEqual(summary['minimum'],0)
        self.assertEqual(summary['maximum'],5)

    def test_missingness_has_no_arbitrary_error_threshold(self):
        g=grid(values=[[None]*3 for _ in range(3)])
        report=audit_artifacts(registry(),grids=[g])
        self.assertEqual(report.to_dict()['errors'],0)
        self.assertIn('MISSING_VALUES',codes(report))

    def test_nonfinite_detected_and_report_serializable(self):
        payload=grid().to_dict();payload['values'][0][0]=float('nan')
        report=audit_artifacts(registry(),grids=[payload])
        self.assertIn('NONFINITE_VALUE',codes(report))
        self.assertIn('GRID_INVALID',codes(report))
        self.assertEqual(json.loads(report.to_json()),report.to_dict())

    def test_grid_range_units_shape_crs_and_provenance(self):
        for field,value in (('units','cm'),('rows',4),('raw_checksum','bad'),('product','')):
            payload=grid().to_dict();payload[field]=value
            with self.subTest(field=field):
                self.assertIn('GRID_INVALID',codes(audit_artifacts(registry(),grids=[payload])))
        for source,value in (('gpm',-1),('smap',1.1)):
            payload=grid(source).to_dict();payload['values'][0][0]=value
            self.assertIn('GRID_INVALID',codes(audit_artifacts(registry(),grids=[payload])))
        payload=grid().to_dict();payload['metadata']['crs']='EPSG:3857'
        self.assertIn('GRID_INVALID',codes(audit_artifacts(registry(),grids=[payload])))

    def test_duplicate_registry_ids(self):
        payload=registry().to_dict();payload['roads']*=2
        self.assertIn('DUPLICATE_ROAD_ID',codes(audit_artifacts(payload)))

    def test_empty_and_invalid_registry(self):
        payload=registry().to_dict();payload['roads']=[]
        self.assertIn('EMPTY_REGISTRY',codes(audit_artifacts(payload)))
        for field,value in (('directionality','sideways'),('coordinates',[[float('inf'),0],[0,0]])):
            payload=registry().to_dict();payload['roads'][0][field]=value
            self.assertIn('REGISTRY_INVALID',codes(audit_artifacts(payload)))

    def test_duplicate_alignment(self):
        reg=registry();aligned=align_environment(reg,gpm=[grid()],targets=[(T,A)]).to_dict()
        aligned['dynamic'].append(copy.deepcopy(aligned['dynamic'][0]))
        self.assertIn('DUPLICATE_ALIGNED_RECORD',codes(audit_artifacts(reg,alignment=aligned)))

    def test_alignment_null_reason_consistency(self):
        reg=registry();aligned=align_environment(reg,targets=[(T,A)]).to_dict()
        aligned['dynamic'][0]['missing_reason']=None
        self.assertIn('ALIGNMENT_INVALID',codes(audit_artifacts(reg,alignment=aligned)))

    def test_alignment_silent_zero_fill_detected_against_grid(self):
        reg=registry(road(21.032,105.802))
        g=grid();aligned=align_environment(reg,gpm=[g],targets=[(T,A)]).to_dict()
        record=next(r for r in aligned['dynamic'] if r['source_type']=='gpm')
        record['value']=0;record['missing_reason']=None
        self.assertIn('ALIGNMENT_VALUE_MISMATCH',codes(audit_artifacts(reg,grids=[g],alignment=aligned)))

    def test_valid_feature_series_and_derived_rain(self):
        reg,aligned,labels=fixture()
        report=audit_artifacts(reg,alignment=aligned,feature_rows=feature_rows(),dataset=dataset(),labels=labels)
        self.assertEqual(report.to_dict()['errors'],0,report.to_json())

    def test_duplicate_feature_row(self):
        reg,aligned,_=fixture();rows=list(feature_rows());rows.append(rows[0])
        self.assertIn('DUPLICATE_FEATURE_ROW',codes(audit_artifacts(reg,alignment=aligned,feature_rows=rows)))

    def test_wrong_feature_mask(self):
        reg,aligned,_=fixture();rows=[r.to_dict() for r in feature_rows()]
        rows[0]['mask']['precipitation_rate_mm_h']=False
        self.assertIn('MASK_MISMATCH',codes(audit_artifacts(reg,alignment=aligned,feature_rows=rows)))

    def test_derived_rain_injection(self):
        for name in ('rain_30m_mm','rain_1h_mm','rain_3h_mm'):
            reg,aligned,_=fixture();rows=[r.to_dict() for r in feature_rows()]
            row=rows[10];row['features'][name]=99;row['mask'][name]=True;row['missing_reasons'][name]=None
            with self.subTest(name=name):
                self.assertIn('DERIVED_RAIN_MISMATCH',codes(audit_artifacts(reg,alignment=aligned,feature_rows=rows)))

    def test_missing_bin_cannot_be_partial_sum(self):
        reg,aligned,_=fixture();rows=[r.to_dict() for r in feature_rows()]
        row=rows[11];row['features']['rain_3h_mm']=4;row['mask']['rain_3h_mm']=True;row['missing_reasons']['rain_3h_mm']=None
        self.assertIn('DERIVED_RAIN_MISMATCH',codes(audit_artifacts(reg,alignment=aligned,feature_rows=rows)))

    def test_graph_checksum_and_connectivity(self):
        reg,_,_=fixture();graph=build_graph(reg).to_dict();graph['checksum']='0'*64
        self.assertIn('CHECKSUM_MISMATCH',codes(audit_artifacts(reg,graph=graph)))
        graph=build_graph(reg).to_dict();graph['adjacency'][0][0]=1
        self.assertIn('GRAPH_SELF_LOOP',codes(audit_artifacts(reg,graph=graph)))

    def test_graph_shape_and_isolation(self):
        reg=registry();report=audit_artifacts(reg,graph=build_graph(reg))
        self.assertEqual(report.to_dict()['errors'],0)
        self.assertIn('ISOLATED_NODES',codes(report))
        payload=build_graph(reg).to_dict();payload['adjacency']=[]
        self.assertIn('GRAPH_SHAPE',codes(audit_artifacts(reg,graph=payload)))

    def test_dataset_shape_checksum_and_mask(self):
        reg,_,labels=fixture()
        for mode,code in (('shape','SAMPLE_SHAPE'),('checksum','CHECKSUM_MISMATCH'),('mask','MASK_MISMATCH')):
            payload=dataset().to_dict()
            if mode=='shape':payload['samples'][0]['X']=[]
            if mode=='checksum':payload['graph_checksum']='0'*64
            if mode=='mask':payload['samples'][0]['X_mask'][0][0][0]=False
            self.assertIn(code,codes(audit_artifacts(reg,feature_rows=feature_rows(),dataset=payload,labels=labels)))

    def test_deterministic_report_and_no_mutation(self):
        artifacts=build_fixture_artifacts()
        before={k:([x.to_dict() for x in v] if isinstance(v,tuple) else v.to_dict()) for k,v in artifacts.items()}
        a=audit_artifacts(**artifacts)
        artifacts['grids']=tuple(reversed(artifacts['grids']))
        artifacts['feature_rows']=tuple(reversed(artifacts['feature_rows']))
        b=audit_artifacts(**artifacts)
        self.assertEqual(a.to_json(),b.to_json())
        self.assertEqual(a.checksum(),hashlib.sha256(a.to_json().encode()).hexdigest())
        self.assertEqual(before['alignment'],artifacts['alignment'].to_dict())
        self.assertEqual(before['dataset'],artifacts['dataset'].to_dict())

    def test_synthetic_warning_and_no_raw_paths(self):
        report=audit_artifacts(**build_fixture_artifacts())
        self.assertIn('SYNTHETIC_DATA',codes(report))
        self.assertNotIn('/workspace/',report.to_json())
        self.assertNotIn('EARTHDATA_TOKEN',report.to_json())

    def test_missing_lineage_is_not_claimed_verified(self):
        reg,_,_=fixture()
        report=audit_artifacts(reg,feature_rows=feature_rows(),dataset=dataset())
        self.assertIn('LINEAGE_NOT_VERIFIED',codes(report))

    def test_malformed_payload_reports_instead_of_crashing(self):
        reg,_,_=fixture()
        for changes in ({'samples':[None]}, {'samples':[{'issue_time':[], 'target_time':{}}]},
                        {'lookback_steps':'six'}):
            payload=dataset().to_dict();payload.update(changes)
            with self.subTest(changes=changes):
                report=audit_artifacts(reg,dataset=payload)
                self.assertGreater(report.to_dict()['errors'],0)
                json.loads(report.to_json())
