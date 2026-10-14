"""Tài khoản, mật khẩu và phiên đăng nhập.

Vai trò: `citizen` (người dân) và `admin` (quản trị viên). Khách vãng lai không có tài khoản.

GHI CHÚ BẢO MẬT: mật khẩu hiện chỉ băm SHA-256 không có salt (đủ cho demo, KHÔNG đủ cho
vận hành thật). Khi nâng cấp, đổi `hash_password` / `verify_password` sang scrypt hoặc
PBKDF2 kèm salt và băm lại khi người dùng đăng nhập kế tiếp. Xem docs/ROADMAP.md.
"""

import hashlib
import secrets
import sqlite3
import time

from . import config
from .db import connect


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password, password_hash):
    return secrets.compare_digest(hash_password(password), password_hash)


def seed_demo_users():
    """Tạo 2 tài khoản demo nếu chưa tồn tại."""
    demo = [
        ("admin", config.DEMO_ADMIN_PASSWORD, "Quản trị viên", "admin"),
        ("nguoidan", config.DEMO_CITIZEN_PASSWORD, "Nguyễn Văn A", "citizen"),
    ]
    with connect() as db:
        for username, password, display_name, role in demo:
            db.execute(
                "INSERT OR IGNORE INTO users VALUES(?,?,?,?)",
                (username, hash_password(password), display_name, role),
            )


def create_session(username):
    """Tạo token phiên (hạn 24 giờ) và dọn các phiên đã hết hạn."""
    token = secrets.token_hex(32)
    now = time.time()
    with connect() as db:
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        db.execute(
            "INSERT INTO sessions VALUES(?,?,?,?)",
            (token, username, now, now + config.SESSION_TTL_SECONDS),
        )
    return token


def delete_session(token):
    with connect() as db:
        db.execute("DELETE FROM sessions WHERE token=?", (token,))


def get_user_by_session(token):
    """Trả về dict {username, display_name, role} hoặc None nếu token sai / hết hạn."""
    if not token:
        return None
    with connect() as db:
        row = db.execute(
            "SELECT u.username, u.display_name, u.role FROM sessions s "
            "JOIN users u ON s.username=u.username WHERE s.token=? AND s.expires_at>?",
            (token, time.time()),
        ).fetchone()
    return dict(row) if row else None


def login(username, password):
    """Xác thực. Trả về (user, token) hoặc None nếu sai thông tin."""
    if not isinstance(username, str) or not isinstance(password, str):
        raise ValueError("Vui lòng nhập tên đăng nhập và mật khẩu.")
    username = username.strip()
    if not username or not password:
        raise ValueError("Vui lòng nhập tên đăng nhập và mật khẩu.")
    with connect() as db:
        row = db.execute(
            "SELECT username, display_name, role, password_hash FROM users WHERE username=?",
            (username,),
        ).fetchone()
    if not row or not verify_password(password, row["password_hash"]):
        return None
    user = {"username": row["username"], "display_name": row["display_name"], "role": row["role"]}
    return user, create_session(row["username"])


def register(username, password, display_name):
    """Đăng ký tài khoản người dân mới. Trả về (user, token). Ném ValueError nếu không hợp lệ."""
    if not all(isinstance(v, str) for v in (username, password, display_name)):
        raise ValueError("Thông tin đăng ký không hợp lệ.")
    username, display_name = username.strip(), display_name.strip()
    if not username or len(username) < 3 or len(username) > 30:
        raise ValueError("Tên đăng nhập cần từ 3 đến 30 ký tự.")
    if not password or len(password) < 6:
        raise ValueError("Mật khẩu cần ít nhất 6 ký tự.")
    if not display_name or len(display_name) > 50:
        raise ValueError("Tên hiển thị cần từ 1 đến 50 ký tự.")
    try:
        with connect() as db:
            db.execute(
                "INSERT INTO users VALUES(?,?,?,?)",
                (username, hash_password(password), display_name, "citizen"),
            )
    except sqlite3.IntegrityError:
        raise ValueError("Tên đăng nhập đã tồn tại.") from None
    user = {"username": username, "display_name": display_name, "role": "citizen"}
    return user, create_session(username)
