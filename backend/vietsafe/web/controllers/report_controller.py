"""Endpoint phản ánh cộng đồng: danh sách, gửi mới, duyệt (admin), tải ảnh đính kèm."""

from ... import config, reports
from ..ratelimit import SlidingWindowLimiter
from ..router import Response, router

# Giới hạn số phản ánh gửi mỗi phút theo tài khoản (xem web/ratelimit.py về lưu ý khi chạy sau proxy).
report_limiter = SlidingWindowLimiter(config.REPORT_RATE_LIMIT_PER_MINUTE, 60)


@router.get("/api/roads")
def list_roads(req):
    return {"roads": reports.get_road_names()}


@router.get("/api/reports")
def list_reports(req):
    status = req.arg("status") or None
    severity = req.arg("severity") or None
    date_from = req.arg("date_from") or None
    date_to = req.arg("date_to") or None
    return {
        "reports": reports.get_reports(
            status=status,
            severity=int(severity) if severity else None,
            date_from=float(date_from) if date_from else None,
            date_to=float(date_to) if date_to else None,
        )
    }


@router.get(
    "/api/reports/{report_id}/history",
    auth="admin",
    deny="Chỉ quản trị viên mới có thể xem lịch sử phản ánh.",
)
def report_history(req):
    return {"history": reports.get_report_history(req.params["report_id"])}


@router.post("/api/reports", auth="user", deny="Vui lòng đăng nhập để gửi phản ánh.")
def create_report(req):
    if not report_limiter.allow(req.user["username"]):
        return Response({"error": "Bạn đã gửi nhiều phản ánh. Vui lòng chờ một phút."}, 429)
    return Response(reports.create_report(req.body, username=req.user["username"]), 201)


@router.get("/api/my-reports", auth="user", deny="Vui lòng đăng nhập.")
def my_reports(req):
    return {"reports": reports.get_my_reports(req.user["username"])}


@router.post(
    "/api/reports/bulk-review",
    auth="admin",
    deny="Chỉ quản trị viên mới có thể duyệt phản ánh.",
)
def bulk_review(req):
    ids = req.body.get("ids", [])
    status = req.body.get("status")
    reason = req.body.get("reason")
    if not ids or not isinstance(ids, list):
        return Response({"error": "Danh sách phản ánh không hợp lệ."}, 400)
    return reports.bulk_review(ids, status, reason)


@router.get("/api/notifications", auth="user", deny="Vui lòng đăng nhập.")
def get_notifications(req):
    return {"notifications": reports.get_notifications(req.user["username"])}


@router.get("/api/notifications/unread-count", auth="user", deny="Vui lòng đăng nhập.")
def get_unread_count(req):
    return {"count": reports.get_unread_count(req.user["username"])}


@router.post("/api/notifications/read", auth="user", deny="Vui lòng đăng nhập.")
def mark_read(req):
    ids = req.body.get("ids") if isinstance(req.body, dict) else None
    reports.mark_notifications_read(req.user["username"], ids)
    return {"ok": True}


@router.post(
    "/api/reports/{report_id}", auth="admin", deny="Chỉ quản trị viên mới có thể duyệt phản ánh."
)
def review_report(req):
    return reports.review_report(
        req.params["report_id"], req.body.get("status"), req.body.get("reason")
    )


@router.get("/api/report-media/{report_id}")
def report_media(req):
    media = reports.get_report_media(req.params["report_id"])
    if media is None:
        return Response({"error": "Không có ảnh."}, 404)
    data, mime = media
    return Response(data, content_type=mime)
