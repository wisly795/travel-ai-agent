"""採購 Agent：報價成交後向供應商訂房。AI 負責比價與建議，人負責核准，系統負責算錢和下單。"""
import json
import os
import uuid
from datetime import timedelta

from pydantic import BaseModel, Field, ValidationError

from . import agent, erp, quotes
from .db import connect, query

PROCUREMENT_MODEL = os.environ.get("PROCUREMENT_MODEL", "claude-opus-5-5")
# 採購金額達到這個數字（或超出預算）就要主管核准
MANAGER_THRESHOLD = int(os.environ.get("MANAGER_APPROVAL_THRESHOLD", "30000"))

SYSTEM = """你是旅行社的採購助理，負責替一張請購單向供應商訂房做比價與建議。系統內的供應商與價格都是模擬資料。

步驟：
1. 用 get_purchase_request 讀取請購單（飯店、房間數、晚數、預算、出發前多久）。
2. 用 list_offers 取得各供應商的報價，每筆都已由系統算好總價、是否在預算內、房量是否足夠。
3. 比較總價、是否在預算內、房量、取消條件與評分。客人成交後仍可能取消，不能免費取消的方案有風險，要和省下的金額一起考量。
   請購單有出發日期時，看每家的 free_cancel_deadline（免費取消最後一天）與 free_cancel_available_now（今天是否還能免費取消）；已過期限的免費取消條件等於沒有。沒有出發日期時要在說明中提醒。
4. 選一家，用 create_po_draft 建立採購單草稿，reason 寫具體理由（為什麼選它、為什麼不選其他家）。

規則：
- 金額一律使用工具回傳的數字，不可自己計算或改動；比較價差時只能用 diff_vs_cheapest（和最便宜的差多少）或 saving_vs_budget（比預算省多少），不要自己算任兩家之間的差價。
- 請購單的 previous_rejections 是之前被人退回的草稿與原因，這次的建議必須回應退回原因。
- 房量不足的供應商不能選。
- 你只能建立草稿，不能核准或下單，核准由人決定。
- 最後用繁體中文簡短說明比較結果與建議，不要使用 Markdown 符號或表格，條列請用「・」，金額寫成 NT$ 14,400。"""

TOOLS = [
    {
        "name": "get_purchase_request",
        "description": "讀取請購單內容：對應的報價、飯店、房間數、晚數、住宿預算與狀態。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "list_offers",
        "description": "列出這張請購單可用的供應商報價，含總價、是否在預算內、房量是否足夠、取消條件、評分。",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "create_po_draft",
        "description": "選定一筆供應商報價，建立採購單草稿，送交人工核准。每張請購單同時只能有一張待核准的草稿。",
        "input_schema": {
            "type": "object",
            "properties": {
                "offer_id": {"type": "integer", "description": "list_offers 回傳的 offer_id"},
                "reason": {"type": "string", "description": "選擇理由，包含和其他供應商的比較"},
            },
            "required": ["offer_id", "reason"],
        },
    },
]


class DraftInput(BaseModel):
    offer_id: int = Field(gt=0)
    reason: str = Field(min_length=10, max_length=1000)


class ProcurementError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def create_request(quote_id):
    """報價成交時呼叫：預算就是報價裡的住宿費。重複呼叫不會產生第二張。"""
    rows = query(
        """
        INSERT INTO purchase_requests (quote_id, hotel_id, rooms, nights, budget, departure_date)
        SELECT q.id, q.hotel_id, q.rooms, q.nights, h.price_per_night * q.rooms * q.nights, q.departure_date
        FROM quotes q JOIN hotels h ON h.id = q.hotel_id
        WHERE q.id = %s
        ON CONFLICT (quote_id) DO NOTHING
        RETURNING *
        """,
        (quote_id,),
    )
    return rows[0] if rows else query("SELECT * FROM purchase_requests WHERE quote_id = %s", (quote_id,))[0]


def cancel_for_quote(quote_id):
    """報價取消：還沒下單的請購單一起取消，待核准的草稿退回。"""
    with connect() as conn:
        conn.execute(
            """
            UPDATE purchase_orders SET status = '已退回', reject_reason = '報價已取消', decided_at = now()
            WHERE status = '待核准' AND request_id IN (SELECT id FROM purchase_requests WHERE quote_id = %s)
            """,
            (quote_id,),
        )
        conn.execute(
            "UPDATE purchase_requests SET status = '已取消' WHERE quote_id = %s AND status IN ('待比價', '待核准')",
            (quote_id,),
        )


def get_request(request_id):
    rows = query(
        """
        SELECT r.*, h.name AS hotel, h.destination, q.customer_name, q.people
        FROM purchase_requests r
        JOIN hotels h ON h.id = r.hotel_id
        JOIN quotes q ON q.id = r.quote_id
        WHERE r.id = %s
        """,
        (request_id,),
    )
    if not rows:
        raise ProcurementError(404, "找不到請購單")
    request = rows[0]
    request["days_until_departure"] = (
        quotes.days_until(request["departure_date"]) if request["departure_date"] else None
    )
    return request


