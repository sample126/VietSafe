"""Read-only, deterministic integrity and quality audit of Data Module artifacts.

Accept model objects or their serialized dictionaries to inspect malformed payloads
without repairing them. References (registry, alignment, feature rows, labels) enable
stronger lineage checks; missing evidence produces warnings, never an invented PASS.
"""

import copy
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass

from .alignment import ALIGNMENT_VERSION
from .environment import EnvironmentalGrid
from .features.dataset import DATASET_SCHEMA
from .features.engineering import (
    FEATURE_NAMES, FEATURE_UNITS, FEATURE_VERSION, RoadFeatureRow,
    _validate_record, build_features, dt, shift,
)
from .features.graph import build_graph
from .features.labels import RoadTarget
from .processing.temporal_alignment import canonical_timestamp
from .registry import RoadRegistry, RoadSegment, canonical_bytes, checksum, finite_number

AUDIT_VERSION = 'quality-audit-v1'


@dataclass(frozen=True)
class QualityIssue:
    severity: str
    code: str
    artifact: str
    detail: str

    def __post_init__(self):
        if self.severity not in ('INFO', 'WARNING', 'ERROR'):
            raise ValueError('Unsupported quality severity')

    def to_dict(self):
        return dict(severity=self.severity, code=self.code, artifact=self.artifact, detail=self.detail)


@dataclass(frozen=True)
class QualityReport:
    _json: str

    def to_dict(self):
        return json.loads(self._json)

    def to_json(self):
        return self._json

    def checksum(self):
        return checksum(self.to_dict())


class _Audit:
    def __init__(self):
        self.issues = []
        self.metrics = []

    def issue(self, code, artifact, detail, severity='ERROR'):
        self.issues.append(QualityIssue(severity, code, artifact, detail))

    def metric(self, artifact, name, value):
        self.metrics.append(dict(artifact=artifact, name=name, value=value))

    def check(self, condition, code, artifact, detail):
        if not condition:
            self.issue(code, artifact, detail)
        return bool(condition)

    def finish(self):
        # Repeated evidence can raise the same issue; report it once without touching input.
        issues = sorted({canonical_bytes(issue.to_dict()) for issue in self.issues})
        decoded = [json.loads(value) for value in issues]
        counts = Counter(issue['severity'] for issue in decoded)
        document = dict(audit_version=AUDIT_VERSION, issues=decoded,
                        metrics=sorted(self.metrics, key=canonical_bytes),
                        errors=counts['ERROR'], warnings=counts['WARNING'], info=counts['INFO'],
                        integrity_pass=counts['ERROR'] == 0)
        return QualityReport(canonical_bytes(document).decode('utf-8'))


def _doc(value):
    return copy.deepcopy(value.to_dict() if hasattr(value, 'to_dict') else value)


def _safe(audit, path, function, *args):
    """Malformed serialized input yields an integrity error, never a repaired object."""
    try:
        return function(audit, *args)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError, RecursionError):
        audit.issue('MALFORMED_ARTIFACT', path, 'Malformed payload prevented remaining checks for this stage')
        return None


def _hash(value):
    try:
        return checksum(value)
    except (ValueError, TypeError, OverflowError, UnicodeError):
        return None


def _numbers_valid(value):
    if isinstance(value, dict):
        return all(_numbers_valid(v) for v in value.values())
    if isinstance(value, (tuple, list)):
        return all(_numbers_valid(v) for v in value)
    return not isinstance(value, (int, float)) or type(value) is bool or finite_number(value)


