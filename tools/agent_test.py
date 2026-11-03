"""不花錢測試 AI 客服流程：用假的 Claude 回應，驗證工具迴圈、存檔、限制與錯誤處理。

在 app 容器內執行：python agent_test.py
"""
import json
from types import SimpleNamespace

from app import agent
from app.db import query

results = []


def check(name, passed, detail=""):
    results.append(passed)
    print(("PASS" if passed else "FAIL"), name, detail)


class Block(SimpleNamespace):
    def model_dump(self, mode="python", exclude_none=False):
        return {k: v for k, v in vars(self).items() if not (exclude_none and v is None)}


def text(value):
    return Block(type="text", text=value)


def tool(id, name, input):
    return Block(type="tool_use", id=id, name=name, input=input)


def reply(stop_reason, *content):
    usage = SimpleNamespace(input_tokens=1000, output_tokens=200,
                            cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return SimpleNamespace(stop_reason=stop_reason, content=list(content), usage=usage)


class FakeClient:
    """照順序吐出事先寫好的回應，並記下每次收到的請求。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.messages = self
        self.beta = self

    def create(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs, default=str)))
        return self.responses.pop(0)


def use(responses):
    agent._client = FakeClient(responses)
    return agent._client


okinawa = query("SELECT id FROM packages WHERE name = '海島放鬆 4 日'")[0]["id"]
seaside = query("SELECT id FROM hotels WHERE name = '海風飯店'")[0]["id"]
# 假 AI 的用量不能算進真實的每日上限：測試期間放寬上限，結束時刪掉測試產生的紀錄
FIRST_TURN = query("SELECT coalesce(max(id), 0) AS n FROM ai_turns")[0]["n"]
agent.DAILY_CHAT_LIMIT, agent.DAILY_COST_LIMIT_USD = 10**6, 10**6

# 1. 查行程 → 算報價 → 回答
client = use([
    reply("tool_use", text("我幫您查一下"),
          tool("t1", "search_packages", {"destination": "沖繩", "people": 4, "max_price_per_person": 30000}),
          tool("t2", "list_hotels", {"destination": "沖繩"})),
    reply("tool_use", tool("t3", "calculate_quote", {"package_id": okinawa, "hotel_id": seaside, "people": 4})),
    reply("end_turn", text("海島放鬆 4 日加海風飯店，4 人總價 NT$ 107,200。")),
])
first = agent.chat(None, "4 個人想去沖繩，每人預算 3 萬")
cid = first["conversation_id"]
check("回傳 AI 回覆", first["reply"].startswith("海島放鬆"))
check("記錄使用的工具", first["tools_used"] == ["search_packages", "list_hotels", "calculate_quote"], first["tools_used"])

second_request = client.requests[1]
tool_results = second_request["messages"][-1]["content"]
check("同一輪的工具結果放在同一則訊息", [r["tool_use_id"] for r in tool_results] == ["t1", "t2"])
found = json.loads(tool_results[0]["content"])
check("查行程工具結果正確", {p["name"] for p in found} == {"海島放鬆 4 日", "親子同樂 5 日"}, [p["name"] for p in found])
quote = json.loads(client.requests[2]["messages"][-1]["content"][0]["content"])
check("算報價工具用系統公式", quote["total_price"] == 22000 * 4 + 3200 * 2 * 3 and quote["rooms"] == 2, quote["total_price"])
check("送給 Claude 的設定（含今天日期）", second_request["model"] == agent.CHAT_MODEL
      and second_request["system"].startswith(agent.SYSTEM) and "今天是" in second_request["system"]
      and len(second_request["tools"]) == len(agent.TOOLS))

turn = query("SELECT * FROM ai_turns WHERE conversation_id = %s", (cid,))
calls = query("SELECT tool FROM ai_tool_calls WHERE turn_id = %s ORDER BY id", (turn[0]["id"],))
check("對話紀錄存檔", len(turn) == 1 and turn[0]["input_tokens"] == 3000 and turn[0]["cost_usd"] > 0, turn[0]["cost_usd"])
check("工具呼叫存檔", [c["tool"] for c in calls] == ["search_packages", "list_hotels", "calculate_quote"])

# 2. 同一段對話：客人同意後建立報價
client = use([
    reply("tool_use", tool("t4", "create_quote",
                           {"customer_name": "AI測試客人", "package_id": okinawa, "hotel_id": seaside, "people": 4})),
    reply("end_turn", text("已建立報價單。")),
])
second = agent.chat(cid, "好，就這個，我叫 AI測試客人")
check("延續同一段對話", client.requests[0]["messages"][0]["content"] == "4 個人想去沖繩，每人預算 3 萬")
check("AI 建立的報價", second["quote"] and second["quote"]["total_price"] == 107200, second["quote"])
saved = query("SELECT source FROM quotes WHERE id = %s", (second["quote"]["id"],))[0]
check("報價來源標記為 AI", saved["source"] == "ai")

# 3. AI 給錯參數或亂叫工具，不會出錯，而是回報錯誤給 AI
client = use([
    reply("tool_use", tool("t5", "calculate_quote", {"package_id": okinawa, "hotel_id": seaside, "people": 0}),
          tool("t6", "delete_everything", {})),
    reply("end_turn", text("人數需要 1 到 20 人。")),
])
agent.chat(cid, "0 個人多少錢")
bad = client.requests[1]["messages"][-1]["content"]
check("不合理參數回報錯誤", bad[0]["is_error"] is True)
check("不存在的工具回報錯誤", bad[1]["is_error"] is True and "沒有這個工具" in bad[1]["content"])

# 4. 轉專人
use([
    reply("tool_use", tool("t7", "request_human", {"reason": "客人詢問取消退費"})),
    reply("end_turn", text("已幫您轉給專人。")),
])
agent.chat(cid, "取消可以退多少？")
handoff = query("SELECT * FROM handoffs WHERE conversation_id = %s", (cid,))
check("建立轉接單", len(handoff) == 1 and handoff[0]["status"] == "待處理")

# 5. 新對話第一句就轉專人（對話要先存在）
use([reply("tool_use", tool("t8", "request_human", {"reason": "客訴"})), reply("end_turn", text("好的"))])
fresh = agent.chat(None, "我要客訴")
check("新對話也能轉專人", len(query("SELECT 1 FROM handoffs WHERE conversation_id = %s", (fresh["conversation_id"],))) == 1)

# 6. Claude 拒答
use([reply("refusal")])
refused = agent.chat(cid, "測試拒答")
check("拒答時給固定說明", "轉給專人" in refused["reply"])

# 7. 工具迴圈有上限
use([reply("tool_use", tool(f"loop{i}", "list_destinations", {})) for i in range(agent.MAX_TOOL_ROUNDS)])
looped = agent.chat(None, "一直查")
check("超過步驟上限會停止", "比較多步驟" in looped["reply"] and len(looped["tools_used"]) == agent.MAX_TOOL_ROUNDS)

# 8. 找不到對話、每日上限
try:
    agent.chat("00000000-0000-0000-0000-000000000000", "嗨")
    check("找不到對話", False)
except agent.ChatError as error:
    check("找不到對話", error.status == 404)

limit = agent.DAILY_CHAT_LIMIT
agent.DAILY_CHAT_LIMIT = 0
try:
    agent.chat(None, "嗨")
    check("每日上限", False)
except agent.ChatError as error:
    check("每日上限", error.status == 429)
finally:
    agent.DAILY_CHAT_LIMIT = limit

# 9. RAG 與退費工具
policy, error = agent.run_tool("search_policy", {"question": "行李箱可以帶多重"}, cid)
check("查規定工具回傳條文與出處", not error and any("行李規定 第1條" in r["source"] for r in policy["results"]))
none, error = agent.run_tool("search_policy", {"question": "推薦我好看的電影"}, cid)
check("查不到規定時明確說沒有", not error and none["results"] == [] and "找不到" in none["message"])
refund, error = agent.run_tool("calculate_refund", {"total_price": 107200, "days_before_departure": 7}, cid)
check("退費計算（7 天扣 50%）", not error and refund["refund"] == 53600 and refund["deduct_percent"] == 50)
edges = [(31, 5), (30, 10), (21, 10), (20, 30), (8, 30), (7, 50), (2, 50), (1, 70), (0, 100)]
check("退費級距邊界", all(agent.run_tool("calculate_refund", {"total_price": 10000, "days_before_departure": d}, cid)[0]
                         ["deduct_percent"] == p for d, p in edges))
_, error = agent.run_tool("calculate_refund", {"total_price": 10000, "days_before_departure": -1}, cid)
check("負的天數被拒絕", error)

# 10. 出發日期（H1）
from datetime import timedelta
from app import quotes as q
in7 = (q.today() + timedelta(days=7)).isoformat()
refund, error = agent.run_tool("calculate_refund", {"total_price": 107200, "departure_date": in7}, cid)
check("用出發日期算退費（7 天後扣 50%）", not error and refund["days_before_departure"] == 7 and refund["refund"] == 53600)
_, error = agent.run_tool("calculate_refund", {"total_price": 107200}, cid)
check("退費沒給天數也沒給日期回報錯誤", error)
in30 = (q.today() + timedelta(days=30)).isoformat()
preview, error = agent.run_tool("calculate_quote", {"package_id": okinawa, "hotel_id": seaside, "people": 2,
                                                   "departure_date": in30}, cid)
check("試算帶出發日期算出回程日", not error and preview["days_until_departure"] == 30
      and preview["return_date"] == (q.today() + timedelta(days=33)).isoformat())
_, error = agent.run_tool("calculate_quote", {"package_id": okinawa, "hotel_id": seaside, "people": 2,
                                             "departure_date": q.today().isoformat()}, cid)
check("今天出發被拒絕", error)

# 11. 費用計算：haiku 輸入 1000、輸出 200
usage = SimpleNamespace(input_tokens=1000, output_tokens=200,
                        cache_creation_input_tokens=None, cache_read_input_tokens=None)
check("費用計算", float(agent.turn_cost("claude-haiku-5-5", usage)) == (1000 * 0.10 + 200 * 0.50) / 1_000_000)

query("DELETE FROM ai_tool_calls WHERE turn_id > %s RETURNING id", (FIRST_TURN,))
query("DELETE FROM ai_turns WHERE id > %s RETURNING id", (FIRST_TURN,))

print(f"\n{sum(results)}/{len(results)} 通過")
raise SystemExit(0 if all(results) else 1)
