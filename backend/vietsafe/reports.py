"""Phản ánh hiện trường từ cộng đồng: tạo, duyệt, liệt kê, xuất CSV.

Vòng đời trạng thái:

    pending --(admin)--> verified --(admin)--> resolved
       |
       +--(admin)--> rejected              (pending/verified tự chuyển `expired` khi quá hạn)

Chỉ phản ánh `verified` còn hạn mới ảnh hưởng bản đồ và định tuyến (xem core/simulation.py).
"""

import base64
import binascii
import csv
import io
import math
import secrets
import time

from . import config
from .core.network import nearest_road
from .db import connect

REPORT_TYPES = ("flood", "traffic", "incident")
REVIEW_TRANSITIONS = {"pending": ("verified", "rejected"), "verified": ("resolved",)}
IMAGE_SIGNATURES = {
    "image/jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
    "image/png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
    "image/webp": lambda b: b.startswith(b"RIFF") and b[8:12] == b"WEBP",
}
_LIST_COLUMNS = (
    "id,road_id,type,severity,lat,lng,address,description,status,"
    "created_at,expires_at,reviewed_at,media_type"
)


def get_reports():
    """Danh sách tối đa 500 phản ánh mới nhất; đồng thời đánh dấu `expired` các phản ánh quá hạn."""
    with connect() as db:
        db.execute(
            "UPDATE reports SET status='expired' "
            "WHERE expires_at<? AND status IN ('pending','verified')",
            (time.time(),),
        )
        rows = db.execute(
            f"SELECT {_LIST_COLUMNS} FROM reports ORDER BY created_at DESC LIMIT 500"
        ).fetchall()
    return [
        dict(r, media_url="/api/report-media/" + r["id"] if r["media_type"] else None) for r in rows
    ]


def get_report_media(report_id):
    """Trả về (bytes, mime) của ảnh đính kèm, hoặc None."""
    with connect() as db:
        row = db.execute("SELECT media,media_type FROM reports WHERE id=?", (report_id,)).fetchone()
    if not row or not row["media"]:
        return None
    return row["media"], row["media_type"]


def _decode_image(data_url):
    """Giải mã data URL ảnh; kiểm tra MIME, chữ ký file (magic bytes) và kích thước."""
    try:
        header, encoded = data_url.split(",", 1)
        media_type = header.removeprefix("data:").removesuffix(";base64")
        if media_type not in IMAGE_SIGNATURES:
            raise ValueError
        media = base64.b64decode(encoded, validate=True)
        if len(media) > config.REPORT_MAX_IMAGE_BYTES or not IMAGE_SIGNATURES[media_type](media):
            raise ValueError
    except (ValueError, TypeError, AttributeError, binascii.Error):
        raise ValueError("Ảnh phải là JPG, PNG hoặc WebP, tối đa 1,5 MB.") from None
    return media, media_type


def create_report(body):
    """Validate và lưu phản ánh mới (trạng thái `pending`).

    Trả về {id, status, road_id, duplicate}. Nếu cùng đoạn đường + loại + mô tả đã được gửi
    trong 5 phút và còn `pending`, trả về phản ánh cũ với `duplicate=True`.
    """
    if not isinstance(body, dict):
        raise ValueError("Nội dung phản ánh không hợp lệ.")
    if body.get("type") not in REPORT_TYPES:
        raise ValueError("Loại phản ánh không hợp lệ.")
    if type(body.get("severity")) is not int or body["severity"] not in (1, 2, 3):
        raise ValueError("Hãy chọn mức độ 1–3.")
    try:
        lat, lng = float(body["lat"]), float(body["lng"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Hãy chọn vị trí trên bản đồ.") from None
    lat_lo, lat_hi = config.PILOT_LAT_RANGE
    lng_lo, lng_hi = config.PILOT_LNG_RANGE
    if not (math.isfinite(lat) and math.isfinite(lng)) or not (
        lat_lo <= lat <= lat_hi and lng_lo <= lng <= lng_hi
    ):
        raise ValueError("Vị trí nằm ngoài vùng thử nghiệm nội thành Hà Nội.")
    km, road, _ = nearest_road(lat, lng)
    if km > config.REPORT_MAX_DISTANCE_KM:
        raise ValueError(
            "Vị trí cách mạng đường thử nghiệm hơn 1 km. Hãy chọn một đoạn đường gần hơn."
        )
    description = body.get("description", "")
    if not isinstance(description, str) or not 10 <= len(description.strip()) <= 1200:
        raise ValueError("Mô tả cần từ 10 đến 1.200 ký tự.")
    address = body.get("address", "")
    if not isinstance(address, str) or len(address) > 200:
        raise ValueError("Địa chỉ tối đa 200 ký tự.")
    media = media_type = None
    if body.get("image"):
        media, media_type = _decode_image(body["image"])

    now = time.time()
    with connect() as db:
        # Khóa ghi ngay từ đầu để kiểm tra trùng + chèn là một thao tác nguyên tử.
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT id FROM reports WHERE road_id=? AND type=? AND description=? "
            "AND created_at>? AND status='pending'",
            (
                road["id"],
                body["type"],
                description.strip(),
                now - config.REPORT_DUPLICATE_WINDOW_SECONDS,
            ),
        ).fetchone()
        if existing:
            return {"id": existing[0], "duplicate": True, "status": "pending"}
        report_id = "R-" + secrets.token_hex(4).upper()
        db.execute(
            "INSERT INTO reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                report_id,
                road["id"],
                body["type"],
                body["severity"],
                lat,
                lng,
                address.strip() or road["name"],
                description.strip(),
                "pending",
                now,
                now + config.REPORT_TTL_SECONDS,
                media,
                media_type,
                None,
            ),
        )
        db.execute(
            "INSERT INTO audit(report_id,action,timestamp) VALUES(?,?,?)",
            (report_id, "created", now),
        )
    return {"id": report_id, "status": "pending", "road_id": road["id"], "duplicate": False}


def review_report(report_id, status):
    """Admin chuyển trạng thái phản ánh theo REVIEW_TRANSITIONS; ghi vào bảng `audit`."""
    if status not in ("verified", "rejected", "resolved"):
        raise ValueError("Trạng thái không hợp lệ.")
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT status,expires_at FROM reports WHERE id=?", (report_id,)
        ).fetchone()
        if not row:
            raise ValueError("Không tìm thấy phản ánh.")
        if row["expires_at"] <= time.time() or status not in REVIEW_TRANSITIONS.get(
            row["status"], ()
        ):
            raise ValueError("Phản ánh đã hết hạn hoặc không thể chuyển sang trạng thái này.")
        now = time.time()
        db.execute("UPDATE reports SET status=?,reviewed_at=? WHERE id=?", (status, now, report_id))
        db.execute(
            "INSERT INTO audit(report_id,action,timestamp) VALUES(?,?,?)",
            (report_id, status, now),
        )
    return {"id": report_id, "status": status}


def export_csv(rows):
    """Xuất CSV (UTF-8 BOM để Excel đọc đúng tiếng Việt); chặn CSV/formula injection."""
    fields = ["id", "road_id", "type", "severity", "address", "description", "status", "created_at"]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                k: "'" + v
                if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r"))
                else v
                for k, v in row.items()
            }
        )
    return ("\ufeff" + stream.getvalue()).encode("utf-8")
