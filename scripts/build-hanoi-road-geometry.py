"""Build the checked-in Hanoi demo road shapes from OSM-based OSRM routes.

Run explicitly when refreshing the static sample. The app never calls OSRM.
"""

import argparse
import json
import math
import sys
import time
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from vietsafe.core.network import EDGE_ROWS, NODES  # noqa: E402


OUTPUT = ROOT / "backend" / "vietsafe" / "core" / "hanoi_roads_osrm.json"
BASE = "https://router.project-osrm.org/route/v1/driving/"


def fetch_route(a, b):
    url = (
        f"{BASE}{a['lng']},{a['lat']};{b['lng']},{b['lat']}"
        "?overview=full&geometries=geojson&alternatives=false"
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=35) as response:
                data = json.load(response)
            if data.get("code") != "Ok" or not data.get("routes"):
                raise ValueError(f"OSRM returned {data.get('code')}")
            route = data["routes"][0]
            coordinates = [
                [round(lat, 5), round(lng, 5)]
                for lng, lat in route["geometry"]["coordinates"]
            ]
            if len(coordinates) < 2:
                raise ValueError("route has fewer than two points")
            return {"coordinates": coordinates, "length_km": round(route["distance"] / 1000, 3)}
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
            if attempt == 2:
                raise RuntimeError(f"Unable to fetch {url}: {error}") from error
            time.sleep(2 * (attempt + 1))


def save_routes(routes):
    pending = OUTPUT.with_suffix(".json.tmp")
    pending.write_text(
        json.dumps(
            {
                "source": "OpenStreetMap via OSRM public demo routing service",
                "profile": "driving",
                "routes": routes,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ) + "\n",
        encoding="utf-8",
    )
    pending.replace(OUTPUT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--improve", action="store_true", help="Compare reverse driving routes for long detours")
    args = parser.parse_args()
    routes = json.loads(OUTPUT.read_text(encoding="utf-8"))["routes"] if OUTPUT.exists() else {}
    for index, (_, a_id, b_id, *_rest) in enumerate(EDGE_ROWS, 1):
        road_id = f"HN-{index:03d}"
        a, b = NODES[a_id], NODES[b_id]
        direct_km = math.hypot((a["lat"] - b["lat"]) * 111, (a["lng"] - b["lng"]) * 104)
        if args.improve:
            current = routes.get(road_id)
            if not current or current["length_km"] < direct_km * 1.8:
                continue
            reverse = fetch_route(b, a)
            if reverse["length_km"] < current["length_km"] * 0.8:
                reverse["coordinates"].reverse()
                routes[road_id] = reverse
                save_routes(routes)
                print(f"Improved {road_id}: {current['length_km']:.1f} -> {reverse['length_km']:.1f} km", flush=True)
            time.sleep(0.35)
            continue
        if road_id in routes:
            continue
        route = fetch_route(a, b)
        if route["length_km"] > max(4, direct_km * 4):
            print(f"Check detour HN-{index:03d}: {route['length_km']:.1f} km vs {direct_km:.1f} km", flush=True)
        routes[road_id] = route
        save_routes(routes)
        print(f"{index:3}/{len(EDGE_ROWS)} {road_id}: {route['length_km']:.1f} km, {len(route['coordinates'])} points", flush=True)
        time.sleep(0.35)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
