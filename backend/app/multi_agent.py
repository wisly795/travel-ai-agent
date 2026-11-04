"""多 Agent 協作版 AI 客服：用 LangGraph 編排，每個 Agent 仍用官方 Anthropic SDK 呼叫 Claude。

流程（一張有向圖）：
  分流 Agent ─┬→ 報價專員 ─┐
              ├→ 規定專員 ─┼→ 檢查員 ──通過──→ 組合回覆
              └→ 接待專員 ─┘      └─不通過→ 退回原專員改一次（最多一次）

- 分流 Agent：只判斷這句話要交給誰，可以同時交給報價與規定兩位（平行執行）。
- 專員：各自只拿到自己需要的工具，權限最小。
- 檢查員：不呼叫 AI，用程式檢查金額有沒有出現在工具結果裡、規定有沒有附條號、有沒有性別稱謂；
  不通過就把問題寫給專員重答，第二次還不通過就改成轉專人，不讓錯的金額送到客人面前。
"""
import json
import operator
import re
from decimal import Decimal
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from . import agent
from .db import connect, query

ROUTE_TOOL = {
    "name": "route",
    "description": "把客人這句話拆給負責的專員，每位專員只拿到自己要處理的部分。",
    "input_schema": {
        "type": "object",
        "properties": {
            "tasks": {
                "type": "object",
                "description": "要交給哪些專員、各自要處理的問題（用客人的口吻改寫成完整的一句話，保留人數、地點、日期、姓名等細節）。用不到的專員就省略。",
                "properties": {
                    "quote": {"type": "string", "description": "報價專員：行程、飯店、報價、建立報價單"},
                    "policy": {"type": "string", "description": "規定專員：取消退費、行李、簽證、保險、付款發票、兒童長者等規定"},
                    "reception": {"type": "string", "description": "接待專員：打招呼、客訴、要找真人、和旅遊無關的問題"},
                },
            },
            "reason": {"type": "string", "description": "一句話說明為什麼這樣分"},
        },
        "required": ["tasks", "reason"],
    },
}
ROUTER_SYSTEM = """你是旅遊客服的分流員，只負責把客人這句話拆給專員，不回答問題。
同時問到報價和規定時，拆成兩個問題分別交給 quote 與 policy。看得懂前面的對話：客人說「好，幫我建立」「我叫王小明」這類接續報價的話，交給 quote，並把需要的細節寫進問題裡。
客人說的人數、金額、日期、姓名一律照抄原文，即使看起來不合理（例如 0 人、50 人）也不可修正或猜測，交給專員判斷。"""

TEAM_RULE = ("你的回答會和其他專員的回答直接合併成一則訊息給客人。只寫你負責的部分；"
             "其他部分當作不存在：不要提到其他專員、不要叫客人去問別人、不要為那些部分建立轉接單，也不要重複打招呼。")
ROLES = {
    "quote": ("報價專員", ["list_destinations", "search_packages", "list_hotels", "calculate_quote", "create_quote", "request_human"],
              "你是報價專員，負責行程、飯店與報價：查詢、用 calculate_quote 算出明細並告訴客人金額。" + TEAM_RULE),
    "policy": ("規定專員", ["search_policy", "calculate_refund", "request_human"],
               "你是規定專員，負責旅遊規定與退費計算：用 search_policy 查條文並附出處。" + TEAM_RULE),
    "reception": ("接待專員", ["list_destinations", "request_human"],
                  "你是接待專員，負責打招呼、說明能幫什麼忙、處理客訴與轉接真人。和旅遊無關的問題禮貌說明只能協助旅遊相關事項。"),
}
ORDER = ["quote", "policy", "reception"]
HONORIFICS = re.compile(r"先生|小姐|女士")
MONEY = re.compile(r"NT\$\s?([\d,]+)")
CLAIMS_HANDOFF = re.compile(r"(已|已經|幫您|為您)\S{0,4}(轉給|轉交|轉接)|轉接單")


def merge(a, b):
    return {**a, **b}


class State(TypedDict, total=False):
    message: str
    history: list
    conversation_id: str
    route: dict
    drafts: Annotated[dict, merge]
    feedback: Annotated[dict, merge]
    attempts: Annotated[dict, merge]
    tool_log: Annotated[list, operator.add]
    path: Annotated[list, operator.add]
    usage: Annotated[list, operator.add]
    reply: str


def tools_for(names):
    return [t for t in agent.TOOLS if t["name"] in names]


