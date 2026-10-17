"""Replaceable rule-based demo flood provider; depths are not measurements."""


def simulate_flood(road, scenario, at):
    if scenario == "normal" or road["seed_event"] != "flood":
        return 0
    slot = int(at // 900)
    jitter = ((int(road["id"][-3:]) * 37 + slot * 11) % 9 - 4) * 0.35
    baseline = 6 if scenario == "rain" else 26
    return round(max(0, baseline + road["susceptibility"] * 8 + jitter), 1)
