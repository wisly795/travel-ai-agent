"""採購流程測試（不花 API 額度）：用假的 Claude 回應測比價、草稿、核准權限、退回、下單失敗與重送。

在 app 容器內執行：python procurement_test.py
"""
import json
import os
import urllib.error
import urllib.request
from types import SimpleNamespace

from app import agent, procurement
from app.db import query

BASE = "http://localhost:8000"
STAFF = os.environ["STAFF_TOKEN"]
MANAGER = os.environ["MANAGER_TOKEN"]
results = []


def check(name, passed, detail=""):
    results.append(passed)
    print(("PASS" if passed else "FAIL"), name, detail)


def call(method, path, body=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Staff-Token"] = token
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


class Block(SimpleNamespace):
    def model_dump(self, mode="python", exclude_none=False):
        return {k: v for k, v in vars(self).items() if not (exclude_none and v is None)}


def reply(stop_reason, *content):
    usage = SimpleNamespace(input_tokens=2000, output_tokens=400,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return SimpleNamespace(stop_reason=stop_reason, content=list(content), usage=usage)


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = self
        self.beta = self

    def create(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs, default=str)))
        return self.responses.pop(0)


def ai_picks(supplier_name, request_id, extra_first=None):
    """假的 AI：讀請購單、看報價、選指定供應商建立草稿。"""
    offer = next(o for o in procurement.list_offers(request_id) if o["supplier"] == supplier_name)
    script = [
        reply("tool_use", Block(type="tool_use", id="p1", name="get_purchase_request", input={}),
              Block(type="tool_use", id="p2", name="list_offers", input={})),
    ]
    if extra_first:
        script.append(reply("tool_use", Block(type="tool_use", id="p0", name="create_po_draft",
                                              input={"offer_id": extra_first, "reason": "價格最低，先試試看這家"})))
    script += [
        reply("tool_use", Block(type="tool_use", id="p3", name="create_po_draft",
                                input={"offer_id": offer["offer_id"], "reason": f"選擇{supplier_name}：在預算內且房量足夠"})),
        reply("end_turn", Block(type="text", text=f"建議向{supplier_name}訂房。")),
    ]
    agent._client = FakeClient(script)
    return agent._client


def deal(destination, package, hotel, people):
    pkg = query("SELECT id FROM packages WHERE name = %s", (package,))[0]["id"]
    htl = query("SELECT id FROM hotels WHERE name = %s", (hotel,))[0]["id"]
    _, quote = call("POST", "/api/quotes", {"customer_name": "採購測試", "package_id": pkg, "hotel_id": htl, "people": people})
    status, result = call("PATCH", f"/api/quotes/{quote['id']}/status", {"status": "成交"}, STAFF)
    return quote, result["purchase_request"]


def latest_po(request_id):
    return query("SELECT * FROM purchase_orders WHERE request_id = %s ORDER BY id DESC LIMIT 1", (request_id,))[0]


call("POST", "/api/erp/fail-mode", {"on": False}, STAFF)  # 確保從正常狀態開始
# 假 AI 的用量不能算進真實的每日上限：測試期間放寬上限，結束時刪掉測試產生的紀錄
FIRST_TURN = query("SELECT coalesce(max(id), 0) AS n FROM ai_turns")[0]["n"]
agent.DAILY_CHAT_LIMIT, agent.DAILY_COST_LIMIT_USD = 10**6, 10**6

# 1. 成交自動產生請購單，預算是住宿費
quote, pr = deal("沖繩", "海島放鬆 4 日", "海風飯店", 4)
check("成交自動產生請購單", pr["status"] == "待比價" and pr["budget"] == 3200 * 2 * 3, pr["budget"])
offers = procurement.list_offers(pr["id"])
totals = {o["supplier"]: o["total"] for o in offers}
check("三家供應商總價由系統計算", totals == {"東亞旅宿批發": 14400, "海島訂房網": 15360, "飯店直訂": 16320}, totals)

