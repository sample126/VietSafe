"""Thread-safe, in-memory per-IP sliding-window request limiter."""
import threading
import time

class RateLimiter:
    def __init__(self, limit=10, interval=60):
        self.limit=limit
        self.interval=interval
        self._lock=threading.Lock()
        self._rates={}

    def allow(self, ip):
        now=time.monotonic()
        with self._lock:
            recent=[value for value in self._rates.get(ip,()) if value>now-self.interval]
            if len(recent)>=self.limit:
                self._rates[ip]=recent
                return False
            self._rates[ip]=recent+[now]
            return True

reports_limiter=RateLimiter()
