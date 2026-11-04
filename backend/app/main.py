"""旅遊行程報價系統的 REST API。"""
import csv
import hmac
import io
import os
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import (agent, auth, automation, crawler, dashboard, erp, evals, metrics, multi_agent, opendata, partner,
               procurement, quotes, rag)
from .db import migrate, query

STAFF_TOKEN = os.environ["STAFF_TOKEN"]
MANAGER_TOKEN = os.environ["MANAGER_TOKEN"]
AUTOMATION_TOKEN = os.environ["AUTOMATION_TOKEN"]
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app):
    migrate()
    auth.bootstrap_users()
    partner.bootstrap_demo_partner()
    rag.sync()
    opendata.bootstrap()
    yield


app = FastAPI(title="旅遊行程報價系統", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.middleware("http")(metrics.middleware)


@app.get("/metrics", include_in_schema=False)
def prometheus_metrics(authorization: str = Header(default="")):
    """給 Prometheus 抓監控指標。要帶 METRICS_TOKEN；沒設定就不開放。"""
    if not metrics.METRICS_TOKEN or not hmac.compare_digest(authorization, f"Bearer {metrics.METRICS_TOKEN}"):
        raise HTTPException(404, "Not Found")
    body, content_type = metrics.render()
    return Response(body, media_type=content_type)


class QuoteRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=50)
    package_id: int = Field(gt=0)
    hotel_id: int = Field(gt=0)
    people: int = Field(ge=1, le=20)
    departure_date: date | None = None

    @field_validator("customer_name")
    @classmethod
    def strip_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("姓名不可空白")
        return value


