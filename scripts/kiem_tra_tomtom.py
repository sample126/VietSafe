import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / "backend"))
"""Check the server-side TomTom configuration without printing the API key.

Use --live for an optional request to the upstream TomTom Traffic API.
"""
import argparse
import os
import sys

from vietsafe.config import load_local_env
from vietsafe.providers.tomtom_traffic import TomTomUnavailable, get_flow_segment


def main():
    parser = argparse.ArgumentParser(description='Kiểm tra cấu hình TomTom của VietSafe')
    parser.add_argument('--live', action='store_true', help='Gọi API TomTom thật một lần')
    args = parser.parse_args()
    load_local_env()
    if not os.environ.get('TOMTOM_API_KEY', '').strip():
        print('THẤT BẠI: Chưa tìm thấy TOMTOM_API_KEY trong môi trường hoặc .env')
        return 1
    print('OK: Máy chủ đã đọc được TOMTOM_API_KEY (giá trị không được hiển thị).')
    if not args.live:
        print('Chưa kiểm tra TomTom trực tiếp. Thêm --live nếu muốn thử API.')
        return 0
    try:
        result = get_flow_segment(21.0285, 105.8542, 15)
    except TomTomUnavailable as exc:
        print(f'CHƯA THÀNH CÔNG: {exc}')
        return 2
    except Exception as exc:
        print(f'LỖI: {type(exc).__name__} trong khi gọi TomTom. Không in khóa API.')
        return 2
    print('THÀNH CÔNG: TomTom trả về số đo đoạn đường gần tọa độ kiểm tra.')
    print('Tốc độ hiện tại:', result.get('current_speed_kmh'), 'km/h')
    print('Tốc độ thông thoáng:', result.get('free_flow_speed_kmh'), 'km/h')
    return 0


if __name__ == '__main__':
    sys.exit(main())
