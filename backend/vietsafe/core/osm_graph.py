"""Locally extracted OSM road graph. Geometry and direction come from OSM node/way tags."""

import gzip
import json
import math
from collections import defaultdict
from collections import Counter
from functools import lru_cache
from pathlib import Path

from .network import ROADS, distance

GRAPH_FILE = Path(__file__).with_name("hanoi_routing_graph.json.gz")
MODE_BITS = {"motorbike": 1, "car": 2, "walk": 4}
GRID = 0.005
HAZARD_GRID = 0.0015


def cell(lat, lng, size):
    return int(lat // size), int(lng // size)


def _hazard_samples():
    cells = defaultdict(list)
    for road in ROADS:
        if not road["seed_event"]:
            continue
        for a, b in zip(road["coordinates"], road["coordinates"][1:]):
            steps = max(1, math.ceil(distance(a, b) / 0.06))
            for i in range(steps + 1):
                lat = a[0] + (b[0] - a[0]) * i / steps
                lng = a[1] + (b[1] - a[1]) * i / steps
                cells[cell(lat, lng, HAZARD_GRID)].append((lat, lng, road["id"]))
    return cells


def _nearest_hazard(lat, lng, samples):
    y, x = cell(lat, lng, HAZARD_GRID)
    best = (0.045, None)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            for sy, sx, road_id in samples.get((y + dy, x + dx), ()):
                km = distance((lat, lng), (sy, sx))
                if km < best[0]:
                    best = km, road_id
    return best[1]


@lru_cache(maxsize=1)
def load_graph():
    if not GRAPH_FILE.exists():
        raise RuntimeError("Thiếu đồ thị OSM cục bộ. Hãy tạo lại dữ liệu từ Geofabrik.")
    with gzip.open(GRAPH_FILE, "rt", encoding="utf-8") as source:
        data = json.load(source)
    nodes = data["nodes"]
    adjacency = [[] for _ in nodes]
    grid = defaultdict(list)
    for i, (lat, lng) in enumerate(nodes):
        grid[cell(lat, lng, GRID)].append(i)
    hazards = []
    for eid, edge in enumerate(data["edges"]):
        a, b, length, forward, backward, name, kind = edge[:7]
        if forward:
            adjacency[a].append((b, eid, forward))
        if backward:
            adjacency[b].append((a, eid, backward))
        hazards.append(edge[7] if len(edge) > 7 else None)
    return nodes, data["edges"], data["names"], adjacency, grid, hazards


@lru_cache(maxsize=3)
def major_component(vehicle):
    nodes, edges, _, _, _, _ = load_graph()
    parent = list(range(len(nodes)))

    def root(node):
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    bit = MODE_BITS[vehicle]
    for edge in edges:
        a, b, _, forward, backward = edge[:5]
        if not (forward | backward) & bit:
            continue
        ra, rb = root(a), root(b)
        if ra != rb:
            parent[rb] = ra
    roots = [root(node) for node in range(len(nodes))]
    biggest = Counter(roots).most_common(1)[0][0]
    return {node for node, component in enumerate(roots) if component == biggest}


def snap_point(lat, lng, vehicle, graph=None, edge_allowed=None, node_allowed=None):
    graph = graph or load_graph()
    nodes, _, _, adjacency, grid, _ = graph
    y, x = cell(lat, lng, GRID)
    bit = MODE_BITS[vehicle]
    nearest = (float("inf"), None)
    for radius in range(1, 7):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                for index in grid.get((y + dy, x + dx), ()):
                    if node_allowed is not None and index not in node_allowed:
                        continue
                    if not any(flags & bit and (edge_allowed is None or edge_allowed(eid)) for _, eid, flags in adjacency[index]):
                        continue
                    km = distance((lat, lng), nodes[index])
                    if km < nearest[0]:
                        nearest = km, index
        if nearest[0] < radius * GRID * 100:
            break
    if nearest[0] > 1.2:
        raise ValueError("Điểm chọn cách mạng đường phù hợp quá xa (>1,2 km). Hãy chọn vị trí khác.")
    return nearest[1], nearest[0]
