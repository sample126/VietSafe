"""A* route suggestions on the locally extracted, directed OSM road graph."""

import heapq
import math

from .network import NODES, distance
from .osm_graph import MODE_BITS, load_graph, major_component, snap_point

# Experimental demo assumptions in centimetres; NOT real-world safety guidance.
FLOOD_LIMIT_CM = {"motorbike": 15, "car": 25, "walk": 10}
DEFAULT_SPEED = {"motorbike": 30, "car": 36, "walk": 4.5}


def _location(value):
    if value in NODES:
        n = NODES[value]
        return n["lat"], n["lng"], n["name"]
    try:
        lat, lng = [float(part.strip()) for part in value.split(",", 1)]
    except (AttributeError, ValueError):
        raise ValueError("Hãy chọn địa điểm có trong danh sách hoặc chọn điểm trên bản đồ.") from None
    if not (20.58 <= lat <= 21.36 and 105.27 <= lng <= 106.08):
        raise ValueError("Điểm chọn nằm ngoài phạm vi bản đồ Hà Nội thử nghiệm.")
    return lat, lng, f"Điểm trên bản đồ ({lat:.4f}, {lng:.4f})"


def calculate_routes(snapshot, origin, destination, horizon=0, vehicle="motorbike"):
    if horizon not in (0, 30, 60) or vehicle not in MODE_BITS:
        raise ValueError("Thời điểm hoặc phương tiện không hợp lệ.")
    start = _location(origin)
    end = _location(destination)
    if distance(start[:2], end[:2]) < 0.02:
        raise ValueError("Điểm đi và điểm đến phải khác nhau.")
    graph = load_graph()
    nodes, edges, names, adjacency, _, hazards = graph
    states = {road["id"]: road for road in snapshot["roads"]}
    bit = MODE_BITS[vehicle]
    def open_edge(eid):
        road = states.get(hazards[eid])
        if not road:
            return True
        point = road["forecast"][horizon // 15]
        return road["known"] and not (road["blocked"] and horizon == 0) and not point["blocked"] and point["depth"] < FLOOD_LIMIT_CM[vehicle]

    component = major_component(vehicle)
    source, source_snap = snap_point(*start[:2], vehicle, graph, open_edge, component)
    target, target_snap = snap_point(*end[:2], vehicle, graph, open_edge, component)
    if source == target:
        raise ValueError("Hai điểm được ghép vào cùng một nút đường. Hãy chọn điểm xa hơn.")
    direct = distance(nodes[source], nodes[target])

    def solve(policy):
        def estimate(node):
            km = distance(nodes[node], nodes[target])
            return km if policy == "shortest" else km / (95 if vehicle != "walk" else 6) * 60

        queue = [(estimate(source), 0, 0, source)]
        best = {source: 0}
        parent = {}
        while queue:
            _, cost, elapsed, node = heapq.heappop(queue)
            if cost > best[node] + 1e-8:
                continue
            if node == target:
                path = []
                while node != source:
                    previous, edge_id = parent[node]
                    path.append((previous, node, edge_id))
                    node = previous
                return list(reversed(path)), elapsed
            for nxt, edge_id, permissions in adjacency[node]:
                if not permissions & bit:
                    continue
                km = edges[edge_id][2]
                road = states.get(hazards[edge_id])
                point = None
                if road:
                    arrival = min(60, horizon + elapsed)
                    point = road["forecast"][min(4, math.ceil(arrival / 15))]
                    if (road["blocked"] and horizon == 0) or point["blocked"] or not road["known"] or point["depth"] >= FLOOD_LIMIT_CM[vehicle] or point["risk"] is None:
                        continue
                speed = DEFAULT_SPEED[vehicle]
                if point and vehicle != "walk":
                    speed = min(speed, max(3, point["speed"]))
                minutes = km / speed * 60
                risk = point["risk"] / 100 if point else 0
                weight = km + risk * km * 0.001 if policy == "shortest" else minutes + risk * km * (22 if policy == "cautious" else 1.5)
                new_cost = cost + weight
                if new_cost + 1e-8 < best.get(nxt, float("inf")):
                    best[nxt] = new_cost
                    parent[nxt] = node, edge_id
                    heapq.heappush(queue, (new_cost + estimate(nxt), new_cost, elapsed + minutes, nxt))
        return None

    routes = []
    for policy, title in (("fast", "Nhanh nhất"), ("shortest", "Ngắn nhất"), ("cautious", "Ít rủi ro nhất")):
        solved = solve(policy)
        if not solved:
            continue
        path, minutes = solved
        edge_ids = [item[2] for item in path]
        if any(edge_ids == r["osm_edge_ids"] for r in routes):
            continue
        coordinates = [nodes[source]] + [nodes[to] for _, to, _ in path]
        road_ids = list(dict.fromkeys(hazards[eid] for eid in edge_ids if hazards[eid]))
        warnings = [states[rid]["name"] for rid in road_ids if (states[rid]["event_type"] if horizon == 0 else (states[rid]["forecast"][horizon // 15]["risk"] or 0) >= 65)]
        steps = list(dict.fromkeys(names[edges[eid][5]] for eid in edge_ids))
        max_risk = max((states[rid]["forecast"][horizon // 15]["risk"] or 0 for rid in road_ids), default=0)
        timeline = []
        for future in (0, 30, 60):
            eta = 0
            for eid in edge_ids:
                road = states.get(hazards[eid])
                speed = DEFAULT_SPEED[vehicle]
                if road and vehicle != "walk":
                    predicted = road["forecast"][future // 15]
                    if predicted["speed"] is not None:
                        speed = min(speed, max(3, predicted["speed"]))
                eta += edges[eid][2] / speed * 60
            affected = [states[rid]["forecast"][future // 15] for rid in road_ids]
            timeline.append(dict(
                horizon=future, eta_minutes=round(eta, 1),
                congested_segments=sum(p["traffic_risk"] is not None and p["traffic_risk"] >= 65 for p in affected),
                flooded_segments=sum(p["depth"] is not None and p["depth"] >= 10 for p in affected),
                max_risk=max((p["risk"] or 0 for p in affected), default=0),
            ))
        routes.append(dict(
            id=policy, title=title, road_ids=road_ids, osm_edge_ids=edge_ids,
            coordinates=coordinates, distance_km=round(sum(edges[eid][2] for eid in edge_ids), 2),
            eta_minutes=round(minutes, 1), max_risk=max_risk, steps=steps[:30],
            warnings=warnings, warning_count=len(warnings), vehicle=vehicle, forecast_timeline=timeline,
            origin_name=start[2], destination_name=end[2],
            origin_snap_km=round(source_snap, 2), destination_snap_km=round(target_snap, 2),
        ))
    return dict(
        routes=routes, calculated_at=snapshot["generated_at"],
        excluded=sum(r["blocked"] or not r["known"] for r in states.values()),
        message=("Tuyến trên đồ thị OSM cục bộ; chưa xét cấm rẽ, quy định theo giờ và tình trạng thực tế. Chỉ để thử nghiệm."
                 if routes else "Không tìm được tuyến hợp lệ trên mạng đường OSM cho phương tiện đã chọn."),
        flood_limits_cm=FLOOD_LIMIT_CM, direct_km=round(direct, 2),
    )
