"""Tìm kiếm tên nút giao / đoạn đường (không phân biệt dấu và hoa thường)."""

import unicodedata

from .network import NODES, ROADS


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
            lat=sum(c[0] for c in r["coordinates"]) / 2,
            lng=sum(c[1] for c in r["coordinates"]) / 2,
            kind="road",
        )
        for r in ROADS
        if term in normalize(r["name"])
    ]
    return matches[:limit]
