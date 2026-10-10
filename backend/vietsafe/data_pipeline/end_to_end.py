"""Deterministic offline fixture validation; no work runs on import."""

import json
from dataclasses import dataclass
from pathlib import Path

from .audit import audit_artifacts
from .features.dataset import build_dataset
from .features.engineering import FEATURE_VERSION, build_features, shift
from .features.graph import build_graph
from .features.labels import RoadTarget
from .features.split import chronological_split
from .ingestion.dem import read_hgt
from .ingestion.gpm import read_gpm
from .ingestion.osm import read_overpass
from .ingestion.smap import read_smap
from .processing.alignment import align_environment
from .processing.osm_network import build_road_network
from .registry import RoadRegistry, canonical_bytes, checksum


@dataclass(frozen=True)
class EndToEndResult:
    _json: str

    def to_dict(self):
        return json.loads(self._json)

    def to_json(self):
        return self._json

    def checksum(self):
        return checksum(self.to_dict())


def build_fixture_artifacts(fixture_root=None, *, reverse_inputs=False):
    """Reuse existing fixtures; make explicitly synthetic labels for OSM road IDs.

    This one-bin smoke run uses issue=observed time, so delayed GPM/SMAP are
    intentionally masked. Existing feature-series tests cover complete rain windows.
    Label values are copied from the matching synthetic label time for every OSM
    road, not measured/geo-matched flood truth. No source file is changed or written.
    """
    root=Path(fixture_root) if fixture_root is not None else Path(__file__).resolve().parents[3]/'data/fixtures'
    osm=read_overpass(root/'osm/overpass-small.json')
    registry=build_road_network(osm).registry
    if registry is None:
        raise ValueError('OSM fixture produced no valid roads')
    if reverse_inputs:
        registry=RoadRegistry(registry.network_version,reversed(list(registry)))
    dem=read_hgt(root/'environment/dem/N21E105-mini.hgt',product_version='fixture-v1',
                 source_uri='urn:vietsafe:fixture:dem',fixture_tile='N21E105.hgt')
    gpm=read_gpm(root/'alignment/gpm-alignment-grid.json')
    smap=read_smap(root/'alignment/smap-alignment-grid.json')
    issue=gpm.observed_at
    aligned=align_environment(registry,dem=dem,gpm=[gpm],smap=[smap],targets=[(issue,issue)])
    rows=build_features(registry,aligned,as_of=issue)
    graph=build_graph(registry)
    fixture=json.loads((root/'features/labels.json').read_text(encoding='utf-8'))
    notice='SYNTHETIC TEST FIXTURE — NOT PRODUCTION FLOOD GROUND TRUTH'
    if fixture.get('fixture_notice') != notice:
        raise ValueError('Synthetic label fixture notice missing')
    target=shift(issue,1)
    templates=sorted((label for label in fixture['labels'] if label['observed_at']==target),key=canonical_bytes)
    if not templates:
        raise ValueError('Synthetic label fixture has no matching target timestamp')
    template=templates[0]
    labels=tuple(RoadTarget(road.road_id,target,template['available_at'],template['target_name'],
                           template['value'],template['units'],
                           dict(data_kind='synthetic',fixture_notice=notice,
                                source_uri='urn:vietsafe:fixture:quality:remapped-label-template',
                                template_checksum=checksum(template),
                                policy='copy-synthetic-template-value-to-each-osm-road-not-ground-truth'),
                           template['event_id']) for road in registry)
    if reverse_inputs:
        rows=tuple(reversed(rows))
        labels=tuple(reversed(labels))
    dataset=build_dataset(registry,rows,labels,target_name=template['target_name'],lookback_steps=1,
                          horizon_steps=1,issue_times=[issue],require_targets=True)
    split=chronological_split(dataset)
    grids=(smap,gpm,dem) if reverse_inputs else (dem,gpm,smap)
    return dict(registry=registry,grids=grids,alignment=aligned,feature_rows=rows,
                graph=graph,dataset=dataset,split=split,labels=labels)


def run_fixture_pipeline(fixture_root=None, *, reverse_inputs=False):
    """Run fixture stages and audit in memory; return hashes, report and limitations."""
    artifacts=build_fixture_artifacts(fixture_root,reverse_inputs=reverse_inputs)
    report=audit_artifacts(**artifacts)
    document=report.to_dict()
    features=sorted((row.to_dict() for row in artifacts['feature_rows']),key=canonical_bytes)
    summary=dict(network_version=artifacts['registry'].network_version,
                 registry_checksum=artifacts['registry'].checksum,road_count=len(artifacts['registry']),
                 alignment_checksum=artifacts['alignment'].checksum(),feature_version=FEATURE_VERSION,
                 feature_checksum=checksum(features),graph_checksum=artifacts['graph'].checksum(),
                 dataset_checksum=artifacts['dataset'].checksum(),split_checksum=artifacts['split'].checksum(),
                 quality_checksum=report.checksum(),errors=document['errors'],warnings=document['warnings'],
                 quality_report=document,fixture_only=True,
                 limitations=['one-bin smoke run; full history covered by feature-series tests',
                              'delayed dynamic sources intentionally unavailable at issue time',
                              'remapped labels are synthetic, not production ground truth'])
    return EndToEndResult(canonical_bytes(summary).decode('utf-8'))
