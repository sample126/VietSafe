"""Endpoint quản trị (chỉ admin): đổi kịch bản mô phỏng, xuất nhật ký dự báo và phản ánh."""

from ... import reports, service
from ...core.forecast import MODEL_VERSION
from ..router import Response, router


def _download(filename):
    """Header yêu cầu trình duyệt tải phản hồi về thành file."""
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


@router.post("/api/scenario", auth="admin", deny="Chỉ quản trị viên mới có thể đổi kịch bản.")
def set_scenario(req):
    return {"scenario": service.set_scenario(req.body.get("scenario"))}


@router.get(
    "/api/export/predictions", auth="admin", deny="Chỉ quản trị viên mới có thể xuất dữ liệu."
)
def export_predictions(req):
    body = {"mode": "demo", "model_version": MODEL_VERSION, "logs": service.prediction_logs()}
    return Response(body, headers=_download("vietsafe-predictions.json"))


@router.get("/api/export/reports", auth="admin", deny="Chỉ quản trị viên mới có thể xuất dữ liệu.")
def export_reports(req):
    return Response(
        reports.export_csv(reports.get_reports()),
        content_type="text/csv; charset=utf-8",
        headers=_download("vietsafe-reports.csv"),
    )
