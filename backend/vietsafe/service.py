"""Lớp dịch vụ: ghép dữ liệu từ DB với logic lõi (core/) để tạo ra câu trả lời cho API."""

import json

from . import config
from .core.forecast import MODEL_VERSION
from .core.simulation import SCENARIOS, build_snapshot
from .db import connect
from .reports import get_reports


def get_scenario():
    with connect() as db:
        return db.execute("SELECT value FROM settings WHERE key='scenario'").fetchone()[0]


def set_scenario(value):
    if value not in SCENARIOS:
        raise ValueError("Kịch bản không hợp lệ.")
    with connect() as db:
        db.execute("UPDATE settings SET value=? WHERE key='scenario'", (value,))
    return value


def current_snapshot():
    """Snapshot hiện tại (kịch bản + phản ánh đã xác minh) và ghi nhật ký dự báo.

    Ghi tối đa 1 bản ghi / 10 giây (khóa theo `tick`), giữ lại 24 giờ để sau này đối chiếu
    với số liệu quan sát thực tế.
    """
    scenario = get_scenario()
    result = build_snapshot(scenario, get_reports())
    tick = int(result["generated_at"] // 10)
    payload = [dict(road_id=r["id"], forecast=r["forecast"]) for r in result["roads"]]
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO prediction_logs VALUES(?,?,?,?,?)",
            (tick, result["generated_at"], MODEL_VERSION, scenario, json.dumps(payload)),
        )
        db.execute(
            "DELETE FROM prediction_logs WHERE tick < ?",
            (tick - config.PREDICTION_LOG_RETENTION_TICKS,),
        )
    return result


def prediction_logs():
    with connect() as db:
        rows = db.execute(
            "SELECT * FROM prediction_logs ORDER BY tick DESC LIMIT ?",
            (config.PREDICTION_LOG_EXPORT_LIMIT,),
        ).fetchall()
    return [dict(r) for r in rows]
