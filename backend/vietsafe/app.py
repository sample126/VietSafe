"""Khởi tạo ứng dụng: tạo DB + dữ liệu mặc định. Gọi một lần trước khi phục vụ request."""

from . import auth, db


def init_app():
    db.init_schema()
    auth.seed_demo_users()
