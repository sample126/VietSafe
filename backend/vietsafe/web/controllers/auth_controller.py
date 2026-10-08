"""Endpoint tài khoản: đăng nhập, đăng ký, đăng xuất, thông tin người dùng hiện tại."""

from ... import auth
from ..router import Response, router


@router.post("/api/auth/login")
def login(req):
    result = auth.login(req.body.get("username", ""), req.body.get("password", ""))
    if result is None:
        return Response({"error": "Sai tên đăng nhập hoặc mật khẩu."}, 401)
    user, token = result
    return {"user": user, "token": token}


@router.post("/api/auth/register")
def register(req):
    user, token = auth.register(
        req.body.get("username", ""),
        req.body.get("password", ""),
        req.body.get("display_name", ""),
    )
    return {"user": user, "token": token}


@router.post("/api/auth/logout")
def logout(req):
    if req.session_token:
        auth.delete_session(req.session_token)
    return {"ok": True}


@router.get("/api/auth/me")
def me(req):
    return {"user": req.user}