class ChatRequest(BaseModel):
    conversation_id: UUID | None = None
    message: str = Field(min_length=1, max_length=500)
    mode: Literal["single", "multi"] = "single"

    @field_validator("message")
    @classmethod
    def strip_message(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("訊息不可空白")
        return value


def identify(authorization: str = Header(default=""), x_staff_token: str = Header(default="")):
    """誰在呼叫：人用帳號登入（Authorization: Bearer 工作階段）；系統整合（n8n、測試程式）用服務權杖。"""
    if authorization.startswith("Bearer "):
        user = auth.user_from_token(authorization[7:])
        if user:
            return {"username": user["username"], "name": user["display_name"], "role": user["role"]}
        raise HTTPException(401, "登入已過期，請重新登入")
    services = ((STAFF_TOKEN, "業務", "服務權杖（業務）"), (MANAGER_TOKEN, "主管", "服務權杖（主管）"),
                (AUTOMATION_TOKEN, "自動化", "n8n 自動化"))
    for token, role, name in services:
        if x_staff_token and hmac.compare_digest(x_staff_token, token):
            return {"username": name, "name": name, "role": role}
    raise HTTPException(401, "請先登入")


def require_staff(who: dict = Depends(identify)):
    """業務、主管、管理員都能進後台；自動化權杖不行。"""
    if who["role"] not in auth.ROLES:
        raise HTTPException(401, "請先登入")
    return who


def require_automation(who: dict = Depends(identify)):
    """自動化流程只能呼叫通知、報表、重送這幾支 API；登入的同仁也可以。"""
    return who


def require_admin(who: dict = Depends(require_staff)):
    if who["role"] != "管理員":
        raise HTTPException(403, "只有管理員可以管理帳號")
    return who


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class NewUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    display_name: str = Field(min_length=1, max_length=30)
    role: str
    password: str = Field(min_length=1, max_length=200)


class UpdateUserRequest(BaseModel):
    is_active: bool | None = None
    role: str | None = None
    password: str | None = Field(default=None, max_length=200)


def auth_call(work):
    try:
        return work()
    except auth.AuthError as error:
        raise HTTPException(error.status, error.message)


@app.post("/api/auth/login")
def login(request: LoginRequest, http: Request):
    ip = http.client.host if http.client else ""
    return auth_call(lambda: auth.login(request.username.strip(), request.password, ip))


@app.post("/api/auth/logout")
def logout(authorization: str = Header(default="")):
    if authorization.startswith("Bearer "):
        auth.logout(authorization[7:])
    return {"ok": True}


@app.get("/api/auth/me")
def me(who: dict = Depends(require_staff)):
    return who


@app.get("/api/admin/users", dependencies=[Depends(require_admin)])
def users():
    return auth.list_users()


@app.post("/api/admin/users", status_code=201, dependencies=[Depends(require_admin)])
def create_user(request: NewUserRequest):
    return auth_call(lambda: auth.create_user(request.username, request.display_name.strip(), request.role, request.password))


@app.patch("/api/admin/users/{user_id}")
def update_user(user_id: int, request: UpdateUserRequest, who: dict = Depends(require_admin)):
    return auth_call(lambda: auth.update_user(user_id, who["username"], request.is_active, request.role, request.password))


@app.get("/api/admin/login-events", dependencies=[Depends(require_admin)])
def login_events():
    return auth.login_events()


class NewPartnerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    rate_limit_per_minute: int = Field(default=30, ge=1, le=600)


class PartnerActiveRequest(BaseModel):
    is_active: bool


@app.get("/api/admin/partners", dependencies=[Depends(require_admin)])
def partners():
    return {"partners": partner.list_partners(), "recent_calls": partner.recent_calls()}


@app.post("/api/admin/partners", status_code=201, dependencies=[Depends(require_admin)])
def create_partner(request: NewPartnerRequest):
    """建立合作夥伴並產生 API 金鑰；金鑰只在這次回傳中出現一次。"""
    return partner.create_partner(request.name.strip(), request.rate_limit_per_minute)


@app.patch("/api/admin/partners/{partner_id}", dependencies=[Depends(require_admin)])
def update_partner(partner_id: int, request: PartnerActiveRequest):
    return partner.set_active(partner_id, request.is_active)


app.mount("/partner", partner.partner_app)


@app.get("/api/health")
def health():
    query("SELECT 1 AS ok")
    return {"status": "ok"}


@app.get("/api/destinations")
def destinations():
    return quotes.list_destinations()


@app.get("/api/packages")
def packages(
    destination: str | None = None,
    max_price: int | None = Query(default=None, gt=0),
    people: int = Query(default=1, ge=1, le=20),
):
    return quotes.search_packages(destination, max_price, people)


@app.get("/api/hotels")
def hotels(destination: str | None = None):
    return quotes.list_hotels(destination)


class PreviewRequest(BaseModel):
    package_id: int = Field(gt=0)
    hotel_id: int = Field(gt=0)
    people: int = Field(ge=1, le=20)
    departure_date: date | None = None


@app.post("/api/quotes/preview")
def preview_quote(request: PreviewRequest):
    """只計算報價明細，不存檔（給 MCP 等外部工具先試算）。"""
    try:
        return quotes.preview_quote(request.package_id, request.hotel_id, request.people, request.departure_date)
    except quotes.QuoteError as error:
        raise HTTPException(error.status, error.message)


class RefundRequest(BaseModel):
    total_price: int = Field(gt=0, le=10_000_000)
    days_before_departure: int | None = Field(default=None, ge=0, le=365)
    departure_date: date | None = None


@app.post("/api/refunds/calculate")
def calculate_refund(request: RefundRequest):
    """依取消與退費規定第 3 條計算扣款與退款；給天數或出發日期其中一個。"""
    try:
        return quotes.calculate_refund(request.total_price, request.days_before_departure, request.departure_date)
    except quotes.QuoteError as error:
        raise HTTPException(error.status, error.message)


@app.post("/api/quotes", status_code=201)
def create_quote(request: QuoteRequest):
    try:
        return quotes.create_quote(
            request.customer_name, request.package_id, request.hotel_id, request.people,
            departure_date=request.departure_date,
        )
    except quotes.QuoteError as error:
        raise HTTPException(error.status, error.message)


@app.get("/api/policies")
def policies():
    return rag.list_policies()


@app.get("/api/explore/cities")
def explore_cities():
    """各縣市有幾個景點、幾家旅宿（政府開放資料）。"""
    return {"cities": opendata.cities(), "source": opendata.SOURCE, "license": opendata.LICENSE}


@app.get("/api/explore/{dataset}")
def explore_search(dataset: Literal["attractions", "hotels"], city: str | None = Query(default=None, max_length=10),
                   q: str | None = Query(default=None, max_length=50), max_price: int | None = Query(default=None, gt=0),
                   with_image: bool = False, limit: int = Query(default=12, ge=1, le=50), offset: int = Query(default=0, ge=0)):
    """搜尋景點或旅宿（政府開放資料；旅宿價格是業者登記的區間，僅供參考，不是報價）。"""
    return opendata.search(dataset, city, q, max_price, with_image, limit, offset)


@app.get("/api/explore/{dataset}/{item_id}")
def explore_get(dataset: Literal["attractions", "hotels"], item_id: str = PathParam(max_length=80)):
    item = opendata.get(dataset, item_id)
    if not item:
        raise HTTPException(404, "找不到這筆資料")
    return {**item, "source": opendata.SOURCE, "license": opendata.LICENSE}


@app.post("/api/admin/opendata/import", status_code=202)
def opendata_import(who: dict = Depends(require_automation)):
    """重新匯入政府開放資料（管理員或 n8n 每日排程）。在背景執行，約 1 分鐘。"""
    if who["role"] not in ("管理員", "自動化"):
        raise HTTPException(403, "只有管理員或自動化流程可以匯入")
    opendata.import_all_background(who["name"])
    return {"started": True}


@app.get("/api/admin/opendata/imports", dependencies=[Depends(require_staff)])
def opendata_imports():
    return opendata.imports()


@app.post("/api/admin/crawler/run", status_code=202)
def crawler_run(who: dict = Depends(require_automation)):
    """爬一次模擬供應商網站（管理員或 n8n 每日排程）。遵守 robots.txt 每秒 1 次，約 1 分鐘。"""
    if who["role"] not in ("管理員", "自動化"):
        raise HTTPException(403, "只有管理員或自動化流程可以執行爬蟲")
    crawler.run_background(who["name"])
    return {"started": True}


@app.get("/api/admin/crawler/runs", dependencies=[Depends(require_staff)])
def crawler_runs():
    return crawler.runs()


@app.get("/api/admin/crawler/changes", dependencies=[Depends(require_staff)])
def crawler_changes():
    return crawler.recent_changes()


@app.get("/api/supplier-prices")
def supplier_prices(city: str | None = Query(default=None, max_length=10)):
    """爬蟲抓到的供應商最新價格（模擬網站資料，比價參考用）。"""
    return {"hotels": crawler.latest_prices(city), "source": "雲遊旅宿比價網（模擬網站，資料皆為虛構）"}


@app.get("/api/policies/model")
def policy_model():
    """目前 RAG 用哪個向量模型、門檻多少。"""
    return rag.info()


@app.get("/api/policies/search")
def search_policies(q: str = Query(min_length=1, max_length=300)):
    """直接看 RAG 找到哪些條文與相似度，方便檢查與教學。"""
    return rag.search(q)


@app.get("/api/chat/status")
def chat_status():
    return {"enabled": bool(os.environ.get("ANTHROPIC_API_KEY")), "model": agent.CHAT_MODEL}


@app.post("/api/chat")
def chat(request: ChatRequest):
    try:
        if request.mode == "multi":
            return multi_agent.chat(request.conversation_id, request.message)
        return agent.chat(request.conversation_id, request.message)
    except agent.ChatError as error:
        raise HTTPException(error.status, error.message)


QUOTE_LIST_SQL = """
    SELECT q.id, q.customer_name, p.name AS package, p.destination, h.name AS hotel,
           q.people, q.rooms, q.nights, q.total_price, q.source, q.status, q.departure_date,
           s.status AS erp_status, s.erp_order_no, q.created_at
    FROM quotes q
    JOIN packages p ON p.id = q.package_id
    JOIN hotels h ON h.id = q.hotel_id
    LEFT JOIN erp_syncs s ON s.quote_id = q.id
    ORDER BY q.id DESC
"""


class StatusRequest(BaseModel):
    status: str = Field(pattern="^(成交|取消)$")
    note: str = Field(default="", max_length=200)


class FailModeRequest(BaseModel):
    on: bool


class HandoffUpdate(BaseModel):
    status: str = Field(pattern="^(待處理|已處理)$")


@app.get("/api/quotes", dependencies=[Depends(require_staff)])
def list_quotes():
    return query(QUOTE_LIST_SQL)


@app.patch("/api/quotes/{quote_id}/status")
def change_quote_status(quote_id: int, request: StatusRequest, who: dict = Depends(require_staff)):
    """業務改報價狀態；改成成交時自動同步到 ERP。記錄是誰改的。"""
    try:
        result = quotes.change_status(quote_id, request.status, request.note, changed_by=who["name"])
    except quotes.QuoteError as error:
        raise HTTPException(error.status, error.message)
    if request.status == "成交":
        result["erp"] = erp.push_quote(quote_id)
        result["purchase_request"] = procurement.create_request(quote_id)
    else:
        procurement.cancel_for_quote(quote_id)
    return result


class DecisionRequest(BaseModel):
    approve: bool
    reason: str = Field(default="", max_length=300)


def procurement_call(work):
    try:
        return work()
    except procurement.ProcurementError as error:
        raise HTTPException(error.status, error.message)
    except agent.ChatError as error:
        raise HTTPException(error.status, error.message)


@app.get("/api/procurement", dependencies=[Depends(require_staff)])
def procurement_list():
    return procurement.list_requests()


@app.get("/api/procurement/{request_id}/offers", dependencies=[Depends(require_staff)])
def procurement_offers(request_id: int):
    return procurement_call(lambda: procurement.list_offers(request_id))


@app.post("/api/procurement/{request_id}/analyze", dependencies=[Depends(require_staff)])
def procurement_analyze(request_id: int):
    """請採購 Agent 比價並建立草稿（使用較強的模型）。"""
    return procurement_call(lambda: procurement.analyze(request_id))


@app.post("/api/purchase-orders/{po_id}/decision")
def purchase_decision(po_id: int, request: DecisionRequest, who: dict = Depends(require_staff)):
    return procurement_call(lambda: procurement.decide(po_id, request.approve, who["role"], request.reason,
                                                       decided_by=who["name"]))


@app.post("/api/purchase-orders/{po_id}/retry", dependencies=[Depends(require_staff)])
def purchase_retry(po_id: int):
    return procurement_call(lambda: procurement.retry_order(po_id))


class NotificationRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=2000)
    dedupe_key: str | None = Field(default=None, max_length=100)


