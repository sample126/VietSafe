"""Kết nối SQLite và schema.

Chỉ chứa hạ tầng lưu trữ. Logic nghiệp vụ nằm ở auth.py, reports.py, service.py.
"""

import sqlite3
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO settings VALUES ('scenario','rain');

CREATE TABLE IF NOT EXISTS reports(
  id TEXT PRIMARY KEY, road_id TEXT NOT NULL, type TEXT NOT NULL, severity INTEGER NOT NULL,
  lat REAL NOT NULL, lng REAL NOT NULL, address TEXT NOT NULL, description TEXT NOT NULL,
  status TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
  media BLOB, media_type TEXT, reviewed_at REAL);

CREATE TABLE IF NOT EXISTS prediction_logs(
  tick INTEGER PRIMARY KEY, created_at REAL, model_version TEXT, scenario TEXT, payload TEXT);

CREATE TABLE IF NOT EXISTS audit(
  id INTEGER PRIMARY KEY, report_id TEXT, action TEXT, timestamp REAL);

CREATE TABLE IF NOT EXISTS users(
  username TEXT PRIMARY KEY,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'citizen');

CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY,
  username TEXT NOT NULL,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL);
"""


@contextmanager
def connect():
    """Mở kết nối, tự commit khi thoát khối `with`, luôn đóng kết nối.

    `config.DB_PATH` được đọc ở mỗi lần gọi để test có thể trỏ sang DB tạm.
    """
    db = sqlite3.connect(config.DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def init_schema():
    """Tạo thư mục dữ liệu và các bảng nếu chưa có (idempotent)."""
    config.DB_PATH.parent.mkdir(exist_ok=True, parents=True)
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
