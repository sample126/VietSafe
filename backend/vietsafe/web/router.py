"""HTTP routes, request/response objects and permission checks (stdlib only)."""
from dataclasses import dataclass, field
import re
from typing import Any
from .. import auth

@dataclass
class Response:
    data: Any
    status: int = 200
    content_type: str = 'application/json; charset=utf-8'
    headers: dict = field(default_factory=dict)

@dataclass
class Request:
    method: str
    path: str
    query: dict
    headers: Any
    body: dict | None
    client_ip: str
    user: dict | None = None

class Route:
    def __init__(self, method, pattern, func, role):
        self.method = method
        self.pattern = pattern
        self.func = func
        self.role = role
        # Allow named path parameters, without ever treating a slash as part of one.
        self.regex = re.compile('^' + re.sub(r'<([a-z_]+)>', r'(?P<\1>[^/]+)', pattern) + '$')

ROUTES = []

def route(method, path, role=None):
    """Register a controller; role is None, 'citizen' or 'admin'."""
    def decorator(fn):
        ROUTES.append(Route(method.upper(), path, fn, role))
        return fn
    return decorator

def dispatch(request):
    for entry in ROUTES:
        if entry.method != request.method:
            continue
        match = entry.regex.fullmatch(request.path)
        if not match:
            continue
        if entry.role:
            token=request.headers.get('X-VietSafe-Session')
            request.user=auth.get_user_by_session(token)
            if entry.role=='citizen' and not request.user:
                return Response({'error':'Vui lòng đăng nhập để gửi phản ánh.'},401)
            if entry.role=='admin' and (not request.user or request.user['role']!='admin'):
                return Response({'error':'Chỉ quản trị viên mới có thể thực hiện thao tác này.'},403)
        return entry.func(request, **match.groupdict())
    return Response({'error':'API không tồn tại.'},404)

# Import controllers only after the decorators and registry have been declared.
from .controllers import system, auth as auth_controller, report, admin  # noqa: E402,F401