class ReadRequest(BaseModel):
    id: int | None = None


@app.post("/api/notifications", dependencies=[Depends(require_automation)])
def create_notification(request: NotificationRequest):
    return automation.add_notification(request.kind, request.title, request.body, request.dedupe_key)


@app.get("/api/notifications", dependencies=[Depends(require_staff)])
def notifications():
    return automation.list_notifications()


@app.post("/api/notifications/read", dependencies=[Depends(require_staff)])
def read_notifications(request: ReadRequest):
    automation.mark_read(request.id)
    return {"ok": True}


@app.get("/api/reports/daily", dependencies=[Depends(require_automation)])
def daily_report():
    return automation.daily_report()


@app.get("/api/purchase-orders/pending", dependencies=[Depends(require_automation)])
def purchase_pending(older_than_hours: int = Query(default=0, ge=0, le=720)):
    """待核准的採購單，給自動化流程做提醒。"""
    return procurement.pending_approvals(older_than_hours)


@app.get("/api/quotes/{quote_id}/events", dependencies=[Depends(require_staff)])
def quote_events(quote_id: int):
    return query("SELECT * FROM quote_events WHERE quote_id = %s ORDER BY id", (quote_id,))


@app.get("/api/erp/syncs", dependencies=[Depends(require_staff)])
def erp_syncs():
    return erp.list_syncs()


