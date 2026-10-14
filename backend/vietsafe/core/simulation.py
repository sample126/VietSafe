"""Bộ mô phỏng "ảnh chụp hiện trạng" (snapshot) của toàn mạng đường.

Hiện toàn bộ dữ liệu quan sát là GIẢ LẬP theo kịch bản thời tiết. Đây là chỗ sẽ được thay bằng
dữ liệu thật (mưa, tốc độ, mực nước) khi có lớp thu thập dữ liệu - xem docs/ROADMAP.md.

Quy tắc quan trọng (có test): phản ánh `pending` KHÔNG BAO GIỜ làm đổi trạng thái đường hay
chi phí định tuyến; chỉ phản ánh `verified` còn hạn mới có tác dụng.
"""

import math
import time

from .forecast import MODEL_VERSION, clamp, forecast
from .network import NODES, ROADS

SCENARIOS = {"normal": ("Trời khô", 0), "rain": ("Mưa lớn", 28), "storm": ("Mưa rất lớn", 55)}


def build_snapshot(scenario="rain", reports=(), now=None):
    """Dựng snapshot toàn mạng đường cho một thời điểm.

    - `scenario`: khóa trong SCENARIOS (quyết định lượng mưa mm/h).
    - `reports`: danh sách phản ánh (chỉ loại `verified` còn hạn mới được áp dụng).
    - `now`: Unix time; mặc định là hiện tại. Dữ liệu dao động theo `now // 10` (đổi mỗi 10 giây).

    Trả về dict gồm: generated_at, mode, scenario, model_version, rainfall, roads (kèm
    forecast 0/15/30/45/60 phút), events, nodes, counts, pending, source_notice, forecast_notice.
    """
    now = time.time() if now is None else now
    tick = int(now // 10)
    rain = SCENARIOS[scenario][1]
    states = []
    for i, road in enumerate(ROADS):
        seed = road["seed_event"]
        wave = math.sin(tick * 0.17 + i) * 2
        flooded = seed == "flood" and rain > 0
        depth = (
            round(max(0, (13 if scenario == "rain" else 31) + road["susceptibility"] * 9 + wave), 1)
            if flooded
            else 0
        )
        severity = 3 if depth >= 30 else 2 if depth >= 15 or seed in ("traffic", "incident") else 1
        incident = seed == "incident"
        speed = max(4, road["free_speed"] - (19 if seed == "traffic" else 5) - rain * 0.13 + wave)
        if flooded:
            speed = max(3, speed - depth * 0.37)
        state = dict(
            road,
            known=seed != "unknown",
            speed=round(speed, 1),
            depth=depth,
            flood_risk=round(clamp(depth * 2.2 + rain * road["susceptibility"] * 0.45)),
            incident=incident,
            blocked=depth >= 30,
            severity=severity,
            event_type="flood" if flooded else seed if seed in ("traffic", "incident") else None,
            updated_at=tick * 10,
            sources=["Bộ mô phỏng tại máy"],
            evidence=["Quan sát tạo bởi kịch bản " + SCENARIOS[scenario][0]],
            origin="demo",
            report_id=None,
        )
        # Pending reports NEVER change road status or route costs.
        for report in sorted(reports, key=lambda r: r["created_at"]):
            if (
                report["road_id"] != road["id"]
                or report["status"] != "verified"
                or report["expires_at"] <= now
            ):
                continue
            state.update(
                known=True,
                event_type=report["type"],
                severity=report["severity"],
                updated_at=report["created_at"],
                origin="local_report",
                report_id=report["id"],
            )
            state["sources"] = ["Phản ánh tại máy • đã xác minh thủ công"]
            state["evidence"] = [report["description"]]
            if report["type"] == "flood":
                state.update(
                    flood_risk=max(state["flood_risk"], report["severity"] * 28),
                    blocked=state["blocked"] or report["severity"] == 3,
                )
            elif report["type"] == "incident":
                state.update(incident=True, blocked=state["blocked"] or report["severity"] == 3)
            elif report["type"] == "traffic":
                state["speed"] = min(state["speed"], 22 - report["severity"] * 5)
        states.append(state)
    for state in states:
        neighbors = [
            s["speed"]
            for s in states
            if s["id"] != state["id"] and s["known"] and {s["a"], s["b"]} & {state["a"], state["b"]}
        ]
        state["forecast"] = [
            forecast(
                state,
                state,
                sum(neighbors) / len(neighbors) if neighbors else state["speed"],
                rain,
                h,
            )
            for h in (0, 15, 30, 45, 60)
        ]
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
                    lat=sum(c[0] for c in s["coordinates"]) / 2,
                    lng=sum(c[1] for c in s["coordinates"]) / 2,
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
        if r["status"] == "pending" and r["expires_at"] > now:
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
        scenario=scenario,
        model_version=MODEL_VERSION,
        rainfall=rain,
        temperature=27 if rain else 31,
        roads=states,
        events=events,
        nodes=list(NODES.values()),
        counts={
            t: sum(e["type"] == t and e["status"] == "verified" for e in events)
            for t in ("flood", "traffic", "incident")
        },
        pending=sum(r["status"] == "pending" and r["expires_at"] > now for r in reports),
        source_notice="Chưa kết nối VOV, camera hoặc cơ quan khí tượng/thoát nước.",
        forecast_notice="Điểm nguy cơ theo quy tắc minh họa; không phải xác suất hoặc kết quả AI đã huấn luyện.",
    )
