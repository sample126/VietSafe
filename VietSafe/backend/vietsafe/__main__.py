"""Điểm vào: `python -m vietsafe [--host H] [--port P]` (chạy từ thư mục backend/)."""

import argparse

from . import config
from .app import init_app
from .web.server import create_server


def main():
    parser = argparse.ArgumentParser(description="VietSafe - máy chủ demo cục bộ")
    parser.add_argument("--port", type=int, default=config.DEFAULT_PORT)
    parser.add_argument("--host", type=str, default=config.DEFAULT_HOST)
    args = parser.parse_args()

    init_app()
    try:
        server = create_server(args.host, args.port)
    except OSError:
        print(f"Cổng {args.port} đang bận. Thử: python -m vietsafe --port {args.port + 1}")
        raise SystemExit(1) from None

    print(f"VietSafe đang chạy tại http://{args.host}:{args.port}", flush=True)
    print("Chỉ dùng cho demo cục bộ. Nhấn Ctrl+C để dừng.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
