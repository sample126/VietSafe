"""Directed road-as-node connectivity, not a routing graph with turn restrictions."""

from dataclasses import dataclass

from ..registry import checksum

GRAPH_VERSION = 'road-connectivity-v1'


def travel_endpoints(road):
    """DATA-03 endpoints are canonical; reverse means b -> a, not a -> b."""
    if road.directionality == 'forward':
        return ((road.endpoint_a, road.endpoint_b),)
    if road.directionality == 'reverse':
        return ((road.endpoint_b, road.endpoint_a),)
    if road.directionality == 'both':
        return ((road.endpoint_a, road.endpoint_b), (road.endpoint_b, road.endpoint_a))
    raise ValueError('Unsupported road directionality')


@dataclass(frozen=True)
class GraphTopology:
    network_version: str
    registry_checksum: str
    road_ids: tuple
    edges: tuple
    adjacency: tuple

    def to_dict(self):
        return dict(graph_version=GRAPH_VERSION, network_version=self.network_version,
                    registry_checksum=self.registry_checksum, road_ids=list(self.road_ids),
                    directed_edges=[list(edge) for edge in self.edges],
                    adjacency=[list(row) for row in self.adjacency],
                    policy='raw-travel-continuity-no-self-loops-uturns-allowed-v1')

    def checksum(self):
        return checksum(self.to_dict())


def build_graph(registry):
    roads = sorted(registry, key=lambda road: road.road_id)
    starts = {}
    for index, road in enumerate(roads):
        for start, _ in travel_endpoints(road):
            starts.setdefault(start, set()).add(index)
    edges = set()
    for index, road in enumerate(roads):
        for _, end in travel_endpoints(road):
            for other in starts.get(end, ()):
                if index != other:
                    edges.add((index, other))
    adjacency = tuple(tuple(int((i, j) in edges) for j in range(len(roads))) for i in range(len(roads)))
    return GraphTopology(registry.network_version, registry.checksum,
                         tuple(road.road_id for road in roads), tuple(sorted(edges)), adjacency)
