"""Lazy artifact loading. No downloads, training, arbitrary paths or synthetic fallback."""

import hashlib
import importlib
import importlib.util
import json
import logging
import os
import threading
from pathlib import Path

from .contracts import FLAGS, SCHEMA_VERSION, TASKS, Unavailable, envelope, task_spec

LOCK = threading.RLock()
_providers = {}
_failures = {}
MANIFEST = Path(__file__).with_name("artifact_manifest.json")
DEPENDENCIES = ("numpy", "pandas", "sklearn", "joblib", "pyarrow", "threadpoolctl")


def root_path():
    value = os.environ.get("VIETSAFE_AI_RESEARCH_ROOT", "").strip()
    return Path(value).resolve() if value else None


def readiness(task):
    spec = task_spec(task)
    root = root_path()
    if root is None:
        return "not_configured", "Chưa cấu hình VIETSAFE_AI_RESEARCH_ROOT."
    if any(importlib.util.find_spec(name) is None for name in DEPENDENCIES):
        return "missing_dependencies", "Cần môi trường Python theo requirements-ai.txt."
    files = json.loads(MANIFEST.read_text(encoding="utf-8"))[task]
    if not all((root / spec["folder"] / name).is_file() for name in files):
        return "missing_artifacts", "Chưa đủ checkpoint hoặc dữ liệu đã xử lý của bài toán này."
    key = (str(root), task)
    if key in _failures:
        return "unavailable", _failures[key]
    return (
        ("ready", "Đã nạp mô hình.")
        if key in _providers
        else ("available", "Có tệp cục bộ; sẽ xác minh và nạp khi mở bài toán.")
    )


def catalog():
    rows = []
    for task, spec in TASKS.items():
        status, message = readiness(task)
        rows.append(
            {
                "id": task,
                **{k: v for k, v in spec.items() if k != "folder"},
                "status": status,
                "message": message,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "retrospective_replay",
        **FLAGS,
        "tasks": rows,
    }


def verify_artifacts(task, folder):
    files = json.loads(MANIFEST.read_text(encoding="utf-8"))[task]
    for name, expected in files.items():
        path = folder / name
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise Unavailable(
                "Tệp nghiên cứu khác phiên bản đã kiểm thử. Cần kiểm tra lại bộ artifact."
            )


def provider(task):
    spec = task_spec(task)
    with LOCK:
        status, message = readiness(task)
        if status not in ("ready", "available"):
            raise Unavailable(message)
        root = root_path()
        key = (str(root), task)
        if key not in _providers:
            try:
                from sklearn import __version__

                if __version__ != "1.6.1":
                    raise Unavailable(
                        "Checkpoint yêu cầu scikit-learn 1.6.1; xem requirements-ai.txt."
                    )
                folder = root / spec["folder"]
                verify_artifacts(task, folder)
                module = importlib.import_module(f".{task}", __package__)
                _providers[key] = module.Provider(folder)
            except Exception as exc:
                logging.getLogger(__name__).exception("AI artifact loading failed for %s", task)
                message = (
                    str(exc)
                    if isinstance(exc, Unavailable)
                    else (
                        "Không nạp được mô hình/dữ liệu. Xem nhật ký máy chủ và hướng dẫn AI_FORECAST.md."
                    )
                )
                _failures[key] = message
                raise Unavailable(message) from exc
        return _providers[key]


def sites(task):
    p = provider(task)
    return {**envelope(task), "sites": p.sites(), "default": p.default}


def times(task, site, day):
    if not isinstance(site, str) or not isinstance(day, str):
        raise ValueError("Điểm và ngày phải là chuỗi.")
    return {**envelope(task), "times": provider(task).times(site, day)}


def predict(payload):
    if set(payload) != {"task", "site_id", "origin"}:
        raise ValueError(
            "Chỉ nhận task, site_id, origin; không nhận đường dẫn hoặc nhãn tương lai."
        )
    task, site, origin = (payload[key] for key in ("task", "site_id", "origin"))
    task_spec(task)
    if not isinstance(site, str) or not isinstance(origin, str) or len(origin) > 80:
        raise ValueError("Điểm và thời điểm không hợp lệ.")
    # threadpoolctl changes process-wide limits; serialize inference across all tasks.
    with LOCK:
        p = provider(task)
        from threadpoolctl import threadpool_limits

        with threadpool_limits(limits=2):
            result = p.predict(site, origin)
        # Reject NaN/Infinity before the common HTTP serializer can emit invalid JSON.
        result = {**envelope(task), **result}
        json.dumps(result, allow_nan=False)
        return result
