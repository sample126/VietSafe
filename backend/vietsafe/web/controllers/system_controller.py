"""Endpoint hệ thống và dữ liệu bản đồ (công khai): sức khỏe, snapshot, tìm kiếm, tìm tuyến."""

from ... import service
from ...core.forecast import MODEL_VERSION
from ...core.routing import calculate_routes
from ...core.search import search_places
from ..router import router


@router.get("/api/health")
def health(req):
    return {"ok": True, "mode": "demo", "model_version": MODEL_VERSION}


@router.get("/api/snapshot")
def snapshot(req):
    return service.current_snapshot()


@router.get("/api/search")
def search(req):
    return {"results": search_places(req.arg("q"))}


@router.get("/api/routes")
def routes(req):
    return calculate_routes(
        service.current_snapshot(),
        req.arg("origin"),
        req.arg("destination"),
        int(req.arg("horizon", "0")),
        req.arg("vehicle", "motorbike"),
    )
