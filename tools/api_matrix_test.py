"""全部 API 掃一遍（不花 API 額度）：權限、錯誤輸入、找不到，以及先前沒有測試直接呼叫的 13 支 API 的正常情況。

在 app 容器內執行：python api_matrix_test.py
第 1 部分不靠人工清單：直接讀程式裡每個路由掛了哪個權限檢查（require_staff／require_admin…），
所以之後新增 API 也會自動被掃到。
"""
import json
import os
import urllib.error
import urllib.request

from app import main
from app.db import query

BASE = "http://localhost:8000"
results = []


def check(name, passed, detail=""):
    passed = bool(passed)
    results.append(passed)
    print(("PASS" if passed else "FAIL"), name, detail)


def call(method, path, body=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw[:1] in (b"{", b"[") else raw)
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            return error.code, json.loads(raw or b"{}")
        except ValueError:
            return error.code, raw


def guards(dependant):
    """這個路由（含巢狀）用到哪些權限檢查函式。"""
    names = set()
    for dep in dependant.dependencies:
        if dep.call is not None:
            names.add(dep.call.__name__)
        names |= guards(dep)
    return names


def login(user, password):
    return call("POST", "/api/auth/login", {"username": user, "password": password})[1]["token"]


sales = {"Authorization": f"Bearer {login('sales', os.environ['SALES_PASSWORD'])}"}
admin = {"Authorization": f"Bearer {login('admin', os.environ['ADMIN_PASSWORD'])}"}

# ---------- 1. 全部路由自動掃描 ----------
routes = []
for route in main.app.routes:
    path = getattr(route, "path", "")
    if not path.startswith("/api/") or not hasattr(route, "dependant"):
        continue
    for method in sorted(route.methods - {"HEAD"}):
        routes.append((method, path, guards(route.dependant)))
print(f"主系統 API：{len(routes)} 支（不含 /partner 子應用與頁面）\n")

server_errors, open_doors, admin_leaks = [], [], []
for method, path, needs in routes:
    url = path
    for name in ("quote_id", "request_id", "po_id", "handoff_id", "user_id", "partner_id", "item_id"):
        url = url.replace("{" + name + "}", "999999")
    url = url.replace("{dataset}", "attractions")
    body = {} if method in ("POST", "PATCH", "PUT") else None
    protected = needs & {"require_staff", "require_admin", "require_automation", "identify"}
    # 沒登入
    status, _ = call(method, url, body)
    if status >= 500:
        server_errors.append(f"{method} {path}（沒登入）→ {status}")
    if protected and status not in (401, 403):
        open_doors.append(f"{method} {path} → {status}")
    # 業務帳號呼叫管理員才能用的 API
    if "require_admin" in needs:
        status, _ = call(method, url, body, sales)
        if status != 403:
            admin_leaks.append(f"{method} {path} → {status}")
    # 有權限、但資料不存在或輸入是空的：可以回 4xx，不可以 500
    if protected and method != "POST" or "999999" in url:
        status, _ = call(method, url, body, admin)
        if status >= 500:
            server_errors.append(f"{method} {path}（管理員、錯誤輸入）→ {status}")

check(f"全部 {len(routes)} 支 API：沒登入、錯誤輸入、不存在的編號，都不會讓系統出錯（500）", not server_errors, server_errors[:5])
check("需要登入的 API 沒登入一律擋下（401／403）", not open_doors, open_doors[:5])
check("管理員專用的 API，業務帳號一律 403", not admin_leaks, admin_leaks[:5])

# ---------- 2. 合作夥伴 API（官網串接） ----------
for method, path in (("GET", "/partner/v1/packages"), ("POST", "/partner/v1/quotes"), ("GET", "/partner/v1/quotes/1")):
    status, _ = call(method, path, {} if method == "POST" else None)
    check(f"合作夥伴 {method} {path} 沒帶金鑰 → 401", status == 401, status)

# ---------- 3. 先前沒有測試直接呼叫的 13 支，測正常情況 ----------
status, body = call("GET", "/api/policies/model")
check("GET /api/policies/model：回傳使用中的向量模型與門檻", status == 200 and "finetuned" in body and body["min_score"] > 0, body)
status, body = call("GET", "/api/explore/cities")
check("GET /api/explore/cities：縣市清單與資料來源", status == 200 and "cities" in body and "觀光署" in body["source"])
status, body = call("GET", "/api/erp/status", headers=sales)
check("GET /api/erp/status：ERP 連線狀態", status == 200 and body.get("status") in ("ok", "error", "down"), body)
status, body = call("GET", "/api/admin/evals", headers=sales)
check("GET /api/admin/evals：評測紀錄（業務可看）", status == 200 and {"running", "latest", "history"} <= set(body))
status, _ = call("POST", "/api/admin/evals/run", {"mode": "single"}, sales)
check("POST /api/admin/evals/run：業務不能執行評測（只有管理員）", status == 403, status)
status, _ = call("POST", "/api/admin/evals/run", {"mode": "nope"}, admin)
check("POST /api/admin/evals/run：模式錯誤回 422（不會真的開始跑、不花錢）", status == 422, status)
status, body = call("GET", "/api/admin/opendata/imports", headers=sales)
check("GET /api/admin/opendata/imports：匯入紀錄", status == 200 and isinstance(body, list))
status, body = call("GET", "/api/admin/crawler/runs", headers=sales)
check("GET /api/admin/crawler/runs：爬蟲紀錄", status == 200 and isinstance(body, list))
status, body = call("GET", "/api/admin/crawler/changes", headers=sales)
check("GET /api/admin/crawler/changes：價格變動", status == 200 and isinstance(body, list))
status, _ = call("POST", "/api/erp/syncs/999999/retry", headers=sales)
check("POST /api/erp/syncs/{id}/retry：不存在的報價回 404", status == 404, status)

# 採購：用既有的請購單測查詢與錯誤處理；不呼叫真的 AI 比價（analyze 會花錢）
existing = query("SELECT id FROM purchase_requests ORDER BY id LIMIT 1")
if existing:
    status, body = call("GET", f"/api/procurement/{existing[0]['id']}/offers", headers=sales)
    check("GET /api/procurement/{id}/offers：三家供應商報價與價差", status == 200 and isinstance(body, (list, dict)), str(body)[:120])
else:
    check("GET /api/procurement/{id}/offers：（沒有請購單，略過）", True)
status, _ = call("GET", "/api/procurement/999999/offers", headers=sales)
check("GET /api/procurement/{id}/offers：不存在回 404", status == 404, status)
status, _ = call("POST", "/api/procurement/999999/analyze", headers=sales)
check("POST /api/procurement/{id}/analyze：不存在回 404（不會呼叫 AI）", status == 404, status)
status, _ = call("POST", "/api/purchase-orders/999999/decision", {"approve": True}, sales)
check("POST /api/purchase-orders/{id}/decision：不存在回 404", status == 404, status)
status, _ = call("POST", "/api/purchase-orders/999999/decision", {"approve": "很好"}, sales)
check("POST /api/purchase-orders/{id}/decision：格式錯誤回 422", status == 422, status)
status, _ = call("POST", "/api/purchase-orders/999999/retry", headers=sales)
check("POST /api/purchase-orders/{id}/retry：不存在回 404", status == 404, status)

print(f"\n{sum(results)}/{len(results)} 通過")
raise SystemExit(0 if all(results) else 1)
