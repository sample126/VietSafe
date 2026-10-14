"""Deterministic, idealized surface storage. No Hanoi observations or trained AI.

Runoff enters a flat ponding area instantly. Drain discharge increases with the
square root of depth until the user-specified capacity at 10 cm. One-second
explicit steps conserve water by limiting drainage to the available volume.
This is a standalone conceptual water-balance model, NOT the SWMM engine.
"""

import copy
import math

MODEL_VERSION = "idealized-surface-storage-v1"
LIMITS = {
    "initial_depth_cm": (0, 100),
    "catchment_area_ha": (0.1, 10),
    "ponding_area_m2": (100, 10000),
    "runoff_coefficient": (0, 1),
    "drainage_capacity_lps": (0, 1000),
    "blockage_percent": (0, 100),
    "threshold_cm": (1, 50),
    "sustain_minutes": (1, 20),
}
DEFAULT = {
    "initial_depth_cm": 0,
    "catchment_area_ha": 2,
    "ponding_area_m2": 1800,
    "runoff_coefficient": 0.8,
    "drainage_capacity_lps": 40,
    "blockage_percent": 20,
    "threshold_cm": 5,
    "sustain_minutes": 10,
    "rain_mm_h": [5, 15, 35, 65, 80, 80, 65, 45, 25, 10, 0, 0],
}
PRESETS = [
    {"id": "heavy", "name": "Mưa lớn · vùng trũng", "inputs": DEFAULT},
    {
        "id": "light",
        "name": "Mưa nhẹ · thoát tốt",
        "inputs": {**DEFAULT, "catchment_area_ha": 1.2, "runoff_coefficient": 0.6,
                   "drainage_capacity_lps": 100, "blockage_percent": 0,
                   "rain_mm_h": [4, 4, 6, 8, 8, 8, 6, 4, 2, 0, 0, 0]},
    },
    {"id": "dry", "name": "Không mưa · đường khô",
     "inputs": {**DEFAULT, "rain_mm_h": [0] * 12}},
    {"id": "receding", "name": "Đã có nước · mưa tạnh",
     "inputs": {**DEFAULT, "initial_depth_cm": 18, "drainage_capacity_lps": 100,
                "blockage_percent": 0, "rain_mm_h": [0] * 12}},
]
FLAGS = {
    "mode": "synthetic_scenario",
    "input_provenance": "user_assumptions_or_synthetic_presets",
    "synthetic": True,
    "hanoi_calibrated": False,
    "public_alert_allowed": False,
    "uses_trained_ai": False,
    "probability": None,
}


def catalog():
    return copy.deepcopy({
        "model_version": MODEL_VERSION,
        "fields": LIMITS,
        "presets": PRESETS,
        "rain_intervals": 12,
        "rain_interval_minutes": 5,
        "rain_limits_mm_h": [0, 150],
        **FLAGS,
    })


