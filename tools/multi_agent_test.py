"""不花錢測試多 Agent 協作（LangGraph）：用假的 Claude 回應，驗證分流、平行專員、檢查員退回重答與轉專人。

在 app 容器內執行：python multi_agent_test.py
"""
import json
import threading
from types import SimpleNamespace

from app import agent, multi_agent
from app.db import query

results = []


def check(name, passed, detail=""):
    passed = bool(passed)
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
    usage = SimpleNamespace(input_tokens=500, output_tokens=100, cache_creation_input_tokens=0, cache_read_input_tokens=0)
    return SimpleNamespace(stop_reason=stop_reason, content=list(content), usage=usage)


def route(*agents, **tasks):
    tasks = tasks or {a: f"{a} 的測試問題" for a in agents}
    return reply("tool_use", tool("r", "route", {"tasks": tasks, "reason": "測試"}))


class FakeClient:
    """依「是哪一位 Agent 在問」吐出事先寫好的回應（專員可能平行執行，不能只靠順序）。"""

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.requests = []
        self.lock = threading.Lock()
        self.messages = self
        self.beta = self

    def who(self, kwargs):
        if kwargs.get("tool_choice", {}).get("name") == "route":
            return "router"
        for key, (_, _, role) in multi_agent.ROLES.items():
            if kwargs["system"].endswith(role):
                return key
        return "?"

    def create(self, **kwargs):
        with self.lock:
            who = self.who(kwargs)
            self.requests.append((who, json.loads(json.dumps(kwargs, default=str))))
            return self.script[who].pop(0)


def use(script):
    agent._client = FakeClient(script)
    return agent._client


okinawa = query("SELECT id FROM packages WHERE name = '海島放鬆 4 日'")[0]["id"]
seaside = query("SELECT id FROM hotels WHERE name = '海風飯店'")[0]["id"]
FIRST_TURN = query("SELECT coalesce(max(id), 0) AS n FROM ai_turns")[0]["n"]
agent.DAILY_CHAT_LIMIT, agent.DAILY_COST_LIMIT_USD = 10**6, 10**6
total = 22000 * 4 + 3200 * 2 * 3

# 1. 只問報價：分流 → 報價專員 → 檢查通過
client = use({
    "router": [route("quote")],
    "quote": [reply("tool_use", tool("q1", "calculate_quote", {"package_id": okinawa, "hotel_id": seaside, "people": 4})),
              reply("end_turn", text(f"海島放鬆 4 日加海風飯店，4 人總價 NT$ {total:,}。"))],
})
first = multi_agent.chat(None, "4 個人去沖繩住海風飯店多少錢")
cid = first["conversation_id"]
check("報價題交給報價專員", [p["agent"] for p in first["agents"]] == ["分流", "報價專員", "檢查員", "組合回覆"], first["agents"])
check("回覆是報價專員的回答", f"NT$ {total:,}" in first["reply"])
quote_req = next(r for w, r in client.requests if w == "quote")
check("報價專員只拿到報價相關工具", {t["name"] for t in quote_req["tools"]} == set(multi_agent.ROLES["quote"][1]))
check("分流強制使用 route 工具", client.requests[0][1]["tool_choice"] == {"type": "tool", "name": "route"})
turn = query("SELECT * FROM ai_turns WHERE conversation_id = %s", (cid,))[0]
calls = query("SELECT tool, agent FROM ai_tool_calls WHERE turn_id = %s", (turn["id"],))
check("存檔：經過的 Agent 與模型標示", len(turn["agent_path"]) == 4 and "多 Agent" in turn["model"], turn["model"])
check("存檔：工具記錄是哪位專員呼叫", calls == [{"tool": "calculate_quote", "agent": "報價專員"}], calls)
check("費用加總分流與專員", turn["input_tokens"] == 1500, turn["input_tokens"])

# 2. 同時問報價與規定：兩位專員平行，各答各的再合併
client = use({
    "router": [route(quote="再說一次剛才的價格", policy="出發前一週取消扣多少")],
    "quote": [reply("end_turn", text(f"剛才的報價是 NT$ {total:,}。"))],
    "policy": [reply("tool_use", tool("p1", "search_policy", {"question": "出發前一週取消"})),
               reply("end_turn", text("出發前 2 至 7 天取消扣團費 50%（取消與退費規定 第3條）。"))],
})
both = multi_agent.chat(cid, "再說一次價格，還有出發前一週取消扣多少")
names = [p["agent"] for p in both["agents"]]
check("報價與規定兩位專員都有執行", "報價專員" in names and "規定專員" in names, names)
check("合併順序：先報價後規定", both["reply"].index("NT$") < both["reply"].index("第3條"), both["reply"])
asked = {w: r["messages"][-1]["content"] for w, r in client.requests if w in ("quote", "policy")
         and isinstance(r["messages"][-1]["content"], str)}
check("每位專員拿到分給自己的問題，並附客人原話供核對數字",
      asked["quote"].startswith("再說一次剛才的價格") and asked["policy"].startswith("出發前一週取消扣多少")
      and all("客人原話" in q for q in asked.values()), asked)
check("第二輪看得到上一輪紀錄（含工具摘要）",
      any("系統紀錄" in m["content"] for w, r in client.requests if w == "quote" for m in r["messages"] if m["role"] == "assistant"))

