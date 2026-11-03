"""n8n 自動化流程測試（不花 API 額度）。在 app 容器內執行：python automation_test.py

流程 1 由主系統呼叫 n8n Webhook 觸發；流程 2–4 是排程，用 n8n 指令手動執行一次來測（見 docs/E_測試報告.md）。
這支只負責流程 1 與主系統這一側的 API。
"""
import json
import os
import time
import urllib.error
import urllib.request

from app import procurement
from app.db import query

BASE = "http://localhost:8000"
STAFF = os.environ["STAFF_TOKEN"]
AUTO = os.environ["AUTOMATION_TOKEN"]
results = []


def check(name, passed, detail=""):
    passed = bool(passed)
    results.append(passed)
    print(("PASS" if passed else "FAIL"), name, detail)


def call(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Staff-Token"] = token
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


# 流程 1：建立報價 → 主系統呼叫 n8n → n8n 寫通知
pkg = query("SELECT id FROM packages WHERE name = '慢活台東 4 日'")[0]["id"]
htl = query("SELECT id FROM hotels WHERE name = '稻浪民宿'")[0]["id"]
_, quote = call("POST", "/api/quotes", {"customer_name": "自動化測試", "package_id": pkg, "hotel_id": htl, "people": 2})
found = None
for _ in range(20):
    rows = query("SELECT * FROM notifications WHERE dedupe_key = %s", (f"quote-{quote['id']}",))
    if rows:
        found = rows[0]
        break
    time.sleep(0.5)
check("新報價自動產生通知（經過 n8n）", found is not None and found["kind"] == "新報價", found and found["title"])
check("通知內容正確", found and "自動化測試" in found["title"] and "NT$ 32,200" in found["body"], found and found["body"])

# 主系統 API
key = f"dup-test-{time.time()}"  # 每次執行用新的 key，重跑測試才不會受上次影響
status, created = call("POST", "/api/notifications", {"kind": "測試", "title": "重複測試", "body": "內容", "dedupe_key": key}, AUTO)
status2, again = call("POST", "/api/notifications", {"kind": "測試", "title": "重複測試", "body": "內容", "dedupe_key": key}, AUTO)
check("同一件事只通知一次", created["created"] and not again["created"])
status, _ = call("POST", "/api/notifications", {"kind": "測試", "title": "t", "body": "b"})
check("沒有權杖不能寫通知", status == 401)
status, _ = call("GET", "/api/notifications", token=AUTO)
check("自動化權杖不能看後台通知列表", status == 401)
status, report = call("GET", "/api/reports/daily", token=AUTO)
check("每日報表資料", status == 200 and {"date", "quotes", "deals", "deal_amount", "top_packages", "ai_cost_usd"} <= set(report), report)
status, pending = call("GET", "/api/purchase-orders/pending?older_than_hours=24", token=AUTO)
check("自動化可查待核准", status == 200 and isinstance(pending, list))
status, retry = call("POST", "/api/erp/retry-failed", token=AUTO)
check("自動化可重送 ERP", status == 200 and "still_failed_detail" in retry)
status, _ = call("GET", "/api/procurement", token=AUTO)
check("自動化權杖不能看採購", status == 401)
status, items = call("GET", "/api/notifications", token=STAFF)
check("業務看得到通知", status == 200 and any(i["dedupe_key"] == f"quote-{quote['id']}" for i in items))
call("POST", "/api/notifications/read", {}, STAFF)
check("全部標為已讀", not query("SELECT 1 FROM notifications WHERE NOT is_read"))

print(f"\n{sum(results)}/{len(results)} 通過")
raise SystemExit(0 if all(results) else 1)
