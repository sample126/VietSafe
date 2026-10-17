"""Extract major OSM roads near Hanoi from a Geofabrik Vietnam PBF.

Requires pyosmium for this one-off build. The running app uses only the JSON output.
"""

import json
import gzip
import math
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import osmium


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "backend" / "vietsafe" / "core" / "hanoi_major_roads.json"
GRAPH_OUTPUT = ROOT / "backend" / "vietsafe" / "core" / "hanoi_routing_graph.json.gz"
SOURCE = "https://download.geofabrik.de/asia/vietnam-latest.osm.pbf"
BOUNDS = (20.58, 105.27, 21.36, 106.08)
CLASSES = ("motorway", "trunk", "primary", "secondary", "tertiary")
WALK_CLASSES = {"footway", "pedestrian", "path", "steps", "living_street"}
DRIVE_CLASSES = set(CLASSES) | {"unclassified", "residential", "living_street", "service"}
DENIED = {"no", "private"}


def access_flags(tags, kind):
    general = tags.get("access", "yes")
    vehicle = tags.get("vehicle", general)
    motor = tags.get("motor_vehicle", vehicle)
    car = tags.get("motorcar", motor)
    bike = tags.get("motorcycle", motor)
    foot = tags.get("foot", general)
    if kind == "service" and tags.get("service") in {"parking_aisle", "driveway", "private"}:
        return 0, 0
    forward = backward = 0
    if kind in DRIVE_CLASSES and kind not in {"motorway", "trunk"} and bike not in DENIED:
        forward |= 1
        backward |= 1
    if kind in DRIVE_CLASSES and car not in DENIED:
        forward |= 2
        backward |= 2
    if kind != "motorway" and kind != "trunk" and (kind in DRIVE_CLASSES or kind in WALK_CLASSES) and foot not in DENIED:
        forward |= 4
        backward |= 4
    oneway = tags.get("oneway", "")
    if kind in {"motorway", "motorway_link"} and not oneway:
        oneway = "yes"
    if oneway in {"yes", "1", "true", "-1"}:
        if oneway == "-1":
            forward &= ~3
        else:
            backward &= ~3
    foot_oneway = tags.get("oneway:foot", "")
    if foot_oneway in {"yes", "1", "true"}:
        backward &= ~4
    elif foot_oneway == "-1":
        forward &= ~4
    return forward, backward


class MajorRoads(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.lines = {kind: [] for kind in CLASSES}
        self.count = 0
        self.nodes = {}
        self.edges = []
        self.names = []
        self.name_ids = {}

    def node_index(self, node):
        if node.ref not in self.nodes:
            self.nodes[node.ref] = [len(self.nodes), round(node.lat, 6), round(node.lon, 6)]
        return self.nodes[node.ref][0]

    def way(self, way):
        kind = way.tags.get("highway")
        if kind not in self.lines and kind not in DRIVE_CLASSES and kind not in WALK_CLASSES:
            return
        points = [(round(node.lat, 5), round(node.lon, 5)) for node in way.nodes if node.location.valid()]
        if len(points) < 2 or not any(
            BOUNDS[0] <= lat <= BOUNDS[2] and BOUNDS[1] <= lng <= BOUNDS[3]
            for lat, lng in points
        ):
            return
        if kind not in self.lines:
            self.add_graph(way, kind)
            return
        self.add_graph(way, kind)
        # OSM way coordinates already follow the road; dropping near-collinear points keeps the static layer small.
        shape = [points[0]]
        for point in points[1:-1]:
            previous = shape[-1]
            if abs(point[0] - previous[0]) + abs(point[1] - previous[1]) >= 0.00006:
                shape.append(point)
        shape.append(points[-1])
        if len(set(shape)) < 2:
            return
        self.lines[kind].append(shape)
        self.count += 1

    def add_graph(self, way, kind):
        forward, backward = access_flags(way.tags, kind)
        if not (forward or backward):
            return
        name = way.tags.get("name:vi") or way.tags.get("name") or kind
        if name not in self.name_ids:
            self.name_ids[name] = len(self.names)
            self.names.append(name)
        name_id = self.name_ids[name]
        for a, b in zip(way.nodes, list(way.nodes)[1:]):
            if not a.location.valid() or not b.location.valid():
                continue
            if not all(BOUNDS[0] <= n.lat <= BOUNDS[2] and BOUNDS[1] <= n.lon <= BOUNDS[3] for n in (a, b)):
                continue
            lat = math.radians((a.lat + b.lat) / 2)
            km = 111.195 * math.hypot(b.lat - a.lat, (b.lon - a.lon) * math.cos(lat))
            if km < 0.0001:
                continue
            self.edges.append([self.node_index(a), self.node_index(b), round(km, 5), forward, backward, name_id, kind])


def main():
    handler = MajorRoads()
    with tempfile.TemporaryDirectory(prefix="vietsafe-osm-") as tempdir:
        source = Path(tempdir) / "vietnam.osm.pbf"
        request = urllib.request.Request(SOURCE, headers={"User-Agent": "VietSafeDemo/1.0 static-hanoi-road-extract"})
        with urllib.request.urlopen(request, timeout=90) as response, source.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
            print(f"Downloaded {source.stat().st_size // 1024 // 1024} MB", flush=True)
        handler.apply_file(str(source), locations=True)
    data = {
        "source": "OpenStreetMap contributors via Geofabrik Vietnam extract",
        "bbox": BOUNDS,
        "classes": handler.lines,
    }
    pending = OUTPUT.with_suffix(".json.tmp")
    pending.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    pending.replace(OUTPUT)
    graph = {
        "source": "OpenStreetMap contributors via Geofabrik Vietnam extract",
        "bbox": BOUNDS,
        "nodes": [[row[1], row[2]] for row in sorted(handler.nodes.values())],
        "edges": handler.edges,
        "names": handler.names,
    }
    with gzip.open(GRAPH_OUTPUT, "wt", encoding="utf-8", compresslevel=6) as output:
        json.dump(graph, output, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {handler.count} road ways to {OUTPUT}", flush=True)
    print(f"Wrote {len(handler.nodes)} nodes and {len(handler.edges)} graph edges to {GRAPH_OUTPUT}", flush=True)
    for kind, shapes in handler.lines.items():
        print(f"{kind}: {len(shapes)}", flush=True)
    env = {**os.environ, "PYTHONPATH": str(ROOT / "backend")}
    subprocess.run([sys.executable, str(ROOT / "scripts" / "prune-hanoi-routing-graph.py")], check=True, env=env)


if __name__ == "__main__":
    main()
