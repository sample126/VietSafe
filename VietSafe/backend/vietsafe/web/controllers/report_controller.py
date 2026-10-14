"""Endpoint phản ánh cộng đồng: danh sách, gửi mới, duyệt (admin), tải ảnh đính kèm."""

from ... import config, reports
from ..ratelimit import SlidingWindowLimiter
from ..router import Response, router

# Giới hạn số phản ánh gửi mỗi phút theo IP (xem web/ratelimit.py về lưu ý khi chạy sau proxy).
report_limiter = SlidingWindowLimiter(config.REPORT_RATE_LIMIT_PER_MINUTE, 60)


@router.get("/api/reports")
def list_reports(req):
    return {"reports": reports.get_reports()}


@router.post("/api/reports", auth="user", deny="Vui lòng đăng nhập để gửi phản ánh.")
def create_report(req):
    if not report_limiter.allow(req.client_ip):
        return Response({"error": "Bạn đã gửi nhiều phản ánh. Vui lòng chờ một phút."}, 429)
    return Response(reports.create_report(req.body), 201)


@router.post(
    "/api/reports/{report_id}", auth="admin", deny="Chỉ quản trị viên mới có thể duyệt phản ánh."
)
def review_report(req):
    return reports.review_report(req.params["report_id"], req.body.get("status"))


@router.get("/api/report-media/{report_id}")
def report_media(req):
    media = reports.get_report_media(req.params["report_id"])
    if media is None:
        return Response({"error": "Không có ảnh."}, 404)
    data, mime = media
    return Response(data, content_type=mime)