@app.get("/api/erp/status", dependencies=[Depends(require_staff)])
def erp_status():
    return erp.health()


@app.post("/api/erp/syncs/{quote_id}/retry", dependencies=[Depends(require_staff)])
def retry_erp(quote_id: int):
    if not query("SELECT 1 FROM erp_syncs WHERE quote_id = %s", (quote_id,)):
        raise HTTPException(404, "這張報價還沒有同步紀錄")
    return erp.push_quote(quote_id)


@app.post("/api/erp/retry-failed", dependencies=[Depends(require_automation)])
def retry_failed():
    """重送所有失敗的同步，給自動化流程定時呼叫。"""
    results = [erp.push_quote(quote_id) for quote_id in erp.failed_quote_ids()]
    failed = [r for r in results if r["status"] == "失敗"]
    return {
        "retried": len(results),
        "succeeded": len(results) - len(failed),
        "still_failed": [r["quote_id"] for r in failed],
        "still_failed_detail": [
            {"quote_id": r["quote_id"], "attempts": r["attempts"], "last_error": r["last_error"]} for r in failed
        ],
    }


@app.post("/api/erp/fail-mode", dependencies=[Depends(require_staff)])
def erp_fail_mode(request: FailModeRequest):
    try:
        return erp.set_fail_mode(request.on)
    except erp.ErpError as error:
        raise HTTPException(502, str(error))


