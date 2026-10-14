"""Giới hạn tốc độ theo khóa (ví dụ địa chỉ IP) bằng cửa sổ trượt, trong bộ nhớ.

Lưu ý: khi chạy sau proxy/tunnel (Cloudflare, Render) mọi người dùng có thể chung một IP proxy;
khi cần chính xác hơn hãy đọc header X-Forwarded-For từ proxy tin cậy.
"""

import threading
import time


class SlidingWindowLimiter:
    def __init__(self, limit, window_seconds=60):
        self.limit = limit
        self.window = window_seconds
        self._hits = {}
        self._lock = threading.Lock()

    def allow(self, key):
        """True nếu được phép (và ghi nhận lượt này); False nếu vượt giới hạn."""
        now = time.time()
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if t > now - self.window]
            if len(recent) >= self.limit:
                self._hits[key] = recent
                return False
            self._hits[key] = recent + [now]
            return True

    def reset(self):
        with self._lock:
            self._hits.clear()
