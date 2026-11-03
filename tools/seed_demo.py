"""建立展示用資料（會花一點 API 額度）：清空測試資料後，用真實流程跑一遍，讓畫面乾淨、有代表性。

在 app 容器內執行：python seed_demo.py
姓名都是虛構的，所有資料皆為模擬資料。過去 13 天的報價是模擬的歷史資料（給儀表板趨勢圖用），
今天的資料則是用真實流程（含真實 AI）產生。
"""
import json
import os
import random
import urllib.request
from datetime import datetime, time, timedelta

from app import erp, quotes
from app.db import connect, query

BASE = "http://localhost:8000"
STAFF = os.environ["STAFF_TOKEN"]
MANAGER = os.environ["MANAGER_TOKEN"]


def call(method, path, body=None, token=STAFF):
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                     method=method, headers={"Content-Type": "application/json", "X-Staff-Token": token})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read())


def chat(conversation_id, message):
    data = call("POST", "/api/chat", {"conversation_id": conversation_id, "message": message})
    print(f"客人：{message}\nAI：{data['reply'][:80]}…  工具：{data['tools_used']}\n")
    return data


def in_days(n):
    return (quotes.today() + timedelta(days=n)).isoformat()


# 1. 清空測試資料（行程、飯店、供應商、規定向量、帳號保留）
with connect() as conn:
    conn.execute("""
        TRUNCATE notifications, purchase_orders, purchase_requests, erp_syncs, quote_events,
                 ai_tool_calls, ai_turns, handoffs, conversations, quotes RESTART IDENTITY CASCADE
    """)
    conn.execute("DELETE FROM sessions")
    conn.execute("TRUNCATE partner_calls")
    conn.execute("DELETE FROM partners WHERE name <> '官網示範'")  # 截圖或測試建立的合作夥伴
    conn.execute("DELETE FROM users WHERE username NOT IN ('admin', 'manager', 'sales')")
erp.call("POST", "/admin/reset", {})
print("已清空測試資料（含模擬 ERP）")

packages = {p["name"]: p for p in call("GET", "/api/packages?people=1")}
hotels = call("GET", "/api/hotels")

# 2. 過去 13 天的模擬歷史報價（固定亂數種子，每次產生一樣的資料）
rng = random.Random(20261103)
surnames = "陳林黃張李王吳劉蔡楊許鄭謝郭洪"
given = "安宇庭晨恩承睿語芯澄"
history = 0
for days_ago in range(13, 0, -1):
    for _ in range(rng.randint(1, 4)):
        package = rng.choice(list(packages.values()))
        hotel = rng.choice([h for h in hotels if h["destination"] == package["destination"]])
        people = rng.choice([2, 2, 3, 4, 4, 6])
        rooms, nights, total = quotes.calculate_quote(package["price_per_person"], hotel["price_per_night"],
                                                      package["days"], people)
        created = datetime.combine(quotes.today() - timedelta(days=days_ago),
                                   time(rng.randint(9, 20), rng.randint(0, 59)), quotes.TAIPEI)
        departure = created.date() + timedelta(days=rng.randint(25, 90))
        roll = rng.random()
        status = "成交" if roll < 0.35 else "取消" if roll < 0.45 else "已報價"
        with connect() as conn:
            q = conn.execute(
                """
                INSERT INTO quotes (customer_name, package_id, hotel_id, people, rooms, nights, total_price,
                                    source, status, departure_date, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (f"{rng.choice(surnames)}○{rng.choice(given)}", package["id"], hotel["id"], people, rooms, nights,
                 total, "ai" if rng.random() < 0.4 else "web", status, departure, created),
            ).fetchone()
            if status != "已報價":
                conn.execute(
                    "INSERT INTO quote_events (quote_id, from_status, to_status, note, changed_by, created_at) "
                    "VALUES (%s, '已報價', %s, '', '示範業務', %s)",
                    (q["id"], status, created + timedelta(hours=rng.randint(2, 30))),
                )
        history += 1
print(f"已建立 {history} 筆過去 13 天的模擬報價")


def web_quote(name, package, hotel, people, depart_in):
    hotel_id = next(h["id"] for h in hotels if h["name"] == hotel)
    return call("POST", "/api/quotes", {"customer_name": name, "package_id": packages[package]["id"],
                                        "hotel_id": hotel_id, "people": people, "departure_date": in_days(depart_in)})


# 3. 今天的網頁報價：王小明，成交 → ERP → 請購單 → AI 比價 → 業務核准下單
q1 = web_quote("王小明", "海島放鬆 4 日", "海風飯店", 3, 40)
pr1 = call("PATCH", f"/api/quotes/{q1['id']}/status", {"status": "成交"})["purchase_request"]
draft1 = call("POST", f"/api/procurement/{pr1['id']}/analyze")["draft"]
call("POST", f"/api/purchase-orders/{draft1['id']}/decision", {"approve": True},
     token=MANAGER if draft1["approver_role"] == "主管" else STAFF)
print("王小明：成交、ERP 同步、採購下單完成")

# 4. AI 客服報價：林小華（推薦 → 明細 → 給出發日期並同意建立）
c = chat(None, "4 個人想去沖繩，每人預算 3 萬，有推薦的嗎？")
c = chat(c["conversation_id"], f"選最便宜的行程和飯店，{in_days(50)} 出發，幫我算總價")
c = chat(c["conversation_id"], "好，就這個，我叫林小華，請建立報價單")
if not c["quote"]:
    c = chat(c["conversation_id"], "確認，請建立")

# 5. 規定問答與轉專人
chat(None, f"我的團費 107,200 元，{in_days(7)} 出發，現在取消可以退多少？")
chat(None, "我想把行程改到下個月，可以嗎？")

# 6. 大額報價：陳大文，成交 → AI 比價 → 等主管核准（留在待核准，展示主管流程）
q3 = web_quote("陳大文", "賞楓慢旅 6 日", "庭園溫泉館", 8, 60)
pr3 = call("PATCH", f"/api/quotes/{q3['id']}/status", {"status": "成交"})["purchase_request"]
call("POST", f"/api/procurement/{pr3['id']}/analyze")
print("陳大文：成交、AI 已比價，等主管核准")

# 7. 一般報價：李美玲（已報價，尚未成交）
web_quote("李美玲", "美食首爾 4 日", "星光商旅", 2, 30)

# 8. 官網串接：用合作夥伴 API（模擬官網的金鑰）建立一筆報價
partner_request = urllib.request.Request(
    BASE + "/partner/v1/quotes", method="POST",
    data=json.dumps({"customer_name": "張○宇", "package_id": packages["慢活台東 4 日"]["id"],
                     "hotel_id": next(h["id"] for h in hotels if h["name"] == "海岸度假屋"),
                     "people": 4, "departure_date": in_days(35)}).encode(),
    headers={"Content-Type": "application/json", "X-API-Key": os.environ["PARTNER_DEMO_KEY"]})
with urllib.request.urlopen(partner_request, timeout=30) as response:
    print("官網串接報價：", json.loads(response.read())["id"])

usage = call("GET", "/api/admin/usage")
print(f"\n展示資料建立完成。今日 AI {usage['turns']} 次，US$ {float(usage['cost_usd']):.4f}")
print("歷史報價：", query("SELECT count(*) AS n FROM quotes WHERE created_at < now() - interval '1 day'")[0]["n"])