@app.get("/api/admin/turns", dependencies=[Depends(require_staff)])
def ai_turns(limit: int = Query(default=30, ge=1, le=200)):
    """AI 對話紀錄：每次提問、回答、用了哪些工具、花多少錢。speaker 是提問的一方：客人或採購系統。"""
    return query(
        """
        SELECT t.id, t.conversation_id, t.user_message, t.reply, t.model,
               t.input_tokens, t.output_tokens, t.cost_usd, t.created_at, t.agent_path,
               CASE WHEN v.mode = 'procurement' OR t.user_message LIKE '【採購】%%' THEN '採購系統' ELSE '客人' END AS speaker,
               coalesce(json_agg(json_build_object('tool', c.tool, 'input', c.input,
                        'output', c.output, 'is_error', c.is_error, 'agent', c.agent) ORDER BY c.id)
                        FILTER (WHERE c.id IS NOT NULL), '[]') AS tools
        FROM ai_turns t LEFT JOIN conversations v ON v.id = t.conversation_id
        LEFT JOIN ai_tool_calls c ON c.turn_id = t.id
        GROUP BY t.id, v.mode ORDER BY t.id DESC LIMIT %s
        """,
        (limit,),
    )


@app.get("/api/admin/dashboard", dependencies=[Depends(require_staff)])
def dashboard_overview(days: int = Query(default=14, ge=7, le=90)):
    """營運儀表板：近 30 天關鍵數字與每日趨勢。"""
    return dashboard.overview(days)


@app.get("/api/admin/evals", dependencies=[Depends(require_staff)])
def eval_overview():
    return {"running": evals.is_running(), "latest": evals.latest(), "history": evals.history()}


class EvalRunRequest(BaseModel):
    mode: Literal["single", "multi"] = "single"


@app.post("/api/admin/evals/run", status_code=202)
def eval_run(request: EvalRunRequest | None = None, who: dict = Depends(require_admin)):
    """管理員觸發 AI 評測（23 題，約 1–2 分鐘，會花少量 API 額度），在背景執行。"""
    mode = request.mode if request else "single"
    try:
        agent.check_limits(None)
        agent.get_client()
    except agent.ChatError as error:
        raise HTTPException(error.status, error.message)
    label = f"由 {who['name']} 執行" + ("（多 Agent）" if mode == "multi" else "")
    if not evals.start_background(label, mode):
        raise HTTPException(409, "評測正在執行中")
    return {"started": True}


@app.get("/api/admin/usage", dependencies=[Depends(require_staff)])
def ai_usage():
    today = query(
        """
        SELECT count(*) AS turns, coalesce(sum(cost_usd), 0) AS cost_usd
        FROM ai_turns
        WHERE created_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Taipei') AT TIME ZONE 'Asia/Taipei'
        """
    )[0]
    return {**today, "turn_limit": agent.DAILY_CHAT_LIMIT, "cost_limit_usd": agent.DAILY_COST_LIMIT_USD}


@app.get("/api/handoffs", dependencies=[Depends(require_staff)])
def handoffs():
    return query("SELECT * FROM handoffs ORDER BY (status = '待處理') DESC, id DESC")


@app.patch("/api/handoffs/{handoff_id}", dependencies=[Depends(require_staff)])
def update_handoff(handoff_id: int, request: HandoffUpdate):
    rows = query("UPDATE handoffs SET status = %s WHERE id = %s RETURNING *", (request.status, handoff_id))
    if not rows:
        raise HTTPException(404, "找不到轉接單")
    return rows[0]


def safe_cell(value):
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


SOURCE_LABELS = {"web": "網頁", "ai": "AI 客服", "partner": "官網串接"}


@app.get("/api/quotes/export.csv", dependencies=[Depends(require_staff)])
def export_quotes():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["編號", "客人", "行程", "目的地", "飯店", "人數", "房間", "晚數", "總價", "來源",
                     "狀態", "出發日", "ERP 同步", "ERP 單號", "建立時間"])
    for row in query(QUOTE_LIST_SQL):
        row["source"] = SOURCE_LABELS.get(row["source"], row["source"])
        writer.writerow([safe_cell(value) for value in row.values()])
    return Response(
        "﻿" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="quotes.csv"'},
    )


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.get("/")
@app.get("/tours")
@app.get("/tours/{rest:path}")
@app.get("/explore")
@app.get("/explore/{rest:path}")
@app.get("/guide")
@app.get("/admin")
def index(rest: str = ""):
    """前端是單頁應用（React Router）：這些網址都回同一個頁面，由前端決定顯示哪一頁，重新整理也不會 404。"""
    return FileResponse(FRONTEND / "index.html")