# 2. AI 比價建立草稿（業務即可核准）
client = ai_picks("海島訂房網", pr["id"])
out = procurement.analyze(pr["id"])
check("AI 建立採購單草稿", out["draft"] and out["draft"]["approver_role"] == "業務" and out["draft"]["amount"] == 15360)
check("採購用較強模型與 fallback", client.requests[0]["model"] == procurement.PROCUREMENT_MODEL
      and client.requests[0]["fallbacks"] == "default" and agent.FALLBACK_BETA in client.requests[0]["betas"])
check("比價過程記在 AI 對話紀錄", query("SELECT model FROM ai_turns ORDER BY id DESC LIMIT 1")[0]["model"] == procurement.PROCUREMENT_MODEL)
try:
    procurement.analyze(pr["id"])
    check("待核准時不能重複比價", False)
except procurement.ProcurementError as error:
    check("待核准時不能重複比價", error.status == 400)

# 3. 退回要寫原因，退回後可以重新比價
po = latest_po(pr["id"])
status, _ = call("POST", f"/api/purchase-orders/{po['id']}/decision", {"approve": False}, STAFF)
check("退回沒寫原因被拒絕", status == 400)
status, rejected = call("POST", f"/api/purchase-orders/{po['id']}/decision", {"approve": False, "reason": "想用直訂比較彈性"}, STAFF)
check("退回成功", status == 200 and rejected["status"] == "已退回")
check("退回後請購單回到待比價", query("SELECT status FROM purchase_requests WHERE id = %s", (pr["id"],))[0]["status"] == "待比價")
seen = procurement.request_for_ai(pr["id"])
check("AI 看得到退回原因、看不到舊分析", "ai_analysis" not in seen
      and seen["previous_rejections"][0]["reject_reason"] == "想用直訂比較彈性")
diffs = {o["supplier"]: o["diff_vs_cheapest"] for o in procurement.list_offers(pr["id"])}
check("價差由系統提供", diffs == {"東亞旅宿批發": 0, "海島訂房網": 960, "飯店直訂": 1920}, diffs)

# 4. 重新比價，業務核准下單
ai_picks("飯店直訂", pr["id"])
procurement.analyze(pr["id"])
po = latest_po(pr["id"])
status, ordered = call("POST", f"/api/purchase-orders/{po['id']}/decision", {"approve": True}, STAFF)
check("業務核准並下單", status == 200 and ordered["status"] == "已下單" and ordered["confirmation_no"].startswith("SUP-"), ordered.get("confirmation_no"))
status, _ = call("POST", f"/api/purchase-orders/{po['id']}/decision", {"approve": True}, STAFF)
check("已下單不能再核准", status == 400)

# 5. 大額需要主管核准
quote2, pr2 = deal("京都", "賞楓慢旅 6 日", "庭園溫泉館", 8)
ai_picks("飯店直訂", pr2["id"])
procurement.analyze(pr2["id"])
po2 = latest_po(pr2["id"])
check("大額草稿標記需主管", po2["approver_role"] == "主管" and po2["amount"] >= procurement.MANAGER_THRESHOLD, po2["amount"])
status, _ = call("POST", f"/api/purchase-orders/{po2['id']}/decision", {"approve": True}, STAFF)
check("業務不能核准大額", status == 403)
status, ok = call("POST", f"/api/purchase-orders/{po2['id']}/decision", {"approve": True}, MANAGER)
check("主管可以核准大額", status == 200 and ok["status"] == "已下單")

# 6. 房量不足的供應商不能選（AI 選了會收到錯誤，改選別家）
quote3, pr3 = deal("沖繩", "海島放鬆 4 日", "海風飯店", 14)
wholesale = next(o for o in procurement.list_offers(pr3["id"]) if o["supplier"] == "東亞旅宿批發")
client = ai_picks("飯店直訂", pr3["id"], extra_first=wholesale["offer_id"])
procurement.analyze(pr3["id"])
error_result = client.requests[2]["messages"][-1]["content"][0]
check("房量不足被系統擋下", error_result["is_error"] and "房量不足" in error_result["content"])
check("AI 改選有房量的供應商", latest_po(pr3["id"])["amount"] == 2720 * 7 * 3)

