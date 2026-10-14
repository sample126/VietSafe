"""Bảng route tối giản (chỉ dùng thư viện chuẩn).

Mỗi endpoint là một hàm `handler(req) -> dict | Response`, đăng ký bằng decorator:

    @router.post("/api/scenario", auth="admin", deny="Chỉ quản trị viên mới ...")
    def set_scenario(req):
        ...

- `auth=None`   : công khai.
- `auth="user"` : cần đăng nhập, thiếu -> 401 với thông báo `deny`.
- `auth="admin"`: cần vai trò admin, thiếu -> 403 với thông báo `deny`.
- Mẫu đường dẫn hỗ trợ tham số: "/api/reports/{report_id}" -> req.params["report_id"].
"""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .. import auth as auth_service


class Request:
    """Thông tin một request đã được parse. `user` được tra cứu lười (lazy) từ token phiên."""

    def __init__(self, method, path, query, body, headers, client_ip, params=None):
        self.method = method
        self.path = path
        self.query = query  # dict[str, list[str]] như urllib.parse.parse_qs
        self.body = body  # dict (POST) hoặc None
        self.headers = headers
        self.client_ip = client_ip
        self.params = params or {}
        self._user = False  # False = chưa tra cứu (khác None = đã tra, không có user)

    @property
    def session_token(self):
        return self.headers.get("X-VietSafe-Session")

    @property
    def user(self):
        if self._user is False:
            self._user = auth_service.get_user_by_session(self.session_token)
        return self._user

    def arg(self, name, default=""):
        """Giá trị đầu tiên của tham số query `name`."""
        return self.query.get(name, [default])[0]


@dataclass
class Response:
    """Phản hồi tường minh khi cần mã trạng thái / header / kiểu nội dung khác mặc định."""

    body: Any
    status: int = 200
    content_type: str = "application/json; charset=utf-8"
    headers: dict = field(default_factory=dict)


@dataclass
class Route:
    method: str
    pattern: "re.Pattern"
    handler: Callable
    auth: str | None
    deny: str | None


class Router:
    def __init__(self):
        self.routes = []

    def add(self, method, path, handler, auth=None, deny=None):
        regex = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", path)
        self.routes.append(Route(method, re.compile(f"^{regex}$"), handler, auth, deny))
        return handler

    def get(self, path, **kw):
        return lambda fn: self.add("GET", path, fn, **kw)

    def post(self, path, **kw):
        return lambda fn: self.add("POST", path, fn, **kw)

    def match(self, method, path):
        """Trả về (route, params) hoặc None."""
        for route in self.routes:
            if route.method == method:
                m = route.pattern.match(path)
                if m:
                    return route, m.groupdict()
        return None


def authorize(route, req):
    """Trả về Response lỗi nếu request không đủ quyền, ngược lại None."""
    if route.auth == "user" and not req.user:
        return Response({"error": route.deny or "Vui lòng đăng nhập."}, 401)
    if route.auth == "admin" and (not req.user or req.user["role"] != "admin"):
        return Response({"error": route.deny or "Chỉ quản trị viên mới có quyền này."}, 403)
    return None


# Bảng route dùng chung của ứng dụng. Các controller (web/controllers/) đăng ký endpoint vào đây.
# Lưu ý: hãy lấy bảng đã đăng ký đầy đủ qua `from .controllers import router`; import trực tiếp
# từ module này sẽ nhận một bảng còn trống nếu chưa ai nạp các controller.
router = Router()
