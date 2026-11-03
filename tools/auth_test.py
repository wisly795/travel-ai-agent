"""H2 帳號登入測試（不花 API 額度）。在 app 容器內執行：python auth_test.py"""
import json
import os
import time
import urllib.error
import urllib.request

from app.db import query

BASE = "http://localhost:8000"
results = []
SALES, MANAGER, ADMIN = (os.environ[k] for k in ("SALES_PASSWORD", "MANAGER_PASSWORD", "ADMIN_PASSWORD"))


def check(name, passed, detail=""):
    results.append(passed)
    print(("PASS" if passed else "FAIL"), name, detail)


def call(method, path, body=None, bearer=None, service=None):
    headers = {"Content-Type": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    if service:
        headers["X-Staff-Token"] = service
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8-sig")
            return response.status, (json.loads(raw) if raw.startswith(("{", "[")) else raw)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def login(username, password):
    return call("POST", "/api/auth/login", {"username": username, "password": password})


# 1. 基本登入
status, body = login("sales", "wrong-password1")
check("密碼錯誤 401", status == 401 and body["detail"] == "帳號或密碼不正確")
status, body = login("nobody", "whatever123")
check("帳號不存在也回一樣的訊息（不透露帳號是否存在）", status == 401 and body["detail"] == "帳號或密碼不正確")
status, sales = login("sales", SALES)
check("業務登入成功", status == 200 and sales["user"]["role"] == "業務" and len(sales["token"]) > 30)
status, me = call("GET", "/api/auth/me", bearer=sales["token"])
check("查詢目前登入者", status == 200 and me["username"] == "sales")
status, _ = call("GET", "/api/quotes", bearer=sales["token"])
check("用登入工作階段看報價", status == 200)
status, _ = call("GET", "/api/quotes", bearer="not-a-real-token")
check("假的工作階段被拒絕", status == 401)
status, _ = call("GET", "/api/quotes", service=os.environ["AUTOMATION_TOKEN"])
check("自動化權杖不能進後台", status == 401)

# 2. 密碼不是明碼存放、工作階段只存雜湊
row = query("SELECT password_hash FROM users WHERE username = 'sales'")[0]
check("資料庫存的是雜湊不是密碼", SALES not in row["password_hash"] and row["password_hash"].startswith("pbkdf2_sha256$"))
check("資料庫找不到原始工作階段", not query("SELECT 1 FROM sessions WHERE token_hash = %s", (sales["token"],)))

# 3. 角色權限
status, _ = call("GET", "/api/admin/users", bearer=sales["token"])
check("業務不能管理帳號", status == 403)
status, admin = login("admin", ADMIN)
status, users = call("GET", "/api/admin/users", bearer=admin["token"])
check("管理員看得到帳號清單", status == 200 and {"admin", "manager", "sales"} <= {u["username"] for u in users})
check("帳號清單不含密碼", all("password_hash" not in u for u in users))

# 4. 新增帳號：弱密碼、格式、重複
suffix = str(int(time.time()))[-6:]
name = f"tester{suffix}"
status, body = call("POST", "/api/admin/users", {"username": name, "display_name": "測試帳號", "role": "業務",
                                                  "password": "short"}, bearer=admin["token"])
check("弱密碼被拒絕", status == 400 and "8 碼" in body["detail"])
status, _ = call("POST", "/api/admin/users", {"username": "Bad Name", "display_name": "x", "role": "業務",
                                               "password": "abcd1234"}, bearer=admin["token"])
check("帳號格式錯誤被拒絕", status == 400)
status, _ = call("POST", "/api/admin/users", {"username": name, "display_name": "x", "role": "老闆",
                                               "password": "abcd1234"}, bearer=admin["token"])
check("不存在的角色被拒絕", status == 400)
status, created = call("POST", "/api/admin/users", {"username": name, "display_name": "測試帳號", "role": "業務",
                                                     "password": "abcd1234"}, bearer=admin["token"])
check("新增帳號成功", status == 201 and created["username"] == name)
status, _ = call("POST", "/api/admin/users", {"username": name, "display_name": "x", "role": "業務",
                                               "password": "abcd1234"}, bearer=admin["token"])
check("重複帳號被拒絕", status == 409)

# 5. 連續失敗鎖定
for _ in range(4):
    login(name, "wrongpass1")
status, body = login(name, "wrongpass1")
check("第 5 次錯誤鎖定帳號", status == 423)
status, _ = login(name, "abcd1234")
check("鎖定中密碼正確也不能登入", status == 423)
status, _ = call("PATCH", f"/api/admin/users/{created['id']}", {"password": "newpass99"}, bearer=admin["token"])
status, newbie = login(name, "newpass99")
check("管理員重設密碼後解鎖並可登入", status == 200)

# 6. 停用帳號：馬上登出、不能再登入
call("PATCH", f"/api/admin/users/{created['id']}", {"is_active": False}, bearer=admin["token"])
status, _ = call("GET", "/api/quotes", bearer=newbie["token"])
check("停用後原本的工作階段立即失效", status == 401)
status, body = login(name, "newpass99")
check("停用的帳號不能登入", status == 403)
admin_id = next(u["id"] for u in users if u["username"] == "admin")
status, _ = call("PATCH", f"/api/admin/users/{admin_id}", {"is_active": False}, bearer=admin["token"])
check("管理員不能停用自己", status == 400)

# 7. 登出
status, _ = call("POST", "/api/auth/logout", bearer=sales["token"])
status2, _ = call("GET", "/api/quotes", bearer=sales["token"])
check("登出後工作階段失效", status == 200 and status2 == 401)

# 8. 操作者紀錄與核准權限
status, sales = login("sales", SALES)
pkg = query("SELECT id FROM packages WHERE name = '美食首爾 4 日'")[0]["id"]
htl = query("SELECT id FROM hotels WHERE name = '星光商旅'")[0]["id"]
_, quote = call("POST", "/api/quotes", {"customer_name": "操作者測試", "package_id": pkg, "hotel_id": htl, "people": 2})
call("PATCH", f"/api/quotes/{quote['id']}/status", {"status": "成交"}, bearer=sales["token"])
event = query("SELECT changed_by FROM quote_events WHERE quote_id = %s", (quote["id"],))[0]
check("狀態變更記錄操作者", event["changed_by"] == "示範業務", event["changed_by"])
pending = query("SELECT id FROM purchase_orders WHERE status = '待核准' ORDER BY id DESC LIMIT 1")
if pending:
    status, _ = call("POST", f"/api/purchase-orders/{pending[0]['id']}/decision", {"approve": True}, bearer=admin["token"])
    check("管理員不能核准採購", status == 403)

# 9. 登入紀錄
events = query("SELECT * FROM login_events WHERE username = %s ORDER BY id", (name,))
check("登入紀錄有成功與失敗", any(e["success"] for e in events) and sum(not e["success"] for e in events) >= 5)
status, logs = call("GET", "/api/admin/login-events", bearer=admin["token"])
check("管理員看得到登入紀錄", status == 200 and len(logs) > 0)

# 清掉測試帳號
query("DELETE FROM sessions WHERE user_id = %s RETURNING user_id", (created["id"],))
query("DELETE FROM users WHERE id = %s RETURNING id", (created["id"],))

print(f"\n{sum(results)}/{len(results)} 通過")
raise SystemExit(0 if all(results) else 1)
