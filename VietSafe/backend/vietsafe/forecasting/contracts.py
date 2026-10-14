"""Research contract v1; deliberately separate from road-risk DataForecastOutput."""

SCHEMA_VERSION = "vietsafe.ai-replay.v1"
FLAGS = {"public_alert_allowed": False, "hanoi_calibrated": False}
TASKS = {
    "bellinge": {
        "title": "Mực nước hệ thống thoát nước",
        "dataset": "Bellinge · Đan Mạch",
        "model": "HistGradientBoostingRegressor · lịch sử toàn mạng",
        "quantity": "drainage_water_level",
        "unit": "m",
        "horizons_minutes": [30, 60],
        "description": "Mực nước so với mốc cảm biến trong cống/bể; không phải độ ngập mặt đường.",
        "folder": "vietsafe-model-comparison-20261007",
        "checkpoint": "HGB_all_nodes_leaves31_iter240",
        "time_basis": "source_clock_timezone_unverified",
        "origin_kind": "source_datetime",
        "date_label": "Ngày theo đồng hồ bộ dữ liệu",
    },
    "floodnet": {
        "title": "Khả năng xuất hiện ngập mặt đường",
        "dataset": "FloodNet · New York",
        "model": "HistGradientBoostingClassifier + hiệu chỉnh sigmoid",
        "quantity": "probability_of_sustained_depth_ge_5cm",
        "unit": "probability",
        "horizons_minutes": [30, 60],
        "description": "Xác suất xuất hiện độ sâu ≥ 5 cm liên tiếp hai khoảng 5 phút trong cửa sổ tương lai, khi hiện tại dưới 5 cm. Không phải dự báo độ sâu.",
        "folder": "vietsafe-floodnet/early_warning",
        "checkpoint": "warning_30+warning_60",
        "time_basis": "UTC",
        "origin_kind": "utc_datetime",
        "date_label": "Ngày quan trắc (UTC)",
    },
    "sztaxi": {
        "title": "Tốc độ giao thông",
        "dataset": "SZ-Taxi · Thâm Quyến",
        "model": "HistGradientBoostingRegressor · lịch sử lân cận",
        "quantity": "traffic_speed",
        "unit": "source_speed_scale",
        "horizons_minutes": [15, 30, 60],
        "description": "Giá trị tốc độ theo thang dữ liệu gốc; chưa xác nhận đơn vị km/h hoặc nhãn ùn tắc. Chỉ số dòng thay cho thời gian thực.",
        "folder": "vietsafe-traffic-tgcn-20261007",
        "checkpoint": "HGB_neighbours_l31_i240",
        "time_basis": "row_index",
        "origin_kind": "row_index",
        "date_label": "Phần dữ liệu",
    },
}


class Unavailable(RuntimeError):
    """Operator configuration or frozen artifacts are unavailable."""


def task_spec(task):
    if not isinstance(task, str) or task not in TASKS:
        raise ValueError("Bài toán không hợp lệ. Chọn bellinge, floodnet hoặc sztaxi.")
    return TASKS[task]


def envelope(task):
    spec = task_spec(task)
    return {
        "schema_version": SCHEMA_VERSION,
        "task": task,
        "mode": "retrospective_replay",
        "dataset": spec["dataset"],
        "model": spec["model"],
        "model_version": spec["checkpoint"],
        "quantity": spec["quantity"],
        "unit": spec["unit"],
        **FLAGS,
        "time_basis": spec["time_basis"],
        "origin_kind": spec["origin_kind"],
        "future_observations_used_as_input": False,
    }