def router(state):
    client = agent.get_client()
    messages = state["history"] + [{"role": "user", "content": state["message"]}]
    try:
        response = client.messages.create(
            model=agent.CHAT_MODEL, max_tokens=300, system=ROUTER_SYSTEM, tools=[ROUTE_TOOL],
            tool_choice={"type": "tool", "name": "route"}, messages=messages,
        )
    except agent.anthropic.APIError as error:
        raise agent.ChatError(502, f"AI 服務暫時無法使用（{type(error).__name__}）")
    block = next(b for b in response.content if b.type == "tool_use")
    raw = block.input.get("tasks") or {}
    tasks = {a: str(raw[a]).strip() for a in ORDER if isinstance(raw, dict) and str(raw.get(a) or "").strip()}
    if not tasks:
        tasks = {"reception": state["message"]}
    usage = {"input": response.usage.input_tokens, "output": response.usage.output_tokens,
             "cost": agent.turn_cost(agent.CHAT_MODEL, response.usage)}
    detail = "；".join(f"{ROLES[a][0]}「{q}」" for a, q in tasks.items())
    return {"route": {"agents": list(tasks), "tasks": tasks, "reason": block.input.get("reason", "")},
            "path": [{"agent": "分流", "detail": f"{detail}（{block.input.get('reason', '')}）"}],
            "usage": [usage]}


def make_specialist(key):
    label, tool_names, role = ROLES[key]

    def run(state):
        system = f"{agent.system_prompt()}\n\n{role}"
        # 只交辦這位專員負責的那一段（分流時拆好的），避免越界；附上客人原話，數字以原話為準（分流改寫可能失真）
        task = state["route"].get("tasks", {}).get(key)
        content = state["message"] if not task or task == state["message"] else (
            f"{task}\n\n（只處理上面這段。客人原話：「{state['message']}」，人數、金額、日期以原話為準。）")
        if key in state.get("feedback", {}):
            content += f"\n\n（系統檢查員：你上一版回答有問題，請修正後重答：{state['feedback'][key]}）"
        messages = state["history"] + [{"role": "user", "content": content}]
        result, text, usage, log = agent.run_loop(
            agent.CHAT_MODEL, system, tools_for(tool_names), messages,
            lambda name, raw: agent.run_tool(name, raw, state["conversation_id"]), effort="low",
        )
        if result != "done" or not text:
            text = "這部分我沒辦法完整回答，需要的話我可以幫您轉給專人。"
        attempt = state.get("attempts", {}).get(key, 0) + 1
        return {"drafts": {key: text}, "attempts": {key: attempt},
                "tool_log": [{**t, "agent": label} for t in log],
                "path": [{"agent": label, "detail": f"第 {attempt} 次作答，用了 {len(log)} 個工具"}],
                "usage": [usage]}

    return run


def numbers_in(value):
    text = json.dumps(value, ensure_ascii=False, default=str).replace(",", "")
    found = {int(float(n)) for n in re.findall(r"\d+(?:\.\d+)?", text)}
    # 客人說「3 萬」「5 千」，AI 寫成 NT$ 30,000 也算客人自己講過的數字
    for n, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([萬千])", text):
        found.add(int(float(n) * (10000 if unit == "萬" else 1000)))
    return found


def review(state):
    """程式檢查，不花 AI 費用。回傳要退回重答的專員與原因。
    合法的金額：這一輪工具回傳的、之前對話出現過的、客人這句話自己說的（例如預算）。"""
    allowed = (numbers_in([t["output"] for t in state.get("tool_log", [])]) | numbers_in(state["history"])
               | numbers_in(state["message"]))
    problems = {}
    for key, text in state["drafts"].items():
        label = ROLES[key][0]
        issues = []
        wrong = [m for m in MONEY.findall(text) if int(m.replace(",", "")) not in allowed]
        if wrong:
            issues.append(f"金額 {'、'.join('NT$ ' + w for w in wrong)} 不在工具結果裡，金額只能用工具回傳的數字")
        found_policy = any(t["tool"] == "search_policy" and t["output"].get("results")
                           for t in state.get("tool_log", []) if t["agent"] == label)
        if found_policy and not re.search(r"第\s?\d+\s?條", text):
            issues.append("回答規定時要註明出處，例如（取消與退費規定 第3條）")
        if HONORIFICS.search(text):
            issues.append("不要使用先生、小姐、女士等稱謂")
        handed_off = any(t["tool"] == "request_human" and not t["is_error"]
                         for t in state.get("tool_log", []) if t["agent"] == label)
        if CLAIMS_HANDOFF.search(text) and not handed_off:
            issues.append("回答說已轉給專人，但沒有真的建立轉接單；不要說沒做的事")
        if issues:
            problems[key] = "；".join(issues)
    return problems


