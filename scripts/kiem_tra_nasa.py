import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "backend"))
"""Kiểm tra cấu hình NASA Earthdata mà không tiết lộ access token."""
import argparse
import base64
from datetime import datetime, timezone
import json
import os

from vietsafe.config import load_local_env


def token_expiration(token):
    """Đọc hạn dùng từ JWT (không xác minh chữ ký hay quyền truy cập)."""
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        middle = parts[1]
        padded = middle + ('=' * (-len(middle) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded))
        exp = payload.get('exp')
        return datetime.fromtimestamp(exp, timezone.utc) if isinstance(exp, int) else None
    except (ValueError, TypeError, OverflowError):
        return None


def main():
    parser = argparse.ArgumentParser(description='Kiểm tra cấu hình NASA Earthdata cho VietSafe')
    parser.add_argument('--online', action='store_true', help='Thử tải granule IMERG thật từ NASA')
    args = parser.parse_args()

    load_local_env()
    token = os.environ.get('NASA_EARTHDATA_TOKEN', '').strip()
    if not token:
        print('CHƯA CẤU HÌNH: thiếu NASA_EARTHDATA_TOKEN trong môi trường hoặc .env.')
        return 2
    print('NASA_EARTHDATA_TOKEN: đã được cấu hình (nội dung được ẩn).')
    expiration = token_expiration(token)
    if expiration is not None:
        print('Thời điểm hết hạn theo JWT (UTC):', expiration.strftime('%Y-%m-%d %H:%M:%S'))
        if expiration <= datetime.now(timezone.utc):
            print('TOKEN HẾT HẠN. Hãy tạo token mới tại NASA Earthdata Login.')
            return 2
        print('Trạng thái thời hạn: chưa hết hạn theo JWT (chưa xác thực với NASA).')
    else:
        print('Không đọc được thời hạn; chỉ thử trực tuyến mới kiểm tra được quyền truy cập.')
    if args.online:
        from vietsafe.providers.nasa_gpm import GpmUnavailable, get_latest_rainfall
        print('Đang thử tải dữ liệu NASA GPM thật...')
        try:
            grid = get_latest_rainfall(force=True)
        except (GpmUnavailable, OSError) as error:
            print('KHÔNG LẤY ĐƯỢC DỮ LIỆU NASA:', error)
            return 1
        print('KẾT NỐI THÀNH CÔNG; số ô mưa:', len(grid['cells']))
        print('Thời điểm dữ liệu:', grid.get('time_start', 'Không rõ'))
    else:
        print('Chưa thử quyền truy cập NASA. Dùng --online để kiểm tra.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
