import unittest
from dataclasses import replace

from tests.data.feature_helpers import fixture,ROOT
from vietsafe.data_pipeline.features.graph import build_graph
from vietsafe.data_pipeline.registry import RoadRegistry
from vietsafe.data_pipeline.ingestion.osm import read_overpass
from vietsafe.data_pipeline.processing.osm_network import build_road_network


class GraphFeatureTests(unittest.TestCase):
    def test_forward_connectivity(self):
        registry,_,_=fixture()
        graph=build_graph(registry)
        self.assertEqual(graph.road_ids,('HN-001','HN-002'))
        self.assertEqual(graph.adjacency,((0,1),(0,0)))
        self.assertEqual(graph.edges,((0,1),))

    def test_reverse_endpoint_semantics(self):
        registry,_,_=fixture()
        roads=list(registry)
        roads[1]=replace(roads[1],directionality='reverse')
        graph=build_graph(RoadRegistry(registry.network_version,roads))
        self.assertEqual(graph.edges,())
        roads[0]=replace(roads[0],directionality='reverse')
        graph=build_graph(RoadRegistry(registry.network_version,roads))
        self.assertEqual(graph.edges,((1,0),))

    def test_both_directions_and_no_self_loops(self):
        registry,_,_=fixture()
        graph=build_graph(RoadRegistry(registry.network_version,[replace(r,directionality='both') for r in registry]))
        self.assertEqual(graph.adjacency,((0,1),(1,0)))

    def test_deterministic_order_and_registry_lineage(self):
        registry,_,_=fixture()
        reverse=RoadRegistry(registry.network_version,reversed(list(registry)))
        a,b=build_graph(registry),build_graph(reverse)
        self.assertEqual(a.to_dict(),b.to_dict())
        self.assertEqual(a.checksum(),b.checksum())
        self.assertEqual(a.network_version,registry.network_version)
        self.assertEqual(a.registry_checksum,registry.checksum)

    def test_osm_travel_lineage_and_matrix(self):
        built=build_road_network(read_overpass(ROOT/'osm/overpass-small.json'))
        graph=build_graph(built.registry)
        lineage=built.to_dict()['lineage']
        self.assertEqual(len(graph.road_ids),len(built.registry))
        pairs=[(i,j) for i in graph.road_ids for j in graph.road_ids if i.endswith(':f') and j==i[:-1]+'r']
        self.assertTrue(pairs)
        n=len(graph.road_ids)
        self.assertEqual(len(graph.adjacency),n)
        for i,ri in enumerate(graph.road_ids):
            self.assertEqual(len(graph.adjacency[i]),n)
            for j,rj in enumerate(graph.road_ids):
                expected=int(i!=j and lineage[ri]['travel_node_ids'][-1]==lineage[rj]['travel_node_ids'][0])
                self.assertIn(graph.adjacency[i][j],(0,1))
                self.assertEqual(graph.adjacency[i][j],expected)
