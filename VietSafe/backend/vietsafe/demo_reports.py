"""Tạo lại các phản ánh mẫu cố định để trình diễn luồng quản trị."""

import argparse
import time

from . import config
from .app import init_app
from .db import connect

DEMO_REPORTS = (
    {
        "id": "R-DEMO-PENDING",
        "description": "[DEMO] Nước ngập gần Cầu Giấy, cần kiểm tra hiện trường.",
        "status": "pending",
        "media": None,
        "media_type": None,
        "verified": False,
    },
    {
        "id": "R-DEMO-VERIFIED",
        "description": "[DEMO] Đã xác minh tình trạng ngập gần Cầu Giấy.",
        "status": "verified",
        "media": None,
        "media_type": None,
        "verified": True,
    },
    {
        "id": "R-DEMO-PHOTO",
        "description": "[DEMO] Phản ánh chờ xác minh có ảnh minh họa thử nghiệm.",
        "status": "pending",
        "media": bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
        ),
        "media_type": "image/png",
        "verified": False,
    },
)
DEMO_IDS = tuple(report["id"] for report in DEMO_REPORTS)


def restore_demo_reports():
    """Thay thế chính xác các fixture R-DEMO; không tác động phản ánh người dùng."""
    init_app()
    now = time.time()
    created_at = now - 60
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        placeholders = ",".join("?" for _ in DEMO_IDS)
        db.execute(f"DELETE FROM audit WHERE report_id IN ({placeholders})", DEMO_IDS)
        db.execute(f"DELETE FROM reports WHERE id IN ({placeholders})", DEMO_IDS)

        for report in DEMO_REPORTS:
            db.execute(
                "INSERT INTO reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    report["id"],
                    "HN-001",
                    "flood",
                    2,
                    21.0313,
                    105.8006,
                    "Khu vực Cầu Giấy (dữ liệu DEMO)",
                    report["description"],
                    report["status"],
                    created_at,
                    now + config.REPORT_TTL_SECONDS,
                    report["media"],
                    report["media_type"],
                    now if report["verified"] else None,
                ),
            )
            db.execute(
                "INSERT INTO audit(report_id,action,timestamp,detail) VALUES(?,?,?,?)",
                (report["id"], "created", created_at, "Fixture DEMO để trình diễn."),
            )
            if report["verified"]:
                db.execute(
                    "INSERT INTO audit(report_id,action,timestamp,detail) VALUES(?,?,?,?)",
                    (
                        report["id"],
                        "verified",
                        now - 30,
                        "Trạng thái mẫu cho kịch bản trình diễn.",
                    ),
                )
    return DEMO_IDS


def main():
    parser = argparse.ArgumentParser(
        description="Khôi phục ba phản ánh R-DEMO-* cho buổi trình diễn VietSafe."
    )
    parser.add_argument(
        "--restore",
        action="store_true",
        required=True,
        help="thay thế đúng các fixture R-DEMO-*; không xóa phản ánh khác",
    )
    parser.parse_args()
    ids = restore_demo_reports()
    print("Đã khôi phục phản ánh demo: " + ", ".join(ids))
    print("Database: " + str(config.DB_PATH))


if __name__ == "__main__":
    main()
