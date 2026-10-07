"""Phục vụ file tĩnh của frontend, có chặn path traversal."""

import mimetypes
from urllib.parse import unquote

from .. import config


def read_static(url_path):
    """Trả về (bytes, mime) hoặc None nếu không tồn tại / nằm ngoài thư mục frontend."""
    root = config.FRONTEND_DIR.resolve()
    target = (
        (root / unquote(url_path).lstrip("/")).resolve() if url_path != "/" else root / "index.html"
    )
    if not target.is_relative_to(root) or not target.is_file():
        return None
    mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    if target.suffix == ".js":
        mime = "application/javascript"  # Windows đôi khi trả text/plain làm hỏng ES module
    return target.read_bytes(), mime
