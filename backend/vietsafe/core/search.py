"""Tìm kiếm tên nút giao / đoạn đường (không phân biệt dấu và hoa thường)."""

import unicodedata
import json
from functools import lru_cache
from pathlib import Path

from .network import NODES, ROADS


@lru_cache(maxsize=1)
def _streets():
    path = Path(__file__).with_name("hanoi_street_search.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def normalize(text):
    """Bỏ dấu tiếng Việt, đổi đ -> d, chữ thường."""
    decomposed = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def search_places(query, limit=12):
    term = normalize(query)[:150]
    matches = [dict(n, kind="node") for n in NODES.values() if term in normalize(n["name"])]
    matches += [
        dict(
            id=r["id"],
            name=r["name"],
            lat=r["center"][0],
            lng=r["center"][1],
            kind="road",
        )
        for r in ROADS
        if term in normalize(r["name"])
    ]
    if len(matches) < limit and len(term) >= 2:
        matches += [dict(id=f"osm-{i}", name=name, lat=lat, lng=lng, kind="osm_street") for i, (name, lat, lng) in enumerate(_streets()) if term in normalize(name)][:limit - len(matches)]
    return matches[:limit]
