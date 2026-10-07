"""Các controller của API: mỗi file nhóm các endpoint theo một chức năng.

| Controller               | Endpoint                                                          |
|--------------------------|-------------------------------------------------------------------|
| `system_controller.py`   | /api/health, /api/snapshot, /api/search, /api/routes              |
| `auth_controller.py`     | /api/auth/login, register, logout, me                             |
| `report_controller.py`   | /api/reports, /api/reports/{id}, /api/report-media/{id}           |
| `admin_controller.py`    | /api/scenario, /api/export/predictions, /api/export/reports       |

Controller chỉ làm việc của tầng HTTP: đọc `req`, gọi nghiệp vụ (service.py / reports.py / auth.py /
core/), rồi trả `dict` hoặc `Response`. KHÔNG viết SQL hay công thức ở đây.

Cách thêm endpoint mới:
  1. Viết logic nghiệp vụ ở service.py / reports.py / core/ (không đụng tới HTTP).
  2. Thêm một hàm vào controller phù hợp với decorator `@router.get(...)` / `@router.post(...)`.
     Chưa có controller phù hợp thì tạo `<tên>_controller.py` mới và nạp nó ở cuối file này.
  3. Khai báo quyền (`auth="user"` / `auth="admin"`) ngay trên decorator.
  4. Thêm test trong backend/tests/ và dòng mô tả trong docs/BACKEND.md.

Quy ước lỗi: ném ValueError (hoặc TypeError/KeyError) với thông báo tiếng Việt để trả HTTP 400;
mọi lỗi khác trả HTTP 500 với thông báo chung (chi tiết chỉ in ra console máy chủ).

Việc nạp các module bên dưới là BẮT BUỘC: decorator chỉ đăng ký route khi module được import.
Vì vậy `server.py` lấy `router` từ đây (`from .controllers import router`), không lấy trực tiếp
từ `router.py`.
"""

from ..router import router
from . import admin_controller, auth_controller, report_controller, system_controller

__all__ = [
    "router",
    "admin_controller",
    "auth_controller",
    "report_controller",
    "system_controller",
]
