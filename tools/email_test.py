"""H5 Email 通知測試（不花 API 額度）。在 app 容器內執行，分三個步驟（中間由外部執行 n8n 排程流程）：

  python email_test.py prepare   清空信箱、建立新報價、準備待核准採購單與 ERP 失敗 3 次
  （外部）docker exec ... n8n execute --id=每日報表／採購提醒／ERP 重試
  python email_test.py check     檢查信件：收件人、主旨、內容
  （外部）再執行一次三個排程流程
  python email_test.py dedupe    檢查沒有重複寄信
"""
import json
import os
import sys
import time
import urllib.request
from datetime import timedelta

from app import erp, procurement, quotes
from app.db import query

BASE = "http://localhost:8000"
MAIL = "http://mailpit:8025/api/v1"
STAFF = os.environ["STAFF_TOKEN"]
STATE = "/tmp/email_test.json"
results = []


def check(name, passed, detail=""):
    results.append(passed)
    print(("PASS" if passed else "FAIL"), name, detail)


def call(method, url, body=None, token=STAFF):
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Content-Type": "application/json", "X-Staff-Token": token})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {"text": raw.decode(errors="replace")}  # Mailpit 清空信箱時回傳純文字「ok」


def messages():
    return call("GET", f"{MAIL}/messages?limit=100")["messages"]


mode = sys.argv[1]

if mode == "prepare":
    call("DELETE", f"{MAIL}/messages")
    # 讓排程流程這次一定有「新」事件：清掉每日報表與採購、ERP 相關的舊通知
    query("DELETE FROM notifications WHERE kind IN ('每日報表', '採購待核准', '同步失敗') RETURNING id")
    pkg = query("SELECT id FROM packages WHERE name = '慢活台東 4 日'")[0]["id"]
    htl = query("SELECT id FROM hotels WHERE name = '稻浪民宿'")[0]["id"]
    quote = call("POST", f"{BASE}/api/quotes", {"customer_name": "寄信測試", "package_id": pkg, "hotel_id": htl,
                                                "people": 2, "departure_date": (quotes.today() + timedelta(days=30)).isoformat()})
    # 待主管核准的採購單
    big = call("POST", f"{BASE}/api/quotes", {"customer_name": "寄信測試大額", "package_id": 4, "hotel_id": 4, "people": 8,
                                              "departure_date": (quotes.today() + timedelta(days=60)).isoformat()})
    pr = call("PATCH", f"{BASE}/api/quotes/{big['id']}/status", {"status": "成交"})["purchase_request"]
    offer = next(o for o in procurement.list_offers(pr["id"]) if o["supplier"] == "海島訂房網")
    po = procurement.create_draft(pr["id"], offer["offer_id"], "寄信測試用草稿：價格與取消條件平衡")
    # ERP 失敗 3 次
    call("POST", f"{BASE}/api/erp/fail-mode", {"on": True})
    failing = call("POST", f"{BASE}/api/quotes", {"customer_name": "寄信測試ERP", "package_id": pkg, "hotel_id": htl,
                                                  "people": 2, "departure_date": (quotes.today() + timedelta(days=40)).isoformat()})
    call("PATCH", f"{BASE}/api/quotes/{failing['id']}/status", {"status": "成交"})
    erp.push_quote(failing["id"])
    erp.push_quote(failing["id"])
    json.dump({"quote": quote["id"], "po": po["id"], "erp_quote": failing["id"]}, open(STATE, "w"))
    for _ in range(20):
        if any(f"#{quote['id']}" in m["Subject"] for m in messages()):
            break
        time.sleep(0.5)
    print("prepared", json.load(open(STATE)))

elif mode == "check":
    state = json.load(open(STATE))
    mail = messages()
    by_subject = {m["Subject"]: m for m in mail}

    def find(text):
        return next((m for s, m in by_subject.items() if text in s), None)

    new_quote = find(f"新報價 #{state['quote']}")
    check("新報價寄給業務", new_quote and new_quote["To"][0]["Address"] == "sales@travel.example",
          new_quote and new_quote["Subject"])
    if new_quote:
        text = call("GET", f"{MAIL}/message/{new_quote['ID']}")["Text"]
        check("信件內容有金額與後台連結", "NT$" in text and "http://localhost:8100" in text and "模擬信件" in text)
        check("寄件者", new_quote["From"]["Address"] == "noreply@travel.example")
    report = find("每日報表")
    check("每日報表寄給主管", report and report["To"][0]["Address"] == "manager@travel.example")
    po = find(f"採購單 #{state['po']} 待主管核准")
    check("大額採購待核准寄給主管", po and po["To"][0]["Address"] == "manager@travel.example")
    erp_mail = find(f"報價 #{state['erp_quote']} 同步 ERP 已失敗")
    check("ERP 失敗 3 次寄給 IT", erp_mail and erp_mail["To"][0]["Address"] == "it@travel.example",
          erp_mail and erp_mail["Subject"])
    json.dump({**state, "count": len(mail)}, open(STATE, "w"))
    print("信件總數", len(mail))

elif mode == "dedupe":
    state = json.load(open(STATE))
    mail = messages()
    check("排程再跑一次也不重複寄信", len(mail) == state["count"], f"{state['count']} → {len(mail)}")
    call("POST", f"{BASE}/api/erp/fail-mode", {"on": False})
    call("POST", f"{BASE}/api/erp/retry-failed")

print(f"\n{sum(results)}/{len(results)} 通過")
raise SystemExit(0 if all(results) else 1)
