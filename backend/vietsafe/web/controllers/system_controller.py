"""Endpoint hệ thống và dữ liệu bản đồ (công khai): sức khỏe, snapshot, tìm kiếm, tìm tuyến."""

import json
from functools import lru_cache
from pathlib import Path

from ... import config, service
from ...core.forecast import MODEL_VERSION
from ...core.routing import calculate_routes
from ...core.search import search_places
from ..router import router


@router.get("/api/health")
def health(req):
    return {"ok": True, "mode": "demo", "model_version": MODEL_VERSION}


@router.get("/api/map-config")
def map_config(req):
    return {"maptiler_key": config.MAPTILER_API_KEY}


@router.get("/api/snapshot")
def snapshot(req):
    return service.current_snapshot()


@lru_cache(maxsize=1)
def _major_road_data():
    path = Path(__file__).resolve().parents[2] / "core" / "hanoi_major_roads.json"
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/api/major-roads")
def major_roads(req):
    return _major_road_data()


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
