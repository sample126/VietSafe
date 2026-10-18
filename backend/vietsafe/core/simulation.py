"""Bộ mô phỏng "ảnh chụp hiện trạng" (snapshot) của toàn mạng đường.

Hiện toàn bộ dữ liệu quan sát là GIẢ LẬP theo kịch bản thời tiết. Đây là chỗ sẽ được thay bằng
dữ liệu thật (mưa, tốc độ, mực nước) khi có lớp thu thập dữ liệu - xem docs/ROADMAP.md.

Quy tắc quan trọng (có test): phản ánh `pending` KHÔNG BAO GIỜ làm đổi trạng thái đường hay
chi phí định tuyến; chỉ phản ánh `verified` còn hạn mới có tác dụng.
"""

import time

from .. import config
from .flood_provider import simulate_flood
from .forecast import MODEL_VERSION, clamp, forecast
from .network import NODES, ROADS
from .traffic_provider import simulate_traffic

SCENARIOS = {"normal": ("Trời khô", 0), "rain": ("Mưa lớn", 28), "storm": ("Mưa rất lớn", 55)}


def _base_state(road, scenario, at):
    """Deterministic 15-minute traffic and rainfall state in Hanoi local time."""
    rain = SCENARIOS[scenario][1]
    slot = int(at // 900)
    seed = road["seed_event"]
    depth = simulate_flood(road, scenario, at)
    flooded = depth > 0
    speed, incident = simulate_traffic(road, at, rain, depth)
    return dict(
        road,
        road_segment_id=road["id"],
        geometry={"type": "LineString", "coordinates": [[lng, lat] for lat, lng in road["coordinates"]]},
        speed_limit=road["free_speed"],
        simulated_speed=speed,
        congestion_level="cao" if speed < road["free_speed"] * 0.45 else "vừa" if speed < road["free_speed"] * 0.7 else "thấp",
        flood_depth=depth,
        incident_type="incident" if incident else None,
        simulated_timestamp=slot * 900,
        scenario_id=scenario,
        known=seed != "unknown",
        speed=speed,
        depth=depth,
        flood_risk=round(clamp(depth * 2.2 + rain * road["susceptibility"] * 0.45)),
        incident=incident,
        blocked=depth >= 30,
        severity=3 if depth >= 30 else 2 if depth >= 15 or seed in ("traffic", "incident") else 1,
        event_type="flood" if flooded else seed if seed in ("traffic", "incident") else None,
        updated_at=slot * 900,
        sources=["Bộ mô phỏng tại máy"],
        evidence=["Giá trị và sự kiện do kịch bản " + SCENARIOS[scenario][0] + " tạo ra; không phải quan trắc thực tế."],
        origin="demo",
        report_id=None,
    )


def _apply_reports(state, reports, at):
    for report in sorted(reports, key=lambda r: r["created_at"]):
        if report["road_id"] != state["id"] or report["status"] != "verified" or report["expires_at"] <= at or report["created_at"] > at:
            continue
        types = [t for t in str(report["type"]).split(",") if t]
        state.update(known=True, event_type=",".join(types), severity=report["severity"], updated_at=report["created_at"], origin="local_report", report_id=report["id"])
        state["sources"] = ["Phản ánh tại máy • đã xác minh thủ công"]
        state["evidence"] = [report["description"]]
        if "flood" in types:
            state.update(flood_risk=max(state["flood_risk"], report["severity"] * 28), blocked=state["blocked"] or report["severity"] == 3)
        if "incident" in types:
            state.update(incident=True, blocked=state["blocked"] or report["severity"] == 3)
        if "traffic" in types:
            state["speed"] = min(state["speed"], 22 - report["severity"] * 5)
            state["simulated_speed"] = state["speed"]


def build_snapshot(scenario="rain", reports=(), now=None):
    """Dựng snapshot toàn mạng đường cho một thời điểm.

    - `scenario`: khóa trong SCENARIOS (quyết định lượng mưa mm/h).
    - `reports`: danh sách phản ánh (chỉ loại `verified` còn hạn mới được áp dụng).
    - `now`: Unix time; mặc định là hiện tại. Trạng thái ổn định trong từng ô 15 phút.

    Trả về dict gồm: generated_at, mode, scenario, model_version, rainfall, roads (kèm
    forecast 0/15/30/45/60 phút), events, nodes, counts, pending, source_notice, forecast_notice.
    """
    real_now = time.time() if now is None else now
    now = config.SIMULATION_EPOCH + (real_now - config.SIMULATION_EPOCH) * config.SIMULATION_SPEED if now is None else now
    rain = SCENARIOS[scenario][1]
    states = []
    for road in ROADS:
        state = _base_state(road, scenario, now)
        _apply_reports(state, reports, real_now)
        if road["reference_url"]:
            state["evidence"].append("Địa điểm được nhắc trong bài viết lịch sử của Thoát nước Hà Nội; tình trạng hiện tại chưa được xác minh.")
        states.append(state)
    future_states = {h: [_base_state(road, scenario, now + h * 60) for road in ROADS] for h in (15, 30, 45, 60)}
    for h, future in future_states.items():
        for state in future:
            _apply_reports(state, reports, real_now + h * 60 / config.SIMULATION_SPEED)
    adjacency = {s["id"]: [other["id"] for other in states if other["id"] != s["id"] and {other["a"], other["b"]} & {s["a"], s["b"]}] for s in states}
    for state in states:
        state["forecast"] = []
        for h in (0, 15, 30, 45, 60):
            group = states if h == 0 else future_states[h]
            current = group[int(state["id"][-3:]) - 1]
            neighbors = [group[int(rid[-3:]) - 1]["speed"] for rid in adjacency[state["id"]] if group[int(rid[-3:]) - 1]["known"]]
            point = forecast(state, current, sum(neighbors) / len(neighbors) if neighbors else current["speed"], rain, 0)
            point["horizon"] = h
            point["depth"] = current["depth"] if current["known"] else None
            point["blocked"] = current["blocked"]
            state["forecast"].append(point)
        state["risk"] = state["forecast"][0]["risk"]
    events = []
    for s in states:
        if s["event_type"] and s["known"]:
            events.append(
                dict(
                    id=s["report_id"] or "demo-" + s["id"],
                    road_id=s["id"],
                    name=s["name"],
                    type=s["event_type"],
                    severity=s["severity"],
                    lat=s["center"][0],
                    lng=s["center"][1],
                    depth=s["depth"] if s["origin"] == "demo" else None,
                    speed=s["speed"],
                    updated_at=s["updated_at"],
                    sources=s["sources"],
                    evidence=s["evidence"],
                    origin=s["origin"],
                    status="verified",
                    blocked=s["blocked"],
                )
            )
    for r in reports:
        if r["status"] == "pending" and r["expires_at"] > real_now:
            events.append(
                dict(
                    id=r["id"],
                    road_id=r["road_id"],
                    name=r["address"],
                    type=r["type"],
                    severity=r["severity"],
                    lat=r["lat"],
                    lng=r["lng"],
                    updated_at=r["created_at"],
                    sources=["Phản ánh tại máy"],
                    evidence=[r["description"]],
                    origin="local_report",
                    status="pending",
                    blocked=False,
                )
            )
    events.sort(key=lambda e: (e["status"] == "pending", -e["severity"], -e["updated_at"]))
    return dict(
        generated_at=now,
        mode="demo",
        simulation_speed=config.SIMULATION_SPEED,
        scenario=scenario,
        model_version=MODEL_VERSION,
        rainfall=rain,
        temperature=27 if rain else 31,
        roads=states,
        events=events,
        nodes=list(NODES.values()),
        counts={
            t: sum(t in str(e["type"]).split(",") and e["status"] == "verified" for e in events)
            for t in ("flood", "traffic", "incident")
        },
        pending=sum(r["status"] == "pending" and r["expires_at"] > real_now for r in reports),
        source_notice="Hình học đường OpenStreetMap/OSRM và lớp đường chính OSM lưu cục bộ; cảnh báo mô phỏng, chưa kết nối Google Maps, VOV, camera hoặc quan trắc thoát nước.",
        forecast_notice="Ngập, ùn tắc và sự cố là chỉ số theo quy tắc trên dữ liệu giả lập; không phải xác suất hay cảnh báo thời gian thực.",
    )
