"""Định tuyến Dijkstra có trọng số rủi ro, theo loại phương tiện.

Hai chính sách: "cautious" (phạt rủi ro rất nặng) và "fast" (ưu tiên thời gian). Đoạn đường bị
chặn / chưa có dữ liệu bị loại; đoạn có nguy cơ ngập vượt ngưỡng (xe máy 82, ô tô 88) cũng loại.
"""

import heapq

from .network import NODES


def calculate_routes(snapshot, origin, destination, horizon=0, vehicle="motorbike"):
    """Tìm tối đa 2 tuyến (ít rủi ro / nhanh nhất) giữa hai nút giao.

    `horizon` chỉ nhận 0, 30 hoặc 60 phút; `vehicle` là "motorbike" hoặc "car". Ném ValueError nếu
    đầu vào sai. Trả về {routes, calculated_at, excluded, message}; `routes` rỗng nếu không có đường.
    """
    if origin not in NODES or destination not in NODES:
        raise ValueError("Hãy chọn điểm đi và đến trong khu vực thử nghiệm.")
    if origin == destination:
        raise ValueError("Điểm đi và điểm đến phải khác nhau.")
    if horizon not in (0, 30, 60) or vehicle not in ("motorbike", "car"):
        raise ValueError("Thời điểm hoặc phương tiện không hợp lệ.")
    roads = {s["id"]: s for s in snapshot["roads"]}
    graph = {n: [] for n in NODES}
    for r in roads.values():
        # Unknown and confirmed blocked edges are never offered as traversable.
        if r["blocked"] or not r["known"]:
            continue
        graph[r["a"]].append((r["b"], r["id"]))
        graph[r["b"]].append((r["a"], r["id"]))

    def solve(policy):
        queue = [(0, 0, origin, [], [origin])]
        best = {origin: 0}
        while queue:
            cost, elapsed, node, edgepath, nodepath = heapq.heappop(queue)
            if cost > best[node] + 1e-9:
                continue
            if node == destination:
                return edgepath, nodepath, elapsed
            for nxt, rid in graph[node]:
                r = roads[rid]
                # Use forecast for estimated edge arrival, conservatively rounded upward.
                at = min(60, horizon + elapsed)
                f = next((f for f in r["forecast"] if f["horizon"] >= at), r["forecast"][-1])
                if f["flood_risk"] >= (82 if vehicle == "motorbike" else 88):
                    continue
                minutes = r["length_km"] / max(3, f["speed"]) * 60
                penalty = (
                    (f["risk"] / 100) ** 2 * r["length_km"] * (20 if policy == "cautious" else 1)
                )
                new = cost + minutes + penalty
                if new < best.get(nxt, float("inf")):
                    best[nxt] = new
                    heapq.heappush(
                        queue, (new, elapsed + minutes, nxt, edgepath + [rid], nodepath + [nxt])
                    )
        return None

    result = []
    for policy in ("cautious", "fast"):
        solved = solve(policy)
        if not solved:
            continue
        ids, nodes, elapsed = solved
        if any(r["road_ids"] == ids for r in result):
            continue
        traversed = [roads[i] for i in ids]
        result.append(
            dict(
                id=policy,
                title="Ưu tiên ít rủi ro" if policy == "cautious" else "Ưu tiên thời gian",
                road_ids=ids,
                coordinates=[[NODES[n]["lat"], NODES[n]["lng"]] for n in nodes],
                distance_km=round(sum(r["length_km"] for r in traversed), 1),
                eta_minutes=round(elapsed, 1),
                max_risk=max(r["forecast"][horizon // 15]["risk"] for r in traversed),
                steps=[r["name"] for r in traversed],
                warnings=[r["name"] for r in traversed if r["event_type"]],
            )
        )
    return dict(
        routes=result,
        calculated_at=snapshot["generated_at"],
        excluded=sum(r["blocked"] or not r["known"] for r in roads.values()),
        message="Mạng đường giản lược và dữ liệu thử nghiệm; không dùng để dẫn đường thực tế."
        if result
        else "Không tìm được tuyến đáp ứng điều kiện trên mạng thử nghiệm. Hãy đổi điểm hoặc thời điểm.",
    )
