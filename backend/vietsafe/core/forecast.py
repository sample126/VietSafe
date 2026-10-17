"""Công thức dự báo nguy cơ ngập / tốc độ cho một đoạn đường.

ĐÂY LÀ MÔ HÌNH QUY TẮC MINH HỌA (explainable baseline), KHÔNG phải mô hình T-GCN đã huấn luyện
và điểm nguy cơ KHÔNG phải xác suất đã hiệu chỉnh. Khi có mô hình thật, thay hàm `forecast`
(giữ nguyên chữ ký) và tăng `MODEL_VERSION`.
"""

MODEL_VERSION = "hanoi-schedule-demo-2.0"


def clamp(x, low=0, high=100):
    return max(low, min(high, x))


def forecast(road, current, neighbor_speed, rain, horizon):
    """Dự báo cho `horizon` phút tới (0-60) của một đoạn đường.

    Trả về ba chỉ số nguy cơ, tốc độ và rủi ro tổng hợp. Đoạn chưa có dữ liệu (`known=False`)
    trả về các giá trị None và nhãn "Chưa đủ dữ liệu" - không bịa số.
    """
    h = horizon / 60
    if not current["known"]:
        return dict(
            horizon=horizon,
            flood_risk=None,
            traffic_risk=None,
            incident_risk=None,
            speed=None,
            risk=None,
            label="Chưa đủ dữ liệu",
        )
    # Rainfall, susceptibility, current flood, spatial neighbor congestion and time horizon.
    flood = clamp(
        current["flood_risk"] + h * (rain * road["susceptibility"] * 0.8 - (9 if rain == 0 else 0))
    )
    speed = max(
        3,
        current["speed"] * (1 - 0.22 * h)
        + 0.12 * h * (neighbor_speed - current["speed"])
        - rain * 0.08 * h
        - (4 * h if current["incident"] else 0),
    )
    if rain == 0:
        speed = min(road["free_speed"], current["speed"] + h * 4)
    congestion = clamp((1 - speed / road["free_speed"]) * 100)
    traffic = clamp(congestion * 0.85 + road.get("traffic_hotspot", 0) * 30 + 6 * h)
    incident = clamp(
        (88 if current["incident"] else road.get("incident_hotspot", 0) * 45)
        + rain * 0.12 + 10 * h
    )
    risk = round(max(flood, traffic, incident))
    return dict(
        horizon=horizon,
        flood_risk=round(flood),
        traffic_risk=round(traffic),
        incident_risk=round(incident),
        speed=round(speed, 1),
        risk=risk,
        label="Cao" if risk >= 65 else "Trung bình" if risk >= 35 else "Thấp",
    )
