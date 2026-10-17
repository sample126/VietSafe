"""Replaceable rule-based demo traffic provider; no live observations."""

from datetime import datetime, timedelta, timezone

HANOI_TIME = timezone(timedelta(hours=7))


def simulate_traffic(road, at, rain, flood_depth):
    local = datetime.fromtimestamp(at, HANOI_TIME)
    hour = local.hour + local.minute / 60
    weekend = local.weekday() >= 5
    peak = (7 <= hour < 9 or 17 <= hour < 19) if not weekend else 18 <= hour < 21
    rush = (0.56 if weekend else 1.0) if peak else (0.16 if weekend else 0.28)
    slot = int(at // 900)
    jitter = ((int(road["id"][-3:]) * 37 + slot * 11) % 9 - 4) * 0.35
    incident = road["seed_event"] == "incident"
    speed = max(4, road["free_speed"] * (1 - rush * (0.28 + road["traffic_hotspot"] * 0.36)) - rain * 0.1 + jitter)
    if flood_depth:
        speed = max(3, speed - flood_depth * 0.3)
    if incident:
        speed = max(3, speed * 0.58)
    if road["seed_event"] == "traffic" and peak:
        speed = max(3, speed * 0.78)
    return round(speed, 1), incident