def list_offers(request_id):
    request = get_request(request_id)
    rows = query(
        """
        SELECT o.id AS offer_id, s.name AS supplier, s.rating, s.note, o.price_per_room_night,
               o.rooms_available, o.free_cancel_days, o.cancel_fee_percent
        FROM supplier_offers o JOIN suppliers s ON s.id = o.supplier_id
        WHERE o.hotel_id = %s
        ORDER BY o.price_per_room_night
        """,
        (request["hotel_id"],),
    )
    for row in rows:
        row["rating"] = float(row["rating"])
        row["total"] = row["price_per_room_night"] * request["rooms"] * request["nights"]
        row["within_budget"] = row["total"] <= request["budget"]
        row["saving_vs_budget"] = request["budget"] - row["total"]
        row["diff_vs_cheapest"] = row["total"] - rows[0]["price_per_room_night"] * request["rooms"] * request["nights"]
        row["enough_rooms"] = row["rooms_available"] >= request["rooms"]
        row["cancel_terms"] = (
            f"出發前 {row['free_cancel_days']} 天以前免費取消，之後收 {row['cancel_fee_percent']}%"
            if row["free_cancel_days"] else f"訂了就不能免費取消，取消收 {row['cancel_fee_percent']}%"
        )
        # 有出發日期才算得出免費取消的最後一天，以及今天是否還在期限內
        if request["departure_date"] and row["free_cancel_days"]:
            deadline = request["departure_date"] - timedelta(days=row["free_cancel_days"])
            row["free_cancel_deadline"] = deadline.isoformat()
            row["free_cancel_available_now"] = quotes.today() <= deadline
        else:
            row["free_cancel_deadline"] = None
            row["free_cancel_available_now"] = False
    return rows


def create_draft(request_id, offer_id, reason):
    request = get_request(request_id)
    if request["status"] not in ("待比價",):
        raise ProcurementError(400, f"請購單目前是「{request['status']}」，不能建立新的草稿")
    offer = next((o for o in list_offers(request_id) if o["offer_id"] == offer_id), None)
    if not offer:
        raise ProcurementError(400, "這筆報價不屬於這張請購單的飯店")
    if not offer["enough_rooms"]:
        raise ProcurementError(400, f"{offer['supplier']} 房量不足（剩 {offer['rooms_available']} 間，需要 {request['rooms']} 間）")
    over = not offer["within_budget"]
    role = "主管" if over or offer["total"] >= MANAGER_THRESHOLD else "業務"
    with connect() as conn:
        po = conn.execute(
            """
            INSERT INTO purchase_orders (request_id, offer_id, amount, over_budget, approver_role, ai_reason)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING *
            """,
            (request_id, offer_id, offer["total"], over, role, reason),
        ).fetchone()
        conn.execute("UPDATE purchase_requests SET status = '待核准' WHERE id = %s", (request_id,))
    return {**po, "supplier": offer["supplier"]}


def request_for_ai(request_id):
    """給 AI 看的請購單：不含上一次的 AI 分析（避免混淆），附上之前被退回的原因。"""
    request = {k: v for k, v in get_request(request_id).items() if k != "ai_analysis"}
    request["previous_rejections"] = query(
        """
        SELECT s.name AS supplier, po.amount, po.reject_reason
        FROM purchase_orders po
        JOIN supplier_offers o ON o.id = po.offer_id JOIN suppliers s ON s.id = o.supplier_id
        WHERE po.request_id = %s AND po.status = '已退回'
        ORDER BY po.id
        """,
        (request_id,),
    )
    return request


def run_tool(request_id, name, raw_input):
    try:
        if name == "get_purchase_request":
            return request_for_ai(request_id), False
        if name == "list_offers":
            return list_offers(request_id), False
        if name == "create_po_draft":
            args = DraftInput(**raw_input)
            return create_draft(request_id, args.offer_id, args.reason), False
        return {"error": f"沒有這個工具：{name}"}, True
    except ValidationError as error:
        return {"error": "參數不正確", "detail": error.errors(include_url=False)}, True
    except ProcurementError as error:
        return {"error": error.message}, True


def analyze(request_id):
    """請 AI 比價並建立草稿。整段過程和客服一樣記在 AI 對話紀錄裡。"""
    request = get_request(request_id)
    if request["status"] != "待比價":
        raise ProcurementError(400, f"請購單目前是「{request['status']}」，不需要比價")
    agent.check_limits(None)
    agent.get_client()
    conversation_id = uuid.uuid4()
    query("INSERT INTO conversations (id, mode) VALUES (%s, 'procurement') RETURNING id", (conversation_id,))
    message = f"請處理請購單 #{request_id}：比價並建立採購單草稿。"
    messages = [{"role": "user", "content": message}]
    result, reply, usage, tool_log = agent.run_loop(
        PROCUREMENT_MODEL, SYSTEM, TOOLS, messages,
        lambda name, raw: run_tool(request_id, name, raw), effort="medium", fallback=True,
    )
    if result != "done":
        reply = "AI 這次沒有完成比價，請稍後再試或由人工選擇供應商。"
    agent.save(conversation_id, messages, f"【採購】{message}", reply, usage, tool_log, PROCUREMENT_MODEL)
    query("UPDATE purchase_requests SET ai_analysis = %s WHERE id = %s RETURNING id", (reply, request_id))
    draft = next((t["output"] for t in tool_log if t["tool"] == "create_po_draft" and not t["is_error"]), None)
    return {"analysis": reply, "draft": json.loads(json.dumps(draft, default=str)) if draft else None}


