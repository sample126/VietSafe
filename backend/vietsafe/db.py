"""SQLite connection and schema. Database file is runtime state, not source code."""
import os
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from .config import DB_PATH as DEFAULT_DB_PATH

DB_PATH = DEFAULT_DB_PATH

@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    DB_PATH.parent.mkdir(exist_ok=True, parents=True)
    with connect() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT OR IGNORE INTO settings VALUES ('scenario','rain');
        CREATE TABLE IF NOT EXISTS reports(
          id TEXT PRIMARY KEY, road_id TEXT NOT NULL, type TEXT NOT NULL, severity INTEGER NOT NULL,
          lat REAL NOT NULL, lng REAL NOT NULL, address TEXT NOT NULL, description TEXT NOT NULL,
          status TEXT NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL,
          media BLOB, media_type TEXT, reviewed_at REAL);
        CREATE TABLE IF NOT EXISTS prediction_logs(
          tick INTEGER PRIMARY KEY, created_at REAL, model_version TEXT, scenario TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, report_id TEXT, action TEXT, timestamp REAL);
        CREATE TABLE IF NOT EXISTS users(
          username TEXT PRIMARY KEY,
          password_hash TEXT NOT NULL,
          display_name TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'citizen'
        );
        CREATE TABLE IF NOT EXISTS flood_observations(
          id TEXT PRIMARY KEY, road_id TEXT, lat REAL NOT NULL, lng REAL NOT NULL,
          depth_cm REAL NOT NULL, observed_at REAL NOT NULL, received_at REAL NOT NULL,
          source TEXT NOT NULL, source_reference TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
          verification_status TEXT NOT NULL DEFAULT 'verified'
        );
        CREATE INDEX IF NOT EXISTS idx_flood_time ON flood_observations(observed_at);
        CREATE TABLE IF NOT EXISTS sessions(
          token TEXT PRIMARY KEY,
          username TEXT NOT NULL,
          created_at REAL NOT NULL,
          expires_at REAL NOT NULL
        );
        ''')




    # Bootstrap admin only when explicitly configured; no public known-password accounts.
    from .auth import hash_password
    admin_password = os.environ.get('VIETSAFE_ADMIN_PASSWORD', '')
    if admin_password:
        if len(admin_password) < 12:
            raise ValueError('VIETSAFE_ADMIN_PASSWORD phải có ít nhất 12 ký tự.')
        with connect() as db:
            existing = db.execute('SELECT 1 FROM users WHERE username=?', ('admin',)).fetchone()
            if not existing:
                db.execute('INSERT INTO users VALUES(?,?,?,?)',
                           ('admin', hash_password(admin_password), 'Quản trị viên', 'admin'))