def _number(value, name, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: cần nhập một số.")
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{name}: giá trị phải từ {lo} đến {hi}.")
    return float(value)


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != set(DEFAULT):
        raise ValueError("Đầu vào phải đủ các thông số kịch bản, không thêm trường khác.")
    params = {k: _number(payload[k], k, *bounds) for k, bounds in LIMITS.items()}
    if not params["sustain_minutes"].is_integer():
        raise ValueError("Thời gian duy trì ngập phải là số phút nguyên.")
    if params["ponding_area_m2"] > params["catchment_area_ha"] * 10000:
        raise ValueError("Diện tích vùng trũng không được lớn hơn diện tích hứng nước.")
    rain = payload["rain_mm_h"]
    if not isinstance(rain, list) or len(rain) != 12:
        raise ValueError("Cần đúng 12 cường độ mưa, mỗi giá trị đại diện 5 phút.")
    params["rain_mm_h"] = [_number(r, "Cường độ mưa (mm/h)", 0, 150) for r in rain]
    return params


def _run(params):
    area = params["ponding_area_m2"]
    initial = params["initial_depth_cm"] / 100 * area
    volume = initial
    inflow_total = outflow_total = 0.0
    capacity = params["drainage_capacity_lps"] / 1000 * (
        1 - params["blockage_percent"] / 100
    )
    threshold_m = params["threshold_cm"] / 100
    already_above = params["initial_depth_cm"] >= params["threshold_cm"]
    consecutive_start = 0 if already_above else None
    first_confirmed = first_onset = None
    required_seconds = int(params["sustain_minutes"] * 60)
    max_volume = volume
    points = [{"minute": 0, "depth_cm": params["initial_depth_cm"],
               "inflow_cumulative_m3": 0.0, "outflow_cumulative_m3": 0.0}]
    horizons = []
    for second in range(1, 3601):
        rain = params["rain_mm_h"][(second - 1) // 300]
        # mm/h -> m/s; hectare -> m2; dt = 1 second.
        incoming = rain / 1000 / 3600 * params["catchment_area_ha"] * 10000 * (
            params["runoff_coefficient"]
        )
        depth = volume / area
        outgoing = min(capacity * min(1.0, math.sqrt(depth / 0.1)), volume + incoming)
        volume = max(0.0, volume + incoming - outgoing)
        inflow_total += incoming
        outflow_total += outgoing
        max_volume = max(max_volume, volume)
        if volume / area >= threshold_m:
            if consecutive_start is None:
                consecutive_start = second
            if first_confirmed is None and second - consecutive_start >= required_seconds:
                first_onset, first_confirmed = consecutive_start, second
        else:
            consecutive_start = None
        if second % 60 == 0:
            points.append({"minute": second // 60, "depth_cm": round(volume / area * 100, 5),
                           "inflow_cumulative_m3": round(inflow_total, 6),
                           "outflow_cumulative_m3": round(outflow_total, 6)})
        if second in (1800, 3600):
            horizons.append({
                "minutes": second // 60,
                "depth_cm": round(volume / area * 100, 5),
                "onset_status": "already_above_threshold" if already_above else (
                    "onset_confirmed" if first_confirmed is not None else "not_confirmed"
                ),
                "onset_within_horizon": None if already_above else first_confirmed is not None,
            })
    return {
        "horizons": horizons,
        "trajectory": points,
        "initially_above_threshold": already_above,
        "first_onset_minute": None if already_above or first_onset is None else first_onset / 60,
        "confirmed_at_minute": None if already_above or first_confirmed is None else first_confirmed / 60,
        "max_depth_cm": max_volume / area * 100,
        "water_balance": {
            "initial_m3": initial, "inflow_m3": inflow_total, "outflow_m3": outflow_total,
            "final_m3": volume, "residual_m3": initial + inflow_total - outflow_total - volume,
        },
    }


def predict(payload):
    params = validate(payload)
    result = _run(params)
    comparison_params = {**params, "drainage_capacity_lps": params["drainage_capacity_lps"] / 2}
    comparison = _run(comparison_params)
    return {
        "schema_version": "vietsafe.flood-scenario.v1",
        "model_version": MODEL_VERSION,
        **FLAGS,
        "inputs": params,
        "depth_reference": "floor_of_idealized_surface_depression",
        "time_reference": "minutes_after_scenario_start",
        "rainfall_total_mm": sum(params["rain_mm_h"]) * 5 / 60,
        "event_definition": {
            "threshold_cm": params["threshold_cm"], "sustain_minutes": params["sustain_minutes"],
            "confirmation_required_within_horizon": True,
            "time_step_seconds": 1,
        },
        **result,
        "comparison": {
            "name": "Giảm một nửa công suất thoát nước",
            "inputs": comparison_params,
            **comparison,
        },
        "limitations": [
            "Mưa, trạng thái ban đầu và thông số thoát nước đều là giả định.",
            "Độ sâu trên đáy vùng trũng lý tưởng; chưa đo hoặc hiệu chỉnh tại Hà Nội.",
            "Không mô phỏng mạng cống, bơm, nước dâng sông, dòng chảy mặt 2D hay tràn ra vùng khác.",
            "Đường so sánh là kiểm tra độ nhạy, không phải khoảng tin cậy hoặc xác suất.",
        ] + (["Độ sâu vượt 1 m: giả định vùng trũng kín cần được xem xét lại."]
             if comparison["max_depth_cm"] > 100 else []),
    }