def reviewer(state):
    problems = review(state)
    retry = {k: v for k, v in problems.items() if state["attempts"].get(k, 0) < 2}
    path = [{"agent": "檢查員", "detail": "全部通過" if not problems else
             "；".join(f"{ROLES[k][0]}：{v}" for k, v in problems.items())}]
    drafts = {}
    for key, issue in problems.items():
        if key not in retry and "金額" in issue:
            # 改過一次金額還是對不上：不把可能錯的金額給客人，改成轉專人
            row = query("INSERT INTO handoffs (conversation_id, reason) VALUES (%s, %s) RETURNING id",
                        (state["conversation_id"], f"多 Agent 檢查未通過：{issue}"))[0]
            drafts[key] = f"這部分的金額需要專人再確認，已建立轉接單 #{row['id']}，專人會盡快聯絡您。"
    return {"feedback": retry, "path": path, "drafts": drafts}


def after_review(state):
    """還有問題、而且還沒重答過的專員退回重答；其餘進入組合回覆。"""
    pending = [k for k in review(state) if state["attempts"].get(k, 0) < 2]
    return pending or "compose"


def compose(state):
    parts = [state["drafts"][k] for k in ORDER if k in state["drafts"]]
    return {"reply": "\n\n".join(parts), "path": [{"agent": "組合回覆", "detail": f"合併 {len(parts)} 位專員的回答"}]}


def build():
    graph = StateGraph(State)
    graph.add_node("router", router)
    for key in ORDER:
        graph.add_node(key, make_specialist(key))
    graph.add_node("reviewer", reviewer)
    graph.add_node("compose", compose)
    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", lambda s: s["route"]["agents"], ORDER)
    for key in ORDER:
        graph.add_edge(key, "reviewer")
    graph.add_conditional_edges("reviewer", after_review, ORDER + ["compose"])
    graph.add_edge("compose", END)
    return graph.compile()


GRAPH = build()


def to_history(rows):
    """多 Agent 模式的對話紀錄只存文字＋工具摘要，每位專員都看得懂、不受別人的工具影響。"""
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def record_text(reply, tool_log):
    if not tool_log:
        return reply
    brief = [{"agent": t["agent"], "tool": t["tool"], "input": t["input"], "output": t["output"]} for t in tool_log
             if not t["is_error"]]
    return f"{reply}\n\n（系統紀錄，客人看不到：{json.dumps(brief, ensure_ascii=False, default=str)[:3000]}）"


def chat(conversation_id, message):
    agent.check_limits(conversation_id)
    agent.get_client()
    conversation_id, history = agent.load_history(conversation_id, mode="multi")
    state = GRAPH.invoke({"message": message, "history": to_history(history), "conversation_id": str(conversation_id),
                          "drafts": {}, "feedback": {}, "attempts": {}, "tool_log": [], "path": [], "usage": []})
    reply = state["reply"] or "抱歉，我沒有產生回覆，請再說一次。"
    usage = {"input": sum(u["input"] for u in state["usage"]), "output": sum(u["output"] for u in state["usage"]),
             "cost": sum((Decimal(u["cost"]) for u in state["usage"]), Decimal(0))}
    history = history + [{"role": "user", "content": message},
                         {"role": "assistant", "content": record_text(reply, state["tool_log"])}]
    save(conversation_id, history, message, reply, usage, state["tool_log"], state["path"])
    created = next((t["output"] for t in state["tool_log"] if t["tool"] == "create_quote" and not t["is_error"]), None)
    return {
        "conversation_id": str(conversation_id),
        "reply": reply,
        "tools_used": [t["tool"] for t in state["tool_log"]],
        "agents": state["path"],
        "quote": json.loads(json.dumps(created, default=str)) if created else None,
    }


def save(conversation_id, history, message, reply, usage, tool_log, path):
    with connect() as conn:
        conn.execute("UPDATE conversations SET history = %s, updated_at = now() WHERE id = %s",
                     (json.dumps(history, ensure_ascii=False, default=str), conversation_id))
        turn = conn.execute(
            """
            INSERT INTO ai_turns (conversation_id, user_message, reply, model, input_tokens, output_tokens, cost_usd, agent_path)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (conversation_id, message, reply, f"{agent.CHAT_MODEL}（多 Agent）",
             usage["input"], usage["output"], usage["cost"], json.dumps(path, ensure_ascii=False)),
        ).fetchone()
        for item in tool_log:
            conn.execute(
                "INSERT INTO ai_tool_calls (turn_id, tool, input, output, is_error, agent) VALUES (%s, %s, %s, %s, %s, %s)",
                (turn["id"], item["tool"], json.dumps(item["input"], ensure_ascii=False),
                 json.dumps(item["output"], ensure_ascii=False, default=str), item["is_error"], item["agent"]),
            )
