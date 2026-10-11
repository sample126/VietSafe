"""HTTP adapter for the opt-in research replay; public GETs expose no file paths."""

from ...forecasting import service
from ...forecasting.contracts import FLAGS, Unavailable
from ..router import Response, router


def call(function, *args):
    try:
        return function(*args)
    except Unavailable as exc:
        return Response({"status": "unavailable", "error": str(exc), **FLAGS}, status=503)


@router.get("/api/ai/catalog")
def catalog(req):
    return service.catalog()


@router.get("/api/ai/sites")
def sites(req):
    return call(service.sites, req.arg("task"))


@router.get("/api/ai/times")
def times(req):
    return call(service.times, req.arg("task"), req.arg("site_id"), req.arg("day"))


@router.post("/api/ai/predict")
def predict(req):
    return call(service.predict, req.body)
