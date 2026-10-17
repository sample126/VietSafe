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
from .core.network import NODES, ROADS, nearest_road
from .core.search import normalize
from .db import connect

# Pillow là phụ thuộc tùy chọn: có thì nén ảnh lớn, không có thì bỏ qua (giữ zero-dependency).
try:  # pragma: no cover - phụ thuộc môi trường
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def get_road_names():
    """Trả về danh sách tên đường trong mạng demo (cho autocomplete)."""
    return sorted({road["name"] for road in ROADS} | {node["name"] for node in NODES.values()})


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


def get_reports(status=None, severity=None, date_from=None, date_to=None, username=None):
    """Danh sách tối đa 500 phản ánh mới nhất; đồng thời đánh dấu `expired` các phản ánh quá hạn.

    Bộ lọc tùy chọn: status, severity, date_from, date_to, username.
    """
    with connect() as db:
        now = time.time()
        expired = db.execute(
            "SELECT id FROM reports WHERE expires_at<? AND status IN ('pending','verified')",
            (now,),
        ).fetchall()
        if expired:
            db.executemany(
                "UPDATE reports SET status='expired' WHERE id=?",
                [(row["id"],) for row in expired],
            )
            db.executemany(
                "INSERT INTO audit(report_id,action,timestamp) VALUES(?,?,?)",
                [(row["id"], "expired", now) for row in expired],
            )
        conditions = []
        params = []
        if status:
            conditions.append("status=?")
            params.append(status)
        if severity:
            conditions.append("severity=?")
            params.append(severity)
        if date_from:
            conditions.append("created_at>=?")
            params.append(date_from)
        if date_to:
            conditions.append("created_at<=?")
            params.append(date_to)
        if username:
            conditions.append("username=?")
            params.append(username)
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT {_LIST_COLUMNS} FROM reports WHERE {where_clause} ORDER BY created_at DESC LIMIT 500"
        rows = db.execute(query, params).fetchall()
    return [
        dict(r, media_url="/api/report-media/" + r["id"] if r["media_type"] else None) for r in rows
    ]


def get_my_reports(username):
    """Lấy phản ánh của một người dùng cụ thể, kèm lý do từ chối (nếu có)."""
    reports_list = get_reports(username=username)
    with connect() as db:
        for r in reports_list:
            r["reason"] = None
            if r["status"] == "rejected":
                row = db.execute(
                    "SELECT detail FROM audit WHERE report_id=? AND action='rejected' ORDER BY timestamp DESC LIMIT 1",
                    (r["id"],),
                ).fetchone()
                if row and row["detail"]:
                    r["reason"] = row["detail"]
    return reports_list


def bulk_review(report_ids, status, reason=None):
    """Duyệt nhiều phản ánh cùng lúc. Trả về {success: [...], failed: [...]}."""
    if status not in ("verified", "rejected", "resolved"):
        raise ValueError("Trạng thái không hợp lệ.")
    if status == "rejected":
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Cần nhập lý do từ chối phản ánh.")
        reason = reason.strip()
        if len(reason) > 240:
            raise ValueError("Lý do từ chối tối đa 240 ký tự.")
    else:
        reason = None

    success = []
    failed = []
    notifications = []  # (username, report_id, message)
    now = time.time()

    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        for report_id in report_ids:
            try:
                row = db.execute(
                    "SELECT status, expires_at, address, username FROM reports WHERE id=?", (report_id,)
                ).fetchone()
                if not row:
                    failed.append({"id": report_id, "error": "Không tìm thấy"})
                    continue
                if row["expires_at"] <= now or status not in REVIEW_TRANSITIONS.get(row["status"], ()):
                    failed.append({"id": report_id, "error": "Không thể chuyển trạng thái"})
                    continue
                db.execute("UPDATE reports SET status=?,reviewed_at=? WHERE id=?", (status, now, report_id))
                db.execute(
                    "INSERT INTO audit(report_id,action,timestamp,detail) VALUES(?,?,?,?)",
                    (report_id, status, now, reason),
                )
                success.append(report_id)
                status_labels = {"verified": "đã được xác minh", "rejected": "đã bị từ chối", "resolved": "đã được xử lý"}
                msg = f"Phản ánh {report_id} ({row['address']}) {status_labels[status]}."
                if reason:
                    msg += f" Lý do: {reason}"
                # Chỉ báo cho chủ sở hữu; phản ánh không có username (fixture demo)
                # thì không ai để báo — KHÔNG được gánefault cho một tài khoản khác.
                if row["username"]:
                    notifications.append((row["username"], report_id, msg))
            except Exception as e:
                failed.append({"id": report_id, "error": str(e)})
        db.execute("COMMIT")

    for username, report_id, message in notifications:
        create_notification(username, report_id, message)

    return {"success": success, "failed": failed}


