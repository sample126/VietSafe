"""Cấu hình tập trung của backend.

Mọi hằng số "có thể muốn chỉnh" nằm ở đây thay vì rải rác trong code. Các giá trị có thể
ghi đè bằng biến môi trường (xem docs/BACKEND.md, mục "Cấu hình").
"""

import os
from pathlib import Path

# backend/vietsafe/config.py  ->  parents[2] là thư mục gốc của repo.
REPO_ROOT = Path(__file__).resolve().parents[2]

# --- Đường dẫn -------------------------------------------------------------------------
FRONTEND_DIR = Path(os.environ.get("VIETSAFE_FRONTEND_DIR", REPO_ROOT / "frontend"))
# Lưu ý: db.py đọc `config.DB_PATH` mỗi lần mở kết nối, nên test có thể gán lại giá trị này.
DB_PATH = Path(os.environ.get("VIETSAFE_DB", REPO_ROOT / "data" / "vietsafe.sqlite3"))

# --- Máy chủ ---------------------------------------------------------------------------
DEFAULT_HOST = os.environ.get("HOST", "localhost")
DEFAULT_PORT = int(os.environ.get("PORT", 8765))
MAX_BODY_BYTES = 2_200_000  # ~1,5 MB ảnh sau khi mã hóa base64 + phần còn lại của JSON
# Host header được chấp nhận ngoài localhost (tunnel / hosting dùng cho demo).
ALLOWED_HOST_SUFFIXES = (
    ".trycloudflare.com",
    ".loca.lt",
    ".ngrok.io",
    ".ngrok-free.app",
    ".onrender.com",
)

# --- Tài khoản & phiên -----------------------------------------------------------------
SESSION_TTL_SECONDS = 24 * 3600
# Tài khoản demo được tạo lần đầu khởi tạo DB (INSERT OR IGNORE: không ghi đè DB đã có).
# Khi deploy công khai, hãy đặt mật khẩu qua biến môi trường thay vì dùng mặc định.
DEMO_ADMIN_PASSWORD = os.environ.get("VIETSAFE_ADMIN_PASSWORD", "vietsafe2026")
DEMO_CITIZEN_PASSWORD = os.environ.get("VIETSAFE_CITIZEN_PASSWORD", "matkhau123")

# --- Phản ánh cộng đồng ------------------------------------------------------------------
REPORT_TTL_SECONDS = 2 * 3600  # phản ánh tự hết hạn sau 2 giờ
REPORT_DUPLICATE_WINDOW_SECONDS = 300  # chặn gửi lặp cùng nội dung trong 5 phút
REPORT_MAX_IMAGE_BYTES = 1_500_000
REPORT_RATE_LIMIT_PER_MINUTE = 10  # theo địa chỉ IP
REPORT_MAX_DISTANCE_KM = 1  # vị trí phải nằm gần một đoạn đường trong mạng thử nghiệm
# Vùng thử nghiệm nội thành Hà Nội. Frontend có bản sao ở frontend/js/config.js (PILOT_BOUNDS).
PILOT_LAT_RANGE = (20.98, 21.065)
PILOT_LNG_RANGE = (105.77, 105.88)

# --- Nhật ký dự báo --------------------------------------------------------------------
PREDICTION_LOG_RETENTION_TICKS = 8640  # 8640 tick x 10 giây = 24 giờ
PREDICTION_LOG_EXPORT_LIMIT = 500
