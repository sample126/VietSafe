"""Keep the OSM street graph near VietSafe's covered demo corridors."""

import gzip
import json
import math
from pathlib import Path

from vietsafe.core.network import ROADS
from vietsafe.core.osm_graph import _hazard_samples, _nearest_hazard

SOURCE = Path(__file__).resolve().parents[1] / "backend" / "vietsafe" / "core" / "hanoi_routing_graph.json.gz"
SEARCH = SOURCE.with_name("hanoi_street_search.json")
CELL = 0.004
MAIN = {"motorway", "trunk", "primary", "secondary", "tertiary"}


def cell(lat, lng):
    return int(lat // CELL), int(lng // CELL)


def main():
    covered = set()
    for road in ROADS:
        for a, b in zip(road["coordinates"], road["coordinates"][1:]):
            steps = max(1, math.ceil(max(abs(a[0] - b[0]), abs(a[1] - b[1])) / CELL))
            for n in range(steps + 1):
                y, x = cell(a[0] + (b[0] - a[0]) * n / steps, a[1] + (b[1] - a[1]) * n / steps)
                for dy in range(-3, 4):
                    for dx in range(-3, 4):
                        covered.add((y + dy, x + dx))
    with gzip.open(SOURCE, "rt", encoding="utf-8") as stream:
        graph = json.load(stream)
    nodes = graph["nodes"]
    keep = []
    used = set()
    for edge in graph["edges"]:
        a, b = edge[:2]
        ay, ax = nodes[a]
        by, bx = nodes[b]
        if edge[6] not in MAIN and cell((ay + by) / 2, (ax + bx) / 2) not in covered:
            continue
        keep.append(edge)
        used.add(a)
        used.add(b)
    remap = {old: new for new, old in enumerate(sorted(used))}
    graph["nodes"] = [nodes[old] for old in sorted(used)]
    graph["edges"] = [[remap[e[0]], remap[e[1]], *e[2:7]] for e in keep]
    graph["coverage"] = "OSM ways within approximately 1.5 km of VietSafe demo corridors"
    samples = _hazard_samples()
    for edge in graph["edges"]:
        ay, ax = graph["nodes"][edge[0]]
        by, bx = graph["nodes"][edge[1]]
        edge.append(_nearest_hazard((ay + by) / 2, (ax + bx) / 2, samples))
    streets = {}
    unnamed = MAIN | {"unclassified", "residential", "living_street", "service", "footway", "path", "pedestrian", "steps"}
    for edge in keep:
        name = graph["names"][edge[5]]
        if name in unnamed or name in streets:
            continue
        lat, lng = nodes[edge[0]]
        streets[name] = [lat, lng]
    SEARCH.write_text(json.dumps([[name, *point] for name, point in streets.items()], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    pending = SOURCE.with_suffix(".pruned.gz")
    with gzip.open(pending, "wt", encoding="utf-8", compresslevel=6) as stream:
        json.dump(graph, stream, ensure_ascii=False, separators=(",", ":"))
    pending.replace(SOURCE)
    print(f"Kept {len(graph['nodes'])} nodes and {len(keep)} OSM edges", flush=True)


if __name__ == "__main__":
    main()
