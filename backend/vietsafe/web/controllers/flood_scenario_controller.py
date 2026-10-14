"""Isolated synthetic scenario API; never writes public alerts or observations."""

from ...forecasting import scenario
from ..router import router


@router.get("/api/flood-simulation/catalog")
def catalog(req):
    return scenario.catalog()


@router.post("/api/flood-simulation/predict")
def predict(req):
    return scenario.predict(req.body)