# 3. 檢查員：金額不在工具結果裡 → 退回重答一次 → 改對就通過
client = use({
    "router": [route("quote")],
    "quote": [reply("tool_use", tool("q2", "calculate_quote", {"package_id": okinawa, "hotel_id": seaside, "people": 4})),
              reply("end_turn", text("4 人總價 NT$ 99,999。")),
              reply("tool_use", tool("q3", "calculate_quote", {"package_id": okinawa, "hotel_id": seaside, "people": 4})),
              reply("end_turn", text(f"更正：4 人總價 NT$ {total:,}。"))],
})
fixed = multi_agent.chat(None, "4 個人去沖繩多少")
names = [p["agent"] for p in fixed["agents"]]
check("金額錯誤被檢查員擋下並退回", names.count("報價專員") == 2 and "99,999" in fixed["agents"][2]["detail"], names)
check("重答後送出正確金額", f"NT$ {total:,}" in fixed["reply"] and "99,999" not in fixed["reply"], fixed["reply"])
retry_req = [r for w, r in client.requests if w == "quote"][2]
check("退回時把問題寫給專員", "系統檢查員" in retry_req["messages"][-1]["content"])

# 4. 改了還是錯 → 不把錯的金額給客人，改成轉專人
client = use({
    "router": [route("quote")],
    "quote": [reply("end_turn", text("總價 NT$ 12,345。")), reply("end_turn", text("總價 NT$ 54,321。"))],
})
blocked = multi_agent.chat(None, "多少錢")
check("兩次都錯就改成轉專人", "轉接單" in blocked["reply"] and "NT$" not in blocked["reply"], blocked["reply"])
check("轉接單有寫原因", query("SELECT 1 FROM handoffs WHERE conversation_id = %s AND reason LIKE '多 Agent 檢查未通過%%'",
                            (blocked["conversation_id"],)))

# 4b. 客人自己說的預算（「3 萬」）被 AI 寫成 NT$ 30,000，不算亂編（真實評測發現的誤判，見錯誤紀錄 I3-1）
use({
    "router": [route("quote")],
    "quote": [reply("end_turn", text("您每人預算 NT$ 30,000，沖繩有符合的行程。"))],
})
budget = multi_agent.chat(None, "4 個人想去沖繩，每人預算 3 萬")
check("客人自己說的預算金額不會被誤判", [p["agent"] for p in budget["agents"]].count("報價專員") == 1
      and "NT$ 30,000" in budget["reply"], budget["agents"][2]["detail"])

# 4c. 說已轉專人但沒有真的建立轉接單 → 退回（真實 AI 抽測發現，見錯誤紀錄 I3-3）
use({
    "router": [route("policy")],
    "policy": [reply("end_turn", text("這個問題已為您轉給專人協助說明。")),
               reply("tool_use", tool("h1", "request_human", {"reason": "客人詢問特殊退費"})),
               reply("end_turn", text("已建立轉接單，專人會盡快聯絡您。"))],
})
claimed = multi_agent.chat(None, "我想問特殊的退費情況")
detail = claimed["agents"][2]["detail"]
check("說轉專人卻沒建立轉接單會被抓到", "沒有真的建立轉接單" in detail, detail)
check("重答時真的建立轉接單才通過", claimed["tools_used"] == ["request_human"] and claimed["agents"][-2]["detail"] == "全部通過",
      claimed["agents"][-2])

# 5. 規定沒附條號、用了性別稱謂 → 退回
client = use({
    "router": [route("policy")],
    "policy": [reply("tool_use", tool("p2", "search_policy", {"question": "行李多重"})),
               reply("end_turn", text("王先生您好，託運行李上限 23 公斤。")),
               reply("end_turn", text("王小明您好，託運行李上限 23 公斤（行李規定 第1條）。"))],
})
cited = multi_agent.chat(None, "我是王小明，行李可以多重")
detail = cited["agents"][2]["detail"]
check("檢查員抓到沒附條號與稱謂", "出處" in detail and "稱謂" in detail, detail)
check("重答後附上條號", "第1條" in cited["reply"] and "先生" not in cited["reply"])

# 6. 和旅遊無關 → 接待專員
use({"router": [route("reception")], "reception": [reply("end_turn", text("我只能協助旅遊相關的問題喔。"))]})
other = multi_agent.chat(None, "幫我寫一首詩")
check("無關問題交給接待專員", [p["agent"] for p in other["agents"]][1] == "接待專員")

# 7. 單一與多 Agent 的對話不能混用
use({})
try:
    agent.chat(cid, "繼續")
    check("切換模式要開新對話", False)
except agent.ChatError as error:
    check("切換模式要開新對話", error.status == 409, error.message)

# 8. 圖的結構
nodes = set(multi_agent.GRAPH.get_graph().nodes)
check("LangGraph 圖包含全部節點", {"router", "quote", "policy", "reception", "reviewer", "compose"} <= nodes, nodes)

# 假 AI 的用量不能算進真實的每日上限：刪掉測試產生的紀錄
agent._client = None
for t in query("SELECT id FROM ai_turns WHERE id > %s", (FIRST_TURN,)):
    query("DELETE FROM ai_tool_calls WHERE turn_id = %s RETURNING id", (t["id"],))
query("DELETE FROM ai_turns WHERE id > %s RETURNING id", (FIRST_TURN,))

print(f"\n{sum(results)}/{len(results)} 通過")
raise SystemExit(0 if all(results) else 1)
