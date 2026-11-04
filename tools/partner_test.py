"""H4 合作夥伴 API 測試（不花 API 額度）。在 app 容器內執行：python partner_test.py"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from app import quotes
from app.db import query

BASE = "http://localhost:8000"
DEMO_KEY = os.environ["PARTNER_DEMO_KEY"]
STAFF = os.environ["STAFF_TOKEN"]
results = []


def check(name, passed, detail=""):
    results.append(passed)
    print(("PASS" if passed else "FAIL"), name, detail)


def call(method, path, body=None, key=None, bearer=None, service=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-API-Key"] = key
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    if service:
        headers["X-Staff-Token"] = service
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read()), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}"), dict(error.headers)


admin = call("POST", "/api/auth/login", {"username": "admin", "password": os.environ["ADMIN_PASSWORD"]})[1]["token"]

# 1. 驗證
status, _, _ = call("GET", "/partner/v1/destinations")
check("沒有金鑰 401", status == 401)
status, _, _ = call("GET", "/partner/v1/destinations", key="pk_fake")
check("假金鑰 401", status == 401)
status, dests, _ = call("GET", "/partner/v1/destinations", key=DEMO_KEY)
check("示範金鑰可以查目的地", status == 200 and "沖繩" in dests)
status, _, _ = call("GET", "/api/quotes", key=DEMO_KEY)
check("合作夥伴金鑰不能進後台", status == 401)

# 2. 查詢與報價
okinawa = urllib.parse.quote("沖繩")  # 網址裡的中文要先編碼
status, pkgs, _ = call("GET", f"/partner/v1/packages?destination={okinawa}&people=2", key=DEMO_KEY)
island = next(p for p in pkgs if p["name"] == "海島放鬆 4 日")
status, hotels, _ = call("GET", f"/partner/v1/hotels?destination={okinawa}", key=DEMO_KEY)
seaside = next(h for h in hotels if h["name"] == "海風飯店")
dep = (quotes.today() + timedelta(days=20)).isoformat()
status, preview, _ = call("POST", "/partner/v1/quotes/preview",
                          {"package_id": island["id"], "hotel_id": seaside["id"], "people": 2, "departure_date": dep}, key=DEMO_KEY)
check("試算由系統計算", status == 200 and preview["total_price"] == 22000 * 2 + 3200 * 1 * 3)
body = {"customer_name": "官網客人", "package_id": island["id"], "hotel_id": seaside["id"], "people": 2, "departure_date": dep}
status, created, _ = call("POST", "/partner/v1/quotes", body, key=DEMO_KEY)
check("建立報價單", status == 201 and created["total_price"] == 53600)
row = query("SELECT source, partner_id FROM quotes WHERE id = %s", (created["id"],))[0]
check("報價來源標記為官網串接", row["source"] == "partner" and row["partner_id"] is not None)
status, _, _ = call("POST", "/partner/v1/quotes", {**body, "departure_date": None}, key=DEMO_KEY)
check("合作夥伴建立報價一定要出發日期", status == 422)
status, _, _ = call("POST", "/partner/v1/quotes", {**body, "departure_date": quotes.today().isoformat()}, key=DEMO_KEY)
check("今天出發被拒絕", status == 400)
status, got, _ = call("GET", f"/partner/v1/quotes/{created['id']}", key=DEMO_KEY)
check("查詢自己的報價單", status == 200 and got["id"] == created["id"])

# 3. 新合作夥伴：金鑰只顯示一次、只存雜湊、看不到別家的報價
status, other, _ = call("POST", "/api/admin/partners", {"name": "測試平台", "rate_limit_per_minute": 3}, bearer=admin)
check("管理員建立合作夥伴並取得金鑰", status == 201 and other["api_key"].startswith("pk_"))
stored = query("SELECT key_hash, key_prefix FROM partners WHERE id = %s", (other["id"],))[0]
check("資料庫只存雜湊", other["api_key"] not in stored["key_hash"] and len(stored["key_prefix"]) == 10)
status, listing, _ = call("GET", "/api/admin/partners", bearer=admin)
check("合作夥伴清單不含金鑰", all("api_key" not in p and "key_hash" not in p for p in listing["partners"]))
status, _, _ = call("GET", f"/partner/v1/quotes/{created['id']}", key=other["api_key"])
check("看不到別家的報價單（回 404）", status == 404)
sales = call("POST", "/api/auth/login", {"username": "sales", "password": os.environ["SALES_PASSWORD"]})[1]["token"]
status, _, _ = call("POST", "/api/admin/partners", {"name": "x"}, bearer=sales)
check("業務不能建立合作夥伴", status == 403)

# 4. 每分鐘呼叫上限（測試平台上限 3 次）
codes = [call("GET", "/partner/v1/destinations", key=other["api_key"])[0] for _ in range(4)]
status, body429, headers = call("GET", "/partner/v1/destinations", key=other["api_key"])
check("前 3 次成功、超過上限回 429", codes[:2] == [200, 200] and 429 in codes + [status], codes + [status])
check("429 附上 Retry-After", headers.get("Retry-After") == "60" or headers.get("retry-after") == "60")
logged = query("SELECT count(*) AS n FROM partner_calls WHERE partner_id = %s AND status = 429", (other["id"],))[0]["n"]
check("被限流的呼叫也有紀錄", logged >= 1)

# 4b. 同時大量呼叫也不能多放（I6 人工驗收問題 7：上限 60 實際放行 69）
status, burst, _ = call("POST", "/api/admin/partners", {"name": "同時呼叫測試", "rate_limit_per_minute": 10}, bearer=admin)
with ThreadPoolExecutor(max_workers=20) as pool:
    burst_codes = list(pool.map(lambda _: call("GET", "/partner/v1/destinations", key=burst["api_key"])[0], range(20)))
check("20 個請求同時送、上限 10：剛好放行 10 次", burst_codes.count(200) == 10 and burst_codes.count(429) == 10,
      f"200×{burst_codes.count(200)}、429×{burst_codes.count(429)}")
pending = query("SELECT count(*) AS n FROM partner_calls WHERE partner_id = %s AND status = 0", (burst["id"],))[0]["n"]
check("紀錄都補上了真正的狀態碼（沒有停在處理中）", pending == 0, f"處理中 {pending} 筆")
query("DELETE FROM partner_calls WHERE partner_id = %s RETURNING id", (burst["id"],))
query("DELETE FROM partners WHERE id = %s RETURNING id", (burst["id"],))

# 5. 停用
call("PATCH", f"/api/admin/partners/{other['id']}", {"is_active": False}, bearer=admin)
status, _, _ = call("GET", "/partner/v1/destinations", key=other["api_key"])
check("停用後金鑰失效", status == 401)

# 6. API 文件
status, spec, _ = call("GET", "/partner/openapi.json")
check("合作夥伴 API 文件", status == 200 and "/v1/quotes" in spec["paths"] and spec["info"]["title"].startswith("旅遊報價系統"))
status, _, _ = call("GET", "/openapi.json")
check("主系統 API 文件仍然關閉", status == 404)

# 清掉測試合作夥伴與測試報價單（不在開發版留下「官網客人」，I6 發現）
query("DELETE FROM notifications WHERE dedupe_key = %s RETURNING id", (f"quote-{created['id']}",))
query("DELETE FROM quote_events WHERE quote_id = %s RETURNING id", (created["id"],))
query("DELETE FROM quotes WHERE id = %s RETURNING id", (created["id"],))
query("DELETE FROM partner_calls WHERE partner_id = %s RETURNING id", (other["id"],))
query("DELETE FROM partners WHERE id = %s RETURNING id", (other["id"],))

print(f"\n{sum(results)}/{len(results)} 通過")
raise SystemExit(0 if all(results) else 1)
