"""用真實 HTTP 請求測試 API。"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
TOKEN = os.environ["STAFF_TOKEN"]
results = []


def call(method, path, body=None, token=None):
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["X-Staff-Token"] = token
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8-sig")
            status = response.status
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8-sig")
        status = error.code
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def check(name, passed, detail=""):
    results.append(passed)
    print(("PASS" if passed else "FAIL"), name, detail)


status, body = call("GET", "/api/health")
check("健康檢查", status == 200 and body["status"] == "ok")

status, destinations = call("GET", "/api/destinations")
check("目的地清單", status == 200 and destinations == sorted(destinations) and len(destinations) == 5, destinations)

status, packages = call("GET", "/api/packages?" + urllib.parse.urlencode({"destination": "沖繩"}))
check("目的地篩選", status == 200 and len(packages) == 2 and all(p["destination"] == "沖繩" for p in packages))

status, cheap = call("GET", "/api/packages?max_price=20000")
check("預算篩選", status == 200 and all(p["price_per_person"] <= 20000 for p in cheap) and len(cheap) == 3)

status, none = call("GET", "/api/packages?people=20&max_price=1000")
check("查無資料回傳空清單", status == 200 and none == [])

status, seats = call("GET", "/api/packages?people=20")
check("名額篩選", status == 200 and all(p["seats_left"] >= 20 for p in seats))

status, injected = call("GET", "/api/packages?" + urllib.parse.urlencode({"destination": "x' OR '1'='1"}))
check("SQL 注入無效", status == 200 and injected == [])

status, hotels = call("GET", "/api/hotels?" + urllib.parse.urlencode({"destination": "沖繩"}))
check("飯店篩選", status == 200 and len(hotels) == 2)

package = next(p for p in packages if p["name"] == "海島放鬆 4 日")
hotel = next(h for h in hotels if h["name"] == "海風飯店")
valid = {"customer_name": "測試客人", "package_id": package["id"], "hotel_id": hotel["id"], "people": 3}
status, quote = call("POST", "/api/quotes", {**valid, "total_price": 1})
expected = 22000 * 3 + 3200 * 2 * 3
check("報價公式", status == 201 and quote["total_price"] == expected, f"{quote.get('total_price')} / {expected}")
check("房間數無條件進位", quote.get("rooms") == 2 and quote.get("nights") == 3)

status, _ = call("POST", "/api/quotes", {**valid, "people": 0})
check("人數 0 被拒絕", status == 422)
status, _ = call("POST", "/api/quotes", {**valid, "people": 21})
check("人數 21 被拒絕", status == 422)
status, _ = call("POST", "/api/quotes", {**valid, "customer_name": "   "})
check("空白姓名被拒絕", status == 422)
status, _ = call("POST", "/api/quotes", {**valid, "package_id": 99999})
check("不存在的行程", status == 404)

kyoto = call("GET", "/api/hotels?" + urllib.parse.urlencode({"destination": "京都"}))[1][0]
status, _ = call("POST", "/api/quotes", {**valid, "hotel_id": kyoto["id"]})
check("目的地不同被拒絕", status == 400)

status, _ = call("POST", "/api/quotes", {**valid, "people": 19})
check("超過剩餘名額被拒絕", status == 400)

status, _ = call("GET", "/api/quotes")
check("未登入不能看報價", status == 401)
status, _ = call("GET", "/api/quotes", token="wrong")
check("錯誤權杖被拒絕", status == 401)
status, _ = call("GET", "/api/quotes/export.csv")
check("未登入不能下載", status == 401)

status, quotes = call("GET", "/api/quotes", token=TOKEN)
check("業務看報價（JOIN）", status == 200 and quotes[0]["package"] == "海島放鬆 4 日" and quotes[0]["hotel"] == "海風飯店")

call("POST", "/api/quotes", {**valid, "customer_name": "=2+3"})
status, csv_text = call("GET", "/api/quotes/export.csv", token=TOKEN)
check("CSV 下載與公式防護", status == 200 and "'=2+3" in csv_text and "編號" in csv_text)

check("CSV 有來源欄位", "來源" in csv_text and "網頁" in csv_text)

# ---- C：報價狀態與 ERP 串接 ----
status, q1 = call("POST", "/api/quotes", valid)
status, deal = call("PATCH", f"/api/quotes/{q1['id']}/status", {"status": "成交"}, token=TOKEN)
check("改成成交並同步 ERP", status == 200 and deal["erp"]["status"] == "成功" and deal["erp"]["erp_order_no"].startswith("ERP-"),
      deal.get("erp"))
status, _ = call("PATCH", f"/api/quotes/{q1['id']}/status", {"status": "成交"}, token=TOKEN)
check("已成交不能再成交", status == 400)
status, again = call("POST", f"/api/erp/syncs/{q1['id']}/retry", token=TOKEN)
check("重送不會在 ERP 重複建單（冪等）", status == 200 and again["erp_order_no"] == deal["erp"]["erp_order_no"]
      and again["attempts"] == 2)
status, _ = call("PATCH", f"/api/quotes/{q1['id']}/status", {"status": "已報價"}, token=TOKEN)
check("不允許的狀態被拒絕", status == 422)
status, _ = call("PATCH", f"/api/quotes/{q1['id']}/status", {"status": "成交"})
check("未登入不能改狀態", status == 401)
status, _ = call("PATCH", "/api/quotes/99999/status", {"status": "成交"}, token=TOKEN)
check("不存在的報價", status == 404)

call("POST", "/api/erp/fail-mode", {"on": True}, token=TOKEN)
status, q2 = call("POST", "/api/quotes", valid)
status, failed = call("PATCH", f"/api/quotes/{q2['id']}/status", {"status": "成交"}, token=TOKEN)
check("ERP 故障時記錄失敗", status == 200 and failed["erp"]["status"] == "失敗" and "503" in failed["erp"]["last_error"])
status, still = call("POST", "/api/erp/retry-failed", token=TOKEN)
check("故障中重送仍失敗", status == 200 and q2["id"] in still["still_failed"])
call("POST", "/api/erp/fail-mode", {"on": False}, token=TOKEN)
status, fixed = call("POST", "/api/erp/retry-failed", token=TOKEN)
check("恢復後重送成功", status == 200 and fixed["succeeded"] >= 1 and q2["id"] not in fixed["still_failed"], fixed)
status, syncs = call("GET", "/api/erp/syncs", token=TOKEN)
row = next(s for s in syncs if s["quote_id"] == q2["id"])
check("同步紀錄次數正確", row["status"] == "成功" and row["attempts"] == 3, row["attempts"])
status, events = call("GET", f"/api/quotes/{q1['id']}/events", token=TOKEN)
check("狀態變更有紀錄", status == 200 and events[0]["to_status"] == "成交")
status, cancel = call("PATCH", f"/api/quotes/{q1['id']}/status", {"status": "取消", "note": "客人改期"}, token=TOKEN)
check("成交後可以取消", status == 200 and cancel["status"] == "取消")
status, _ = call("PATCH", f"/api/quotes/{q1['id']}/status", {"status": "成交"}, token=TOKEN)
check("取消後不能成交", status == 400)

for path in ["/api/erp/syncs", "/api/admin/turns", "/api/admin/usage", "/api/handoffs"]:
    status, _ = call("GET", path)
    check(f"未登入不能看 {path}", status == 401)
status, usage = call("GET", "/api/admin/usage", token=TOKEN)
check("用量統計", status == 200 and {"turns", "cost_usd", "turn_limit", "cost_limit_usd"} <= set(usage))
status, turns = call("GET", "/api/admin/turns", token=TOKEN)
check("AI 對話紀錄", status == 200 and isinstance(turns, list))
status, _ = call("PATCH", "/api/handoffs/99999", {"status": "已處理"}, token=TOKEN)
check("不存在的轉接單", status == 404)

# ---- H1：出發日期 ----
from datetime import date as _date, datetime as _dt, timedelta as _td
from zoneinfo import ZoneInfo
TODAY = _dt.now(ZoneInfo("Asia/Taipei")).date()
d30 = (TODAY + _td(days=30)).isoformat()
status, dated = call("POST", "/api/quotes", {**valid, "departure_date": d30})
check("報價帶出發日期", status == 201 and dated["departure_date"] == d30
      and dated["return_date"] == (TODAY + _td(days=33)).isoformat() and dated["days_until_departure"] == 30)
for label, d in [("今天", TODAY), ("昨天", TODAY - _td(days=1)), ("超過一年", TODAY + _td(days=366))]:
    status, body = call("POST", "/api/quotes", {**valid, "departure_date": d.isoformat()})
    check(f"出發日期{label}被拒絕", status == 400, body.get("detail"))
status, _ = call("POST", "/api/quotes", {**valid, "departure_date": "2026-13-45"})
check("日期格式錯誤被拒絕", status == 422)
status, refund = call("POST", "/api/refunds/calculate", {"total_price": 107200, "departure_date": (TODAY + _td(days=7)).isoformat()})
check("用出發日期算退費", status == 200 and refund["days_before_departure"] == 7 and refund["deduct_percent"] == 50)
status, _ = call("POST", "/api/refunds/calculate", {"total_price": 107200})
check("退費沒給天數也沒給日期被拒絕", status == 400)
status, listing = call("GET", "/api/quotes", token=TOKEN)
check("報價列表有出發日", any(row["departure_date"] == d30 for row in listing))

status, preview = call("POST", "/api/quotes/preview", {k: v for k, v in valid.items() if k != "customer_name"})
check("試算報價不存檔", status == 200 and preview["total_price"] == 85200 and "id" not in preview)
status, refund = call("POST", "/api/refunds/calculate", {"total_price": 107200, "days_before_departure": 7})
check("退費計算 API", status == 200 and refund["refund"] == 53600)
status, _ = call("POST", "/api/refunds/calculate", {"total_price": 107200, "days_before_departure": -1})
check("退費天數不可為負", status == 422)

# ---- H3：儀表板 ----
status, dash = call("GET", "/api/admin/dashboard?days=14", token=TOKEN)
days = [row["day"] for row in dash.get("daily", [])]
check("儀表板資料", status == 200 and {"summary", "daily", "top_packages", "sources"} <= set(dash))
check("每日趨勢 14 天連續且最後一天是今天", len(days) == 14 and days[-1] == TODAY.isoformat()
      and all((_date.fromisoformat(b) - _date.fromisoformat(a)).days == 1 for a, b in zip(days, days[1:])), days[-1:])
check("成交率在 0 到 1 之間", 0 <= dash["summary"]["conversion_rate"] <= 1)
status, _ = call("GET", "/api/admin/dashboard")
check("未登入不能看儀表板", status == 401)
status, _ = call("GET", "/api/admin/dashboard?days=3", token=TOKEN)
check("天數範圍外被拒絕", status == 422)

status, docs = call("GET", "/api/policies")
check("規定文件清單", status == 200 and len(docs) == 6 and sum(len(d["articles"]) for d in docs) == 29)
status, hits = call("GET", "/api/policies/search?" + urllib.parse.urlencode({"q": "充電寶可以放託運嗎"}))
check("向量搜尋找到正確條文", status == 200 and hits and hits[0]["source"].startswith("行李規定 第4條"),
      hits[0]["source"] if hits else hits)
status, hits = call("GET", "/api/policies/search?" + urllib.parse.urlencode({"q": "推薦我好看的電影"}))
check("無關問題沒有結果", status == 200 and hits == [])
status, _ = call("GET", "/api/policies/search?q=")
check("空白搜尋被拒絕", status == 422)

status, chat_status = call("GET", "/api/chat/status")
check("AI 狀態", status == 200 and set(chat_status) == {"enabled", "model"}, chat_status)
status, _ = call("POST", "/api/chat", {"message": "   "})
check("空白訊息被拒絕", status == 422)
status, _ = call("POST", "/api/chat", {"message": "a" * 501})
check("超過 500 字被拒絕", status == 422)
status, _ = call("POST", "/api/chat", {"message": "嗨", "conversation_id": "not-a-uuid"})
check("對話編號格式錯誤被拒絕", status == 422)
if not chat_status["enabled"]:
    status, body = call("POST", "/api/chat", {"message": "嗨"})
    check("沒有金鑰時回 503", status == 503 and "尚未啟用" in body["detail"])

status, _ = call("GET", "/docs")
check("API 文件頁關閉", status == 404)

print(f"\n{sum(results)}/{len(results)} 通過")
sys.exit(0 if all(results) else 1)
