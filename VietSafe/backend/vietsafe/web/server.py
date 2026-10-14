"""HTTP handler dựa trên http.server (thư viện chuẩn) + vòng đời máy chủ.

Handler chỉ lo phần "hạ tầng": kiểm tra Host/Origin, đọc body, gọi router, gắn security header,
ghi phản hồi. Mọi logic endpoint nằm ở các controller trong web/controllers/.
"""

import json
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .. import config
from .controllers import router
from .router import Request, Response, authorize
from .static import read_static

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https://tiles.stadiamaps.com https://*.tile.openstreetmap.org; "
    "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
)
# Lỗi nghiệp vụ -> HTTP 400 (thông báo của lỗi được trả cho người dùng).
CLIENT_ERRORS_GET = (ValueError, TypeError)
CLIENT_ERRORS_POST = (ValueError, TypeError, KeyError, UnicodeDecodeError)


class Handler(BaseHTTPRequestHandler):
    server_version = "VietSafe/1.1"

    def log_message(self, fmt, *args):
        # Log gọn: bỏ qua polling snapshot, không in nội dung phản ánh hay vị trí.
        if args and str(args[0]).startswith("GET /api/snapshot"):
            return
        super().log_message(fmt, *args)

    # --- Ghi phản hồi -----------------------------------------------------------------
    def respond(self, data, code=200, content_type="application/json; charset=utf-8", headers=None):
        if content_type.startswith("application/json"):
            payload = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        else:
            payload = data
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header(
            "Cache-Control", "no-store" if self.path.startswith("/api/") else "no-cache"
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", CSP)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send(self, response):
        self.respond(response.body, response.status, response.content_type, response.headers)

    # --- Kiểm tra an ninh -------------------------------------------------------------
    def valid_host(self):
        host = self.headers.get("Host", "")
        port = self.server.server_port
        if host in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return True
        domain = host.split(":")[0].lower()
        return any(domain.endswith(suffix) for suffix in config.ALLOWED_HOST_SUFFIXES)

    def valid_post_origin(self):
        """POST phải có header tùy biến X-VietSafe và (nếu có) Origin cùng nguồn - chống CSRF."""
        port = self.server.server_port
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        allowed = (
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
            f"http://{host}",
            f"https://{host}",
        )
        return (
            self.valid_host()
            and not (origin and origin not in allowed)
            and self.headers.get("X-VietSafe") == "local"
        )

    # --- Điều phối --------------------------------------------------------------------
    def _make_request(self, method, parsed, body=None):
        return Request(
            method, parsed.path, parse_qs(parsed.query), body, self.headers, self.client_address[0]
        )

    def _dispatch(self, req):
        """Tìm route, kiểm tra quyền, gọi handler. Trả về Response, hoặc None nếu không có route."""
        found = router.match(req.method, req.path)
        if not found:
            return None
        route, req.params = found
        denied = authorize(route, req)
        if denied:
            return denied
        result = route.handler(req)
        return result if isinstance(result, Response) else Response(result)

    def do_GET(self):
        if not self.valid_host():
            return self.respond({"error": "Local access only."}, 403)
        parsed = urlparse(self.path)
        try:
            response = self._dispatch(self._make_request("GET", parsed))
            if response:
                return self.send(response)
            if parsed.path.startswith("/api/"):
                return self.respond({"error": "API không tồn tại."}, 404)
            asset = read_static(parsed.path)
            if asset is None:
                return self.respond({"error": "Không tìm thấy tài nguyên."}, 404)
            return self.respond(asset[0], content_type=asset[1])
        except CLIENT_ERRORS_GET as e:
            return self.respond({"error": str(e)}, 400)
        except Exception:
            traceback.print_exc()
            return self.respond(
                {"error": "Lỗi xử lý dữ liệu tại máy. Kiểm tra cửa sổ máy chủ."}, 500
            )

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        if not self.valid_post_origin():
            return self.respond({"error": "Yêu cầu phải được gửi từ website hợp lệ."}, 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > config.MAX_BODY_BYTES:
                return self.respond({"error": "Nội dung quá lớn hoặc trống."}, 413)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("JSON phải là một đối tượng.")
            response = self._dispatch(self._make_request("POST", urlparse(self.path), body))
            if response is None:
                return self.respond({"error": "API không tồn tại."}, 404)
            return self.send(response)
        except CLIENT_ERRORS_POST as e:
            return self.respond({"error": str(e)}, 400)
        except Exception:
            traceback.print_exc()
            return self.respond({"error": "Không thể lưu dữ liệu. Kiểm tra máy chủ."}, 500)


def create_server(host, port):
    """Tạo (chưa chạy) máy chủ HTTP đa luồng. Truyền port=0 để hệ điều hành chọn cổng trống."""
    return ThreadingHTTPServer((host, port), Handler)