# 7. 供應商故障：下單失敗 → 重送
call("POST", "/api/erp/fail-mode", {"on": True}, STAFF)
po3 = latest_po(pr3["id"])
check("14 人採購金額超過門檻要主管", po3["approver_role"] == "主管", po3["amount"])
status, failed = call("POST", f"/api/purchase-orders/{po3['id']}/decision", {"approve": True}, MANAGER)
check("供應商故障時記錄下單失敗", failed["status"] == "下單失敗" and "503" in failed["last_error"])
status, again = call("POST", f"/api/purchase-orders/{po3['id']}/retry", token=STAFF)
check("故障中重送仍失敗", again["status"] == "下單失敗")
call("POST", "/api/erp/fail-mode", {"on": False}, STAFF)
status, fixed = call("POST", f"/api/purchase-orders/{po3['id']}/retry", token=STAFF)
check("恢復後重送成功", fixed["status"] == "已下單")

# 8. 報價取消：待核准的草稿退回、請購單取消
quote4, pr4 = deal("首爾", "美食首爾 4 日", "星光商旅", 2)
ai_picks("海島訂房網", pr4["id"])
procurement.analyze(pr4["id"])
status, pending = call("GET", "/api/purchase-orders/pending", token=STAFF)
check("待核准清單", status == 200 and any(p["quote_id"] == quote4["id"] for p in pending))
call("PATCH", f"/api/quotes/{quote4['id']}/status", {"status": "取消"}, STAFF)
po4 = latest_po(pr4["id"])
check("報價取消時草稿自動退回", po4["status"] == "已退回" and po4["reject_reason"] == "報價已取消")
check("報價取消時請購單取消", query("SELECT status FROM purchase_requests WHERE id = %s", (pr4["id"],))[0]["status"] == "已取消")

# 9. 出發日期與免費取消期限（H1）：10 天後出發
from datetime import timedelta
from app import quotes as q
pkg = query("SELECT id FROM packages WHERE name = '海島放鬆 4 日'")[0]["id"]
htl = query("SELECT id FROM hotels WHERE name = '海風飯店'")[0]["id"]
dep = q.today() + timedelta(days=10)
_, q5 = call("POST", "/api/quotes", {"customer_name": "期限測試", "package_id": pkg, "hotel_id": htl,
                                     "people": 2, "departure_date": dep.isoformat()})
_, deal5 = call("PATCH", f"/api/quotes/{q5['id']}/status", {"status": "成交"}, STAFF)
pr5 = deal5["purchase_request"]
check("請購單帶出發日期", procurement.get_request(pr5["id"])["days_until_departure"] == 10)
terms = {o["supplier"]: (o["free_cancel_deadline"], o["free_cancel_available_now"]) for o in procurement.list_offers(pr5["id"])}
check("直訂 14 天期限已過", terms["飯店直訂"] == ((dep - timedelta(days=14)).isoformat(), False), terms["飯店直訂"])
check("訂房網 7 天期限還沒過", terms["海島訂房網"] == ((dep - timedelta(days=7)).isoformat(), True), terms["海島訂房網"])
check("批發本來就不能免費取消", terms["東亞旅宿批發"] == (None, False))

# 10. 權限
status, _ = call("POST", f"/api/purchase-orders/{po4['id']}/decision", {"approve": True})
check("未登入不能核准", status == 401)
status, _ = call("GET", "/api/procurement")
check("未登入不能看採購", status == 401)
status, listing = call("GET", "/api/procurement", token=MANAGER)
check("主管權杖也能看後台", status == 200 and len(listing) >= 4)

query("DELETE FROM ai_tool_calls WHERE turn_id > %s RETURNING id", (FIRST_TURN,))
query("DELETE FROM ai_turns WHERE id > %s RETURNING id", (FIRST_TURN,))

print(f"\n{sum(results)}/{len(results)} 通過")
raise SystemExit(0 if all(results) else 1)