def decide(po_id, approve, role, reject_reason="", decided_by=""):
    rows = query("SELECT * FROM purchase_orders WHERE id = %s", (po_id,))
    if not rows:
        raise ProcurementError(404, "找不到採購單")
    po = rows[0]
    if po["status"] != "待核准":
        raise ProcurementError(400, f"採購單目前是「{po['status']}」，不能再核准或退回")
    if role not in ("業務", "主管"):
        raise ProcurementError(403, "管理員負責帳號與系統設定，不能核准採購")
    if po["approver_role"] == "主管" and role != "主管":
        raise ProcurementError(403, "這張採購單需要主管核准或退回")
    query("UPDATE purchase_orders SET decided_by = %s WHERE id = %s RETURNING id", (decided_by, po_id))
    if not approve:
        if not reject_reason.strip():
            raise ProcurementError(400, "退回要寫原因")
        with connect() as conn:
            conn.execute(
                "UPDATE purchase_orders SET status = '已退回', reject_reason = %s, decided_at = now() WHERE id = %s",
                (reject_reason.strip(), po_id),
            )
            conn.execute("UPDATE purchase_requests SET status = '待比價' WHERE id = %s", (po["request_id"],))
        return query("SELECT * FROM purchase_orders WHERE id = %s", (po_id,))[0]
    query("UPDATE purchase_orders SET decided_at = now() WHERE id = %s RETURNING id", (po_id,))
    return place_order(po_id)


def place_order(po_id):
    """核准後送給供應商（模擬 API）。失敗記錄原因，可以重送。"""
    po = query(
        """
        SELECT po.*, s.name AS supplier, h.name AS hotel, r.rooms, r.nights, r.quote_id
        FROM purchase_orders po
        JOIN supplier_offers o ON o.id = po.offer_id
        JOIN suppliers s ON s.id = o.supplier_id
        JOIN purchase_requests r ON r.id = po.request_id
        JOIN hotels h ON h.id = r.hotel_id
        WHERE po.id = %s
        """,
        (po_id,),
    )[0]
    try:
        booking = erp.call("POST", "/api/supplier-bookings", {
            "po_id": po["id"], "supplier": po["supplier"], "hotel": po["hotel"],
            "rooms": po["rooms"], "nights": po["nights"], "amount": po["amount"],
        })
        status, confirmation, error = "已下單", booking["confirmation_no"], None
    except erp.ErpError as exc:
        status, confirmation, error = "下單失敗", None, str(exc)
    with connect() as conn:
        conn.execute(
            "UPDATE purchase_orders SET status = %s, confirmation_no = coalesce(%s, confirmation_no), last_error = %s WHERE id = %s",
            (status, confirmation, error, po_id),
        )
        conn.execute("UPDATE purchase_requests SET status = %s WHERE id = %s", (status, po["request_id"]))
    return query("SELECT * FROM purchase_orders WHERE id = %s", (po_id,))[0]


def retry_order(po_id):
    rows = query("SELECT status FROM purchase_orders WHERE id = %s", (po_id,))
    if not rows:
        raise ProcurementError(404, "找不到採購單")
    if rows[0]["status"] != "下單失敗":
        raise ProcurementError(400, "只有下單失敗的採購單可以重送")
    return place_order(po_id)


def list_requests():
    return query(
        """
        SELECT r.id, r.quote_id, r.rooms, r.nights, r.budget, r.status, r.ai_analysis, r.created_at, r.departure_date,
               h.name AS hotel, q.customer_name,
               po.id AS po_id, po.amount, po.over_budget, po.approver_role, po.ai_reason,
               po.status AS po_status, po.reject_reason, po.confirmation_no, po.last_error, po.decided_by,
               s.name AS supplier
        FROM purchase_requests r
        JOIN hotels h ON h.id = r.hotel_id
        JOIN quotes q ON q.id = r.quote_id
        LEFT JOIN LATERAL (
            SELECT * FROM purchase_orders WHERE request_id = r.id ORDER BY id DESC LIMIT 1
        ) po ON true
        LEFT JOIN supplier_offers o ON o.id = po.offer_id
        LEFT JOIN suppliers s ON s.id = o.supplier_id
        ORDER BY r.id DESC
        """
    )


def pending_approvals(older_than_hours=0):
    return query(
        """
        SELECT po.id, po.amount, po.approver_role, po.created_at, r.quote_id
        FROM purchase_orders po JOIN purchase_requests r ON r.id = po.request_id
        WHERE po.status = '待核准' AND po.created_at <= now() - make_interval(hours => %s)
        ORDER BY po.id
        """,
        (older_than_hours,),
    )
