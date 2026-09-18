import sys
from pathlib import Path
sys.path.insert(0, r"f:\Data for Life\vietsafe-local")
import threading
import time
import json
import urllib.request
import urllib.error
from server import Handler, ThreadingHTTPServer, init_db

PORT = 8769
BASE_URL = f"http://127.0.0.1:{PORT}"

def request(path, method="GET", body=None, headers=None):
    url = BASE_URL + path
    h = {"X-VietSafe": "local", "Origin": BASE_URL}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if body is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read()
            return resp.status, json.loads(content.decode("utf-8"))
    except urllib.error.HTTPError as e:
        content = e.read()
        try:
            return e.code, json.loads(content.decode("utf-8"))
        except:
            return e.code, content.decode("utf-8")

def main():
    init_db()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)

    print("=== Testing VietSafe APIs ===")

    # 1. Health check
    status, res = request("/api/health")
    assert status == 200, f"Health check failed: {status} {res}"
    print("[PASS] Health check:", res.get("ok"))

    # 2. GET /api/auth/me (no session)
    status, res = request("/api/auth/me")
    assert status == 200 and res.get("user") is None, f"Expected null user: {res}"
    print("[PASS] Anonymous /api/auth/me returns null")

    # 3. POST /api/auth/login invalid
    status, res = request("/api/auth/login", method="POST", body={"username": "admin", "password": "wrong"})
    assert status == 401, f"Expected 401, got {status} {res}"
    print("[PASS] Invalid password returns 401")

    # 4. POST /api/auth/login as citizen
    status, res = request("/api/auth/login", method="POST", body={"username": "nguoidan", "password": "matkhau123"})
    assert status == 200 and "token" in res, f"Login failed: {res}"
    citizen_token = res["token"]
    print("[PASS] Login as citizen:", res["user"])

    # 5. Citizen attempts admin action (change scenario) -> should be 403
    status, res = request("/api/scenario", method="POST", body={"scenario": "heavy_rain"}, headers={"X-VietSafe-Session": citizen_token})
    assert status == 403, f"Expected 403 for citizen changing scenario, got {status}: {res}"
    print("[PASS] Citizen blocked from changing scenario (403)")

    # 6. Anonymous attempts report creation -> 401
    status, res = request("/api/reports", method="POST", body={"type": "flood", "severity": 2, "lat": 21.025, "lng": 105.83, "description": "Test report without auth"})
    assert status == 401, f"Expected 401 for anonymous report, got {status}: {res}"
    print("[PASS] Anonymous blocked from submitting report (401)")

    # 7. Citizen submits valid report
    status, res = request("/api/reports", method="POST", body={
        "type": "flood",
        "severity": 2,
        "lat": 21.0285,
        "lng": 105.8355,
        "address": "Phố Giảng Võ",
        "description": "Nước ngập nửa bánh xe, xe máy đi lại khó khăn"
    }, headers={"X-VietSafe-Session": citizen_token})
    assert status == 201, f"Expected 201 for citizen report, got {status}: {res}"
    report_id = res["id"]
    print("[PASS] Citizen created report successfully:", report_id)

    # 8. Citizen attempts to review/verify report -> should be 403
    status, res = request(f"/api/reports/{report_id}", method="POST", body={"status": "verified"}, headers={"X-VietSafe-Session": citizen_token})
    assert status == 403, f"Expected 403 for citizen review, got {status}: {res}"
    print("[PASS] Citizen blocked from reviewing reports (403)")

    # 9. POST /api/auth/login as admin
    status, res = request("/api/auth/login", method="POST", body={"username": "admin", "password": "vietsafe2026"})
    assert status == 200 and "token" in res, f"Admin login failed: {res}"
    admin_token = res["token"]
    print("[PASS] Login as admin:", res["user"])

    # 10. Admin reviews/verifies report -> 200
    status, res = request(f"/api/reports/{report_id}", method="POST", body={"status": "verified"}, headers={"X-VietSafe-Session": admin_token})
    assert status == 200 and res.get("status") == "verified", f"Admin review failed: {res}"
    print("[PASS] Admin verified report successfully")

    # 11. Admin changes scenario -> 200
    status, res = request("/api/scenario", method="POST", body={"scenario": "storm"}, headers={"X-VietSafe-Session": admin_token})
    assert status == 200, f"Admin change scenario failed: {res}"
    print("[PASS] Admin changed scenario to storm")

    # 12. Register new user
    new_user = f"user_{int(time.time())}"
    status, res = request("/api/auth/register", method="POST", body={
        "username": new_user,
        "password": "password123",
        "display_name": "Người dùng mới"
    })
    assert status == 200 and "token" in res, f"Registration failed: {res}"
    print("[PASS] Registered new user:", res["user"])

    # 13. Logout
    status, res = request("/api/auth/logout", method="POST", body={}, headers={"X-VietSafe-Session": admin_token})
    assert status == 200, f"Logout failed: {res}"
    status, res = request("/api/auth/me", headers={"X-VietSafe-Session": admin_token})
    assert res.get("user") is None, f"Expected user to be None after logout, got: {res}"
    print("[PASS] Admin logged out successfully")

    server.shutdown()
    print("\nALL 13 TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    main()