def get_report_history(report_id):
    """Lịch sử trạng thái cho một phản ánh; quyền truy cập được kiểm tra ở controller."""
    with connect() as db:
        if not db.execute("SELECT 1 FROM reports WHERE id=?", (report_id,)).fetchone():
            raise ValueError("Không tìm thấy phản ánh.")
        rows = db.execute(
            "SELECT action,timestamp,detail FROM audit WHERE report_id=? ORDER BY timestamp,id",
            (report_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_report_media(report_id):
    """Trả về (bytes, mime) của ảnh đính kèm, hoặc None."""
    with connect() as db:
        row = db.execute("SELECT media,media_type FROM reports WHERE id=?", (report_id,)).fetchone()
    if not row or not row["media"]:
        return None
    return row["media"], row["media_type"]


def _compress_image(media, media_type):
    """Nén ảnh để giảm dung lượng lưu trữ. Bỏ qua nếu thiếu Pillow hoặc ảnh đã nhỏ."""
    if Image is None or len(media) <= 500_000:
        return media, media_type
    try:
        img = Image.open(io.BytesIO(media))
        max_dim = 1200
        if max(img.size) > max_dim:
            ratio = max_dim / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        output = io.BytesIO()
        if media_type == "image/jpeg":
            img.save(output, format="JPEG", quality=75, optimize=True)
        elif media_type == "image/png":
            img.save(output, format="PNG", optimize=True)
        else:  # webp
            img.save(output, format="WEBP", quality=75)
        compressed = output.getvalue()
        if len(compressed) < len(media):
            return compressed, media_type
    except Exception:
        pass
    return media, media_type


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
        media, media_type = _compress_image(media, media_type)
    except (ValueError, TypeError, AttributeError, binascii.Error):
        raise ValueError("Ảnh phải là JPG, PNG hoặc WebP, tối đa 1,5 MB.") from None
    return media, media_type


def _resolve_address(address):
    """Map a typed address to the most specific matching place in the demo road graph."""
    query = normalize(address.strip())
    if not query:
        raise ValueError("Hãy nhập địa chỉ hoặc dùng GPS để xác định vị trí.")

    places = [dict(node, kind="node") for node in NODES.values()]
    places.extend(
        dict(
            id=road["id"],
            name=road["name"],
            lat=sum(point[0] for point in road["coordinates"]) / 2,
            lng=sum(point[1] for point in road["coordinates"]) / 2,
            kind="road",
        )
        for road in ROADS
    )
    matches = [place for place in places if normalize(place["name"]) in query]
    if not matches:
        raise ValueError(
            "Chưa tìm thấy địa chỉ trong mạng đường thử nghiệm. Hãy nhập tên đường hoặc nút giao gợi ý, hoặc dùng GPS."
        )

    longest_name = max(len(normalize(place["name"])) for place in matches)
    matches = [place for place in matches if len(normalize(place["name"])) == longest_name]
    matching_nodes = [place for place in matches if place["kind"] == "node"]
    if matching_nodes:
        matches = matching_nodes
    locations = {(place["lat"], place["lng"]): place for place in matches}
    if len(locations) > 1:
        raise ValueError(
            "Địa chỉ khớp nhiều vị trí trong mạng thử nghiệm. Hãy nhập tên đường hoặc nút giao cụ thể hơn."
        )
    return next(iter(locations.values()))


def create_report(body, username=None):
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
    address = body.get("address", "")
    if not isinstance(address, str) or len(address) > 200:
        raise ValueError("Địa chỉ tối đa 200 ký tự.")
    location_source = "gps"
    resolved_place = None
    if "lat" in body or "lng" in body:
        try:
            lat, lng = float(body["lat"]), float(body["lng"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Tọa độ GPS không hợp lệ.") from None
    else:
        place = _resolve_address(address)
        lat, lng = place["lat"], place["lng"]
        location_source = "address"
        resolved_place = place["name"]
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
    media = media_type = None
    if body.get("image"):
        media, media_type = _decode_image(body["image"])

    now = time.time()
    with connect() as db:
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
            return {
                "id": existing[0],
                "duplicate": True,
                "status": "pending",
                "location_source": location_source,
                "resolved_place": resolved_place,
            }
        report_id = "R-" + secrets.token_hex(4).upper()
        db.execute(
            "INSERT INTO reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
                username,
            ),
        )
        db.execute(
            "INSERT INTO audit(report_id,action,timestamp) VALUES(?,?,?)",
            (report_id, "created", now),
        )
    return {
        "id": report_id,
        "status": "pending",
        "road_id": road["id"],
        "duplicate": False,
        "location_source": location_source,
        "resolved_place": resolved_place,
    }


def review_report(report_id, status, reason=None):
    """Admin chuyển trạng thái phản ánh theo REVIEW_TRANSITIONS; ghi vào bảng `audit`."""
    if status not in ("verified", "rejected", "resolved"):
        raise ValueError("Trạng thái không hợp lệ.")
    if status == "rejected":
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("Cần nhập lý do từ chối phản ánh.")
        reason = reason.strip()
        if len(reason) > 240:
            raise ValueError("Lý do từ chối tối đa 240 ký tự.")
    else:
        reason = None
    notification_message = None
    notification_username = None
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT status, expires_at, address, username FROM reports WHERE id=?", (report_id,)
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
            "INSERT INTO audit(report_id,action,timestamp,detail) VALUES(?,?,?,?)",
            (report_id, status, now, reason),
        )
        status_labels = {"verified": "đã được xác minh", "rejected": "đã bị từ chối", "resolved": "đã được xử lý"}
        notification_message = f"Phản ánh {report_id} ({row['address']}) {status_labels[status]}."
        if reason:
            notification_message += f" Lý do: {reason}"
        # None nếu phản ánh không thuộc tài khoản nào -> không gửi thông báo.
        notification_username = row["username"]
    if notification_message and notification_username:
        create_notification(notification_username, report_id, notification_message)
    return {"id": report_id, "status": status}


def create_notification(username, report_id, message):
    """Tạo thông báo cho người dùng khi phản ánh của họ được xử lý."""
    with connect() as db:
        db.execute(
            "INSERT INTO notifications(username, report_id, message, created_at) VALUES(?,?,?,?)",
            (username, report_id, message, time.time()),
        )


def get_notifications(username, limit=20):
    """Lấy thông báo của người dùng (mới nhất trước)."""
    with connect() as db:
        rows = db.execute(
            "SELECT id, report_id, message, read, created_at FROM notifications "
            "WHERE username=? ORDER BY created_at DESC LIMIT ?",
            (username, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_notifications_read(username, notification_ids=None):
    """Đánh dấu thông báo đã đọc. Nếu không chỉ định IDs, đánh dấu tất cả."""
    with connect() as db:
        if notification_ids:
            placeholders = ",".join("?" for _ in notification_ids)
            db.execute(
                f"UPDATE notifications SET read=1 WHERE username=? AND id IN ({placeholders})",
                [username, *notification_ids],
            )
        else:
            db.execute("UPDATE notifications SET read=1 WHERE username=?", (username,))


def get_unread_count(username):
    """Số thông báo chưa đọc của người dùng."""
    with connect() as db:
        row = db.execute(
            "SELECT COUNT(*) as count FROM notifications WHERE username=? AND read=0",
            (username,),
        ).fetchone()
    return row["count"] if row else 0


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
