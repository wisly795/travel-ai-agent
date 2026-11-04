"""簡單壓力測試（不花 API 額度，不呼叫 AI）：模擬多人同時逛網站，看回應時間與錯誤。

python load_test.py <網址> [Host 標頭]
20 個人同時、持續 60 秒，混合：首頁、查行程、試算報價、查景點、搜尋規定。
標準：沒有錯誤；一般 API 的 P95 在 2 秒內（搜尋規定要算向量，放寬到 3 秒）。
"""
import json
import statistics
import sys
import threading
import time
import urllib.parse
import urllib.request
from collections import defaultdict

BASE = sys.argv[1].rstrip("/")
HOST = sys.argv[2] if len(sys.argv) > 2 else None
USERS, SECONDS = 20, 60
CITY = urllib.parse.quote("花蓮縣")
ACTIONS = [
    ("首頁", "GET", "/", None),
    ("查行程", "GET", "/api/packages?people=2", None),
    ("試算報價", "POST", "/api/quotes/preview", {"package_id": 1, "hotel_id": 1, "people": 4}),
    ("查景點", "GET", f"/api/explore/attractions?city={CITY}&limit=12", None),
    ("搜尋規定", "GET", "/api/policies/search?q=" + urllib.parse.quote("出發前一週取消退多少"), None),
]
LIMITS = {"搜尋規定": 3.0}
times, errors = defaultdict(list), defaultdict(int)
lock = threading.Lock()
stop = time.monotonic() + SECONDS


def user(n):
    i = n
    while time.monotonic() < stop:
        name, method, path, body = ACTIONS[i % len(ACTIONS)]
        i += 1
        headers = {"Content-Type": "application/json"}
        if HOST:
            headers["Host"] = HOST
        request = urllib.request.Request(BASE + path, method=method, headers=headers,
                                         data=json.dumps(body).encode() if body else None)
        start = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response.read()
                ok = response.status < 400
        except Exception:
            ok = False
        with lock:
            times[name].append(time.monotonic() - start)
            if not ok:
                errors[name] += 1


threads = [threading.Thread(target=user, args=(n,)) for n in range(USERS)]
for t in threads:
    t.start()
for t in threads:
    t.join()

total = sum(len(v) for v in times.values())
print(f"{USERS} 人同時、{SECONDS} 秒：共 {total} 次請求（每秒約 {total / SECONDS:.0f} 次），錯誤 {sum(errors.values())} 次")
print(f"{'動作':8s} {'次數':>6s} {'P50':>7s} {'P95':>7s} {'最慢':>7s} 錯誤")
passed = not errors
for name, *_ in ACTIONS:
    v = sorted(times[name])
    p95 = v[int(len(v) * 0.95) - 1]
    print(f"{name:8s} {len(v):6d} {statistics.median(v):6.2f}s {p95:6.2f}s {v[-1]:6.2f}s {errors[name]}")
    passed &= p95 <= LIMITS.get(name, 2.0)
print("壓力測試：" + ("通過" if passed else "未達標準"))
raise SystemExit(0 if passed else 1)