def _synthetic(value):
    if isinstance(value, dict):
        return value.get('is_test_fixture') is True or value.get('data_kind') == 'synthetic' or any(
            _synthetic(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_synthetic(v) for v in value)
    return isinstance(value, str) and ('SYNTHETIC' in value.upper() or 'TEST FIXTURE' in value.upper())


def _base(audit, document, path):
    if not audit.check(isinstance(document, dict), 'MALFORMED_ARTIFACT', path, 'Expected object'):
        return False
    audit.check(_numbers_valid(document), 'NONFINITE_VALUE', path, 'Non-finite numeric value present')
    if _synthetic(document):
        audit.issue('SYNTHETIC_DATA', path, 'Synthetic/test evidence is not production ground truth', 'WARNING')
    if 'checksum' in document:
        content = {k: v for k, v in document.items() if k != 'checksum'}
        audit.check(document['checksum'] == _hash(content), 'CHECKSUM_MISMATCH', path, 'Declared checksum differs')
    return True


def _time_check(audit, value, path, canonical=True):
    try:
        parsed = canonical_timestamp(value) if canonical else dt(value).isoformat().replace('+00:00', 'Z')
        audit.check(parsed == value, 'INVALID_TIMESTAMP', path, 'Timestamp is not canonical UTC serialization')
        return dt(value)
    except (ValueError, TypeError, OverflowError):
        audit.issue('INVALID_TIMESTAMP', path, 'Invalid timestamp')
        return None


def _missing(audit, path, values):
    count = len(values)
    missing = sum(value is None for value in values)
    audit.metric(path, 'missingness', dict(count=count, available_count=count-missing,
                                         missing_count=missing, missing_ratio=missing/count if count else 0))
    if missing:
        audit.issue('MISSING_VALUES', path, 'Missing values retained; no production threshold applied', 'WARNING')


def _registry(audit, source):
    document = _doc(source)
    if not _base(audit, document, 'registry'):
        return None
    roads = document.get('roads')
    if not audit.check(isinstance(roads, list), 'REGISTRY_INVALID', 'registry', 'roads must be a list'):
        return None
    identities = [r.get('road_id') for r in roads if isinstance(r, dict)]
    audit.check(len(identities) == len(set(str(x) for x in identities)), 'DUPLICATE_ROAD_ID', 'registry', 'Duplicate road IDs')
    audit.check(bool(roads), 'EMPTY_REGISTRY', 'registry', 'Registry is empty')
    if all(isinstance(x, str) for x in identities) and identities != sorted(identities):
        audit.issue('NONCANONICAL_ORDER', 'registry', 'Road IDs are not sorted', 'WARNING')
    try:
        valid = RoadRegistry(document.get('network_version'), [RoadSegment(**r) for r in roads])
    except (ValueError, TypeError, KeyError, AttributeError):
        audit.issue('REGISTRY_INVALID', 'registry', 'Registry validation rejected geometry/direction/identity/lineage')
        return None
    audit.metric('registry', 'road_count', len(valid))
    audit.metric('registry', 'network_version', valid.network_version)
    audit.metric('registry', 'registry_checksum', valid.checksum)
    if 'checksum' in document:
        audit.check(document['checksum'] == valid.checksum, 'CHECKSUM_MISMATCH', 'registry', 'Registry fingerprint differs')
    audit.issue('REGISTRY_VALIDATED', 'registry', 'Existing registry validator passed', 'INFO')
    return valid


def _grid(audit, source):
    document = _doc(source)
    path = 'environment/' + str(document.get('source_type', 'unknown')) if isinstance(document, dict) else 'environment'
    if not _base(audit, document, path):
        return
    try:
        EnvironmentalGrid.from_dict({k: v for k, v in document.items() if k != 'checksum'})
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        audit.issue('GRID_INVALID', path, 'Existing grid validator rejected shape/CRS/range/provenance/time')
    matrix = document.get('values')
    values = [v for row in matrix if isinstance(row, (list, tuple)) for v in row] if isinstance(matrix, (list, tuple)) else []
    _missing(audit, path, values)
    finite = [v for v in values if finite_number(v)]
    audit.metric(path, 'value_summary', dict(valid_count=len(finite), nodata_count=sum(v is None for v in values),
                 invalid_count=sum(v is not None and not finite_number(v) for v in values),
                 minimum=min(finite) if finite else None, maximum=max(finite) if finite else None))
    for field in ('rows', 'cols', 'units', 'raw_checksum', 'product', 'product_version',
                  'observed_at', 'available_at', 'source_uri'):
        value = document.get(field)
        if value is None or isinstance(value, str) or type(value) is int and finite_number(value):
            audit.metric(path, field, value)
    audit.metric(path, 'grid_checksum', _hash({k:v for k,v in document.items() if k != 'checksum'}))


def _alignment(audit, source, registry, grids):
    document = _doc(source)
    if not _base(audit, document, 'alignment'):
        return None
    audit.check(document.get('alignment_version') == ALIGNMENT_VERSION, 'VERSION_MISMATCH', 'alignment', 'Alignment version differs')
    audit.check(document.get('network_version') == registry.network_version and
                document.get('registry_checksum') == registry.checksum,
                'CHECKSUM_MISMATCH', 'alignment', 'Registry lineage differs')
    seen, groups = set(), defaultdict(list)
    grid_lookup = {_hash(_doc(grid)): _doc(grid) for grid in grids}
    for kind in ('static', 'dynamic'):
        records = document.get(kind)
        if not audit.check(isinstance(records, list), 'ALIGNMENT_INVALID', 'alignment/'+kind, 'Expected records list'):
            continue
        for record in records:
            if not isinstance(record, dict):
                audit.issue('ALIGNMENT_INVALID', 'alignment/'+kind, 'Expected record object')
                continue
            path = 'alignment/'+kind+'/'+str(record.get('road_id'))+'/'+str(record.get('timestamp'))
            digest = _hash({field:record.get(field) for field in
                           ('road_id','source_type','variable','timestamp','as_of','grid_checksum')})
            audit.check(digest is None or digest not in seen, 'DUPLICATE_ALIGNED_RECORD', path, 'Repeated aligned record')
            if digest:
                seen.add(digest)
            try:
                _validate_record(record, registry, kind == 'static')
            except (ValueError, TypeError, KeyError, AttributeError):
                audit.issue('ALIGNMENT_INVALID', path, 'Aligned contract/provenance validation failed')
            value = record.get('value')
            grid = grid_lookup.get(record.get('grid_checksum'))
            if grid is not None:
                for field in ('raw_checksum','product','product_version','source_uri','units','variable'):
                    audit.check(record.get(field)==grid.get(field),'PROVENANCE_MISMATCH',path,
                                'Aligned source '+field+' differs from grid')
                row,col=record.get('grid_row'),record.get('grid_col')
                matrix=grid.get('values',[])
                if type(row) is int and type(col) is int and 0<=row<len(matrix) and isinstance(matrix[row],list) and 0<=col<len(matrix[row]):
                    original=matrix[row][col]
                    if value is not None:
                        audit.check(value==original,'ALIGNMENT_VALUE_MISMATCH',path,
                                    'Aligned value differs from source cell; possible silent filling')
                    if record.get('missing_reason')=='GRID_NODATA':
                        audit.check(original is None,'MISSING_REASON_MISMATCH',path,'GRID_NODATA contradicts source cell')
                elif value is not None:
                    audit.issue('ALIGNMENT_INVALID',path,'Usable value has no valid source cell index')
            elif value is not None:
                audit.issue('LINEAGE_NOT_VERIFIED' if not grids else 'CHECKSUM_MISMATCH',path,
                            'No source grid evidence for selected cell','WARNING' if not grids else 'ERROR')
            for label in ('variable', 'source_type', 'road_id'):
                groups[label+'/'+str(record.get(label))].append(value)
            if kind == 'dynamic':
                target = _time_check(audit, record.get('timestamp'), path)
                as_of = _time_check(audit, record.get('as_of'), path, False)
                if target and as_of:
                    audit.check(as_of >= target, 'FEATURE_LEAKAGE', path, 'as_of precedes target timestamp')
                if value is not None:
                    available = _time_check(audit, record.get('source_available_at'), path, False)
                    observed = _time_check(audit, record.get('source_observed_at'), path, False)
                    if as_of and available:
                        audit.check(available <= as_of, 'FEATURE_LEAKAGE', path, 'Source available after as_of')
                    if target and observed:
                        audit.check(observed <= target, 'FEATURE_LEAKAGE', path, 'Future source observation')
    for group, values in sorted(groups.items()):
        _missing(audit, 'alignment/'+group, values)
    return document


def _feature_objects(audit, rows, registry, alignment, issue_time):
    documents, objects, seen = [], [], set()
    context = _time_check(audit, issue_time, 'features/issue_time') if issue_time is not None else None
    groups = defaultdict(list)
    for source in rows:
        record = _doc(source)
        if not _base(audit, record, 'features'):
            continue
        documents.append(record)
        key = (record.get('road_id'), record.get('timestamp'))
        path = 'features/'+str(key[0])+'/'+str(key[1])
        audit.check(key not in seen, 'DUPLICATE_FEATURE_ROW', path, 'Repeated road/timestamp')
        seen.add(key)
        audit.check(record.get('feature_version') == FEATURE_VERSION, 'VERSION_MISMATCH', path, 'Feature version differs')
        audit.check(record.get('network_version') == registry.network_version and registry.get(key[0]) is not None,
                    'REGISTRY_MISMATCH', path, 'Feature road/network differs')
        target = _time_check(audit, key[1], path)
        as_of = _time_check(audit, record.get('as_of'), path, False)
        if context and as_of:
            audit.check(as_of <= context, 'FEATURE_LEAKAGE', path, 'Feature as_of after forecast issue time')
        features, mask, reasons = (record.get(k) for k in ('features','mask','missing_reasons'))
        if not audit.check(all(isinstance(d, dict) and set(d) == set(FEATURE_NAMES) for d in (features,mask,reasons)),
                           'FEATURE_SHAPE', path, 'Expected six named features/masks/reasons'):
            continue
        audit.check(all(type(mask[n]) is bool and mask[n] == (features[n] is not None) for n in FEATURE_NAMES),
                    'MASK_MISMATCH', path, 'Feature mask contradicts null values')
        for name in FEATURE_NAMES:
            groups[name].append(features[name])
        try:
            row = RoadFeatureRow(key[0], record['network_version'], key[1], record['as_of'],
                                 tuple(features[n] for n in FEATURE_NAMES),
                                 tuple(reasons[n] for n in FEATURE_NAMES), record['provenance'])
            audit.check(row.provenance.get('registry_checksum') == registry.checksum,
                        'CHECKSUM_MISMATCH', path, 'Feature registry fingerprint differs')
            objects.append(row)
        except (ValueError, TypeError, KeyError, AttributeError):
            audit.issue('FEATURE_INVALID', path, 'Feature model validation failed')
    for name, values in sorted(groups.items()):
        _missing(audit, 'features/'+name, values)
    if alignment is None:
        audit.issue('LINEAGE_NOT_VERIFIED', 'features', 'Supply aligned records to verify availability and derived rain', 'WARNING')
    else:
        expected = {}
        for cutoff in sorted({row.as_of for row in objects}):
            try:
                expected[cutoff] = {(row.road_id,row.timestamp): row for row in build_features(registry,alignment,as_of=cutoff)}
            except (ValueError, TypeError, KeyError, AttributeError):
                audit.issue('LINEAGE_INVALID', 'features', 'Cannot rebuild reference features from supplied alignment')
        for row in objects:
            path = 'features/'+row.road_id+'/'+row.timestamp
            reference = expected.get(row.as_of,{}).get((row.road_id,row.timestamp))
            if reference is None:
                audit.issue('LINEAGE_INVALID', path, 'No matching reference feature row')
                continue
            for i,name in enumerate(FEATURE_NAMES):
                if row.values[i] != reference.values[i]:
                    code = 'DERIVED_RAIN_MISMATCH' if i in (1,2,3) else 'FEATURE_VALUE_MISMATCH'
                    if reference.values[i] is None and row.values[i] is not None:
                        if any(term in (reference.missing_reasons[i] or '') for term in ('AS_OF','FUTURE','AVAILABLE')):
                            code = 'FEATURE_LEAKAGE'
                    audit.issue(code, path+'/'+name, 'Feature differs from exact same-as_of source reconstruction')
            audit.check(row.to_dict()['provenance'] == reference.to_dict()['provenance'],
                        'PROVENANCE_MISMATCH', path, 'Feature lineage differs from source reconstruction')
    return documents, objects


def _graph(audit, source, registry):
    document = _doc(source)
    if not _base(audit, document, 'graph'):
        return None
    expected = build_graph(registry).to_dict()
    for field in ('graph_version','network_version','registry_checksum','road_ids'):
        audit.check(document.get(field) == expected[field], 'GRAPH_METADATA_MISMATCH', 'graph', field+' differs')
    n = len(registry)
    matrix = document.get('adjacency')
    valid_shape = isinstance(matrix,list) and len(matrix)==n and all(isinstance(row,list) and len(row)==n for row in matrix)
    audit.check(valid_shape, 'GRAPH_SHAPE', 'graph', 'Expected N x N adjacency')
    if valid_shape:
        audit.check(all(type(v) is int and v in (0,1) for row in matrix for v in row),
                    'GRAPH_VALUE', 'graph', 'Adjacency must contain integer 0/1')
        audit.check(all(matrix[i][i] == 0 for i in range(n)), 'GRAPH_SELF_LOOP', 'graph', 'V1 diagonal must be zero')
        edges = sum(v == 1 for row in matrix for v in row)
        isolated = sum(not any(matrix[i]) and not any(row[i] for row in matrix) for i in range(n))
        audit.metric('graph','summary',dict(road_count=n,directed_edge_count=edges,isolated_node_count=isolated,
                                          density=edges/(n*(n-1)) if n>1 else 0))
        if isolated:
            audit.issue('ISOLATED_NODES','graph','Isolated nodes are a limitation, not automatically invalid','WARNING')
    audit.check(document.get('adjacency') == expected['adjacency'] and document.get('directed_edges') == expected['directed_edges'],
                'GRAPH_CONNECTIVITY', 'graph', 'Adjacency/edges differ from registry travel connectivity')
    return document


def _shape(value, dimensions):
    if not dimensions:
        return True
    return isinstance(value,(list,tuple)) and len(value)==dimensions[0] and all(_shape(v,dimensions[1:]) for v in value)


def _dataset(audit, source, registry, graph, rows, labels):
    document = _doc(source)
    if not _base(audit,document,'dataset'):
        return None
    expected_graph = build_graph(registry).to_dict()
    for field, expected in (('schema',DATASET_SCHEMA),('feature_version',FEATURE_VERSION),
                           ('network_version',registry.network_version),('timestep_minutes',30),
                           ('road_ids',expected_graph['road_ids']),('feature_names',list(FEATURE_NAMES)),
                           ('feature_units',list(FEATURE_UNITS))):
        audit.check(document.get(field)==expected,'DATASET_METADATA','dataset',field+' differs')
    names = document.get('feature_names',[])
    audit.check(not isinstance(names,list) or document.get('target_name') not in names,
                'TARGET_LEAKAGE','dataset','Target included among input feature names')
    audit.check(document.get('graph_checksum') == _hash(expected_graph) and document.get('graph') == expected_graph,
                'CHECKSUM_MISMATCH','dataset','Graph fingerprint/payload differs from registry')
    if graph is not None:
        audit.check(document.get('graph_checksum') == _hash({k:v for k,v in graph.items() if k!='checksum'}),
                    'CHECKSUM_MISMATCH','dataset','Supplied graph and dataset disagree')
    lookback,horizon = document.get('lookback_steps'),document.get('horizon_steps')
    if not audit.check(type(lookback) is int and lookback>0 and type(horizon) is int and horizon>0,
                       'DATASET_CONFIG','dataset','Positive integer lookback/horizon required'):
        return document
    samples = document.get('samples')
    if not audit.check(isinstance(samples,list),'DATASET_SHAPE','dataset','samples must be a list'):
        return document
    row_lookup = {_hash(r.to_dict()): r for r in rows}
    label_lookup = {_hash(_doc(label)): _doc(label) for label in labels} if labels is not None else None
    seen = set()
    n,f = len(registry),len(FEATURE_NAMES)
    for sample in samples:
        if not isinstance(sample,dict):
            audit.issue('SAMPLE_SHAPE','dataset','Sample must be an object'); continue
        path='dataset/sample/'+str(sample.get('issue_time'))
        identity=(sample.get('issue_time'),sample.get('target_time'))
        audit.check(identity not in seen,'DUPLICATE_SAMPLE',path,'Duplicate issue/target sample')
        seen.add(identity)
        issue=_time_check(audit,sample.get('issue_time'),path)
        target=_time_check(audit,sample.get('target_time'),path)
        if issue and target:
            audit.check(target>issue,'TARGET_LEAKAGE',path,'Target must be strictly after issue')
            audit.check(sample['target_time']==shift(sample['issue_time'],horizon),'HORIZON_MISMATCH',path,'Target shift differs')
            audit.check(sample.get('history_timestamps') == [shift(sample['issue_time'],o) for o in range(1-lookback,1)],
                        'HISTORY_GAP',path,'History timestamps are not contiguous bin ends')
        valid = True
        for field,dims in (('X',(lookback,n,f)),('X_mask',(lookback,n,f)),('y',(n,)),('y_mask',(n,)),
                           ('feature_as_of',(lookback,n)),('feature_row_checksums',(lookback,n)),
                           ('label_available_at',(n,)),('label_checksums',(n,))):
            valid = audit.check(_shape(sample.get(field),dims),'SAMPLE_SHAPE',path,field+' shape differs') and valid
        if not valid:
            continue
        for t in range(lookback):
            for r in range(n):
                values,masks=sample['X'][t][r],sample['X_mask'][t][r]
                audit.check(all(v is None or finite_number(v) for v in values),'NONFINITE_VALUE',path,'Invalid X numeric value')
                audit.check(all(type(m) is bool and m==(v is not None) for v,m in zip(values,masks)),
                            'MASK_MISMATCH',path,'X mask contradicts null')
                cutoff=_time_check(audit,sample['feature_as_of'][t][r],path,False)
                if issue and cutoff:
                    audit.check(cutoff<=issue,'FEATURE_LEAKAGE',path,'Feature snapshot after issue')
                ref=sample['feature_row_checksums'][t][r]
                reference=row_lookup.get(ref)
                if reference is None:
                    audit.issue('LINEAGE_NOT_VERIFIED' if not rows else 'CHECKSUM_MISMATCH',path,
                                'No matching feature row evidence','WARNING' if not rows else 'ERROR')
                else:
                    audit.check(reference.road_id==expected_graph['road_ids'][r] and
                                t<len(sample.get('history_timestamps',[])) and
                                reference.timestamp==sample['history_timestamps'][t] and
                                reference.as_of==sample['feature_as_of'][t][r],
                                'FEATURE_LEAKAGE',path,'Feature row identity/time reference differs')
                    if list(reference.values)!=values:
                        # Equality to a label alone is not leakage: require mismatch to known X evidence.
                        injected=any(v is not None and v!=expected and v in sample['y']
                                     for v,expected in zip(values,reference.values))
                        audit.issue('TARGET_LEAKAGE' if injected else 'FEATURE_VALUE_MISMATCH',path,
                                    'X differs from referenced feature row')
        audit.check(all(v is None or finite_number(v) for v in sample['y']),'NONFINITE_VALUE',path,'Invalid y value')
        audit.check(all(type(m) is bool and m==(v is not None) for v,m in zip(sample['y'],sample['y_mask'])),
                    'MASK_MISMATCH',path,'y mask contradicts null')
        if document.get('require_targets'):
            audit.check(all(sample['y_mask']),'TARGET_MISSING',path,'Required target missing')
        for r,(value,available,refs) in enumerate(zip(sample['y'],sample['label_available_at'],sample['label_checksums'])):
            if value is None:
                continue
            when=_time_check(audit,available,path,False)
            if when and target:
                audit.check(when>=target,'INVALID_TIMESTAMP',path,'Label availability precedes observation')
            if label_lookup is not None:
                references=[label_lookup.get(ref) for ref in refs] if isinstance(refs,list) else []
                audit.check(len(references)==1 and references[0] is not None and
                            references[0].get('road_id')==expected_graph['road_ids'][r] and
                            references[0].get('observed_at')==sample.get('target_time') and
                            references[0].get('available_at')==available and
                            references[0].get('target_name')==document.get('target_name') and
                            references[0].get('value')==value,
                            'TARGET_PROVENANCE',path,'Target differs from supplied label evidence')
    audit.metric('dataset','sample_count',len(samples))
    audit.metric('dataset','dataset_checksum',_hash({k:v for k,v in document.items() if k!='checksum'}))
    if not samples:
        audit.issue('EMPTY_DATASET','dataset','No eligible forecast samples','WARNING')
    if labels is None:
        audit.issue('LINEAGE_NOT_VERIFIED','dataset','Supply labels to verify target provenance','WARNING')
    return document


def _split(audit, source, dataset):
    document=_doc(source)
    if not _base(audit,document,'split'):
        return
    audit.check(document.get('split_version')=='chronological-target-blocks-v1','VERSION_MISMATCH','split','Split version differs')
    ratios=document.get('requested_ratios')
    valid_ratios=isinstance(ratios,dict) and set(ratios)=={'train','validation','test'} and all(
        finite_number(value) and 0<=value<=1 for value in ratios.values())
    audit.check(valid_ratios and math.isclose(sum(ratios.values()),1,rel_tol=0,abs_tol=1e-9),
                'SPLIT_CONFIG','split','Ratios must be finite and sum to one')
    audit.check(type(document.get('preserve_events')) is bool and type(document.get('purge_overlap')) is bool,
                'SPLIT_CONFIG','split','Policy flags must be boolean')
    if dataset is None:
        audit.issue('LINEAGE_NOT_VERIFIED','split','Supply dataset to verify sample references and purge','WARNING')
        lookup={}
    else:
        audit.check(document.get('dataset_checksum')==_hash({k:v for k,v in dataset.items() if k!='checksum'}),
                    'CHECKSUM_MISMATCH','split','Dataset fingerprint differs')
        lookup={_hash(s):s for s in dataset.get('samples',[]) if isinstance(s,dict)}
    seen,events=set(),{}
    previous=None
    for name in ('train','validation','test'):
        part=document.get(name)
        if not audit.check(isinstance(part,list),'SPLIT_SHAPE','split/'+name,'Expected partition list'):
            continue
        if not part:
            audit.issue('EMPTY_SPLIT','split/'+name,'Empty partition may follow grouping/purge policy','WARNING')
        order=[]
        for item in part:
            if not isinstance(item,dict):
                audit.issue('SPLIT_SHAPE','split/'+name,'Expected sample reference'); continue
            ref=item.get('sample_checksum')
            audit.check(ref not in seen,'SPLIT_DUPLICATE','split/'+name,'Sample repeated across/within partitions')
            seen.add(ref)
            target=_time_check(audit,item.get('target_time'),'split/'+name)
            issue=_time_check(audit,item.get('issue_time'),'split/'+name)
            if target and issue:
                order.append((target,issue))
                if previous:
                    audit.check(target>=previous,'SPLIT_CHRONOLOGY','split/'+name,'Later split precedes earlier split')
            actual=lookup.get(ref)
            if dataset is not None:
                audit.check(actual is not None and actual.get('issue_time')==item.get('issue_time') and
                            actual.get('target_time')==item.get('target_time') and actual.get('event_ids')==item.get('event_ids'),
                            'CHECKSUM_MISMATCH','split/'+name,'Sample reference differs from dataset')
            if actual and previous and document.get('purge_overlap'):
                history=actual.get('history_timestamps',[])
                if history:
                    try:
                        audit.check(dt(history[0])>previous,'SPLIT_OVERLAP','split/'+name,'History touches previous target block')
                    except (ValueError,TypeError):
                        audit.issue('INVALID_TIMESTAMP','split/'+name,'Invalid history timestamp')
            if document.get('preserve_events'):
                for event in item.get('event_ids',[]):
                    audit.check(event not in events or events[event]==name,'EVENT_SPLIT','split/'+name,'Event crosses partitions')
                    events[event]=name
        audit.check(order==sorted(order),'SPLIT_CHRONOLOGY','split/'+name,'Partition order is not chronological')
        if order:
            previous=max(previous,max(t for t,_ in order)) if previous else max(t for t,_ in order)
    audit.metric('split','retained_sample_count',len(seen))


def audit_artifacts(registry, *, grids=(), alignment=None, feature_rows=None, graph=None,
                    dataset=None, split=None, labels=None, issue_time=None):
    """Audit supplied artifacts read-only. Omitted stages are not claimed validated.

    Supply original alignment/feature rows/labels for source and target verification.
    Numeric equality of y and a valid X value by itself is never treated as leakage.
    """
    audit=_Audit()
    validated=_safe(audit,'registry',_registry,registry)
    grid_sources=tuple(grids)
    for grid in grid_sources:
        _safe(audit,'environment',_grid,grid)
    if validated is None:
        audit.issue('DEPENDENT_AUDIT_SKIPPED','registry','Invalid registry prevents dependent checks','WARNING')
        return audit.finish()
    aligned=_safe(audit,'alignment',_alignment,alignment,validated,grid_sources) if alignment is not None else None
    rows=[]
    if feature_rows is not None:
        result=_safe(audit,'features',_feature_objects,feature_rows,validated,aligned,issue_time)
        if result is not None:
            _,rows=result
    graph_doc=_safe(audit,'graph',_graph,graph,validated) if graph is not None else None
    label_list=tuple(labels) if labels is not None else None
    if label_list is not None:
        for label in label_list:
            document=_doc(label)
            if _base(audit,document,'labels'):
                try:
                    value=RoadTarget(**document)
                    if validated.get(value.road_id) is None:
                        raise ValueError('Unknown road')
                except (ValueError,TypeError,KeyError):
                    audit.issue('TARGET_PROVENANCE','labels','Invalid supervised target')
    dataset_doc=_safe(audit,'dataset',_dataset,dataset,validated,graph_doc,rows,label_list) if dataset is not None else None
    if split is not None:
        _safe(audit,'split',_split,split,dataset_doc)
    return audit.finish()


def main(argv=None):
    """Optional offline fixture audit CLI; imports and --help perform no pipeline work."""
    import argparse
    parser=argparse.ArgumentParser(description='Read-only Data Module quality audit, offline fixtures only')
    parser.add_argument('--fixture-demo',action='store_true')
    args=parser.parse_args(argv)
    if not args.fixture_demo:
        parser.print_help()
        return 0
    from .end_to_end import run_fixture_pipeline
    result=run_fixture_pipeline()
    print(result.to_json(),end='')
    return 1 if result.to_dict()['errors'] else 0


if __name__=='__main__':
    raise SystemExit(main())
