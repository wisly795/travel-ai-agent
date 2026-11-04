"""合作夥伴 API（官網串接）：API 金鑰只存雜湊、每分鐘呼叫上限、呼叫紀錄、獨立的 API 文件。

官網或旅遊平台的「後端」用 X-API-Key 呼叫這裡；金鑰不能放在瀏覽器裡。
文件頁：/partner/docs
"""
import hashlib
import os
import secrets
from datetime import date

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from . import quotes
from .db import connect, query

DEMO_KEY = os.environ.get("PARTNER_DEMO_KEY", "")

partner_app = FastAPI(
    title="旅遊報價系統｜合作夥伴 API",
    version="1.0",
    description=(
        "給官網與合作旅遊平台串接用。所有資料皆為模擬資料。\n\n"
        "**驗證**：每個請求都要帶 `X-API-Key` 標頭（向系統管理員申請，只會顯示一次）。\n\n"
        "**呼叫上限**：依合作夥伴設定（預設每分鐘 30 次），超過回 429，請依 `Retry-After` 秒數後再試。\n\n"
        "**價格**：一律由系統計算，請不要自行計算或修改。"
    ),
    docs_url="/docs", redoc_url=None, openapi_url="/openapi.json",
)


def key_hash(key):
    return hashlib.sha256(key.encode()).hexdigest()


def new_key():
    return "pk_" + secrets.token_urlsafe(24)


def bootstrap_demo_partner():
    """用 .env 的 PARTNER_DEMO_KEY 建立「官網示範」合作夥伴，讓模擬官網與測試可以直接使用。"""
    if DEMO_KEY:
        query(
            """
            INSERT INTO partners (name, key_prefix, key_hash, rate_limit_per_minute)
            VALUES ('官網示範', %s, %s, 60) ON CONFLICT (key_hash) DO NOTHING RETURNING id
            """,
            (DEMO_KEY[:10], key_hash(DEMO_KEY)),
        )


def create_partner(name, rate_limit):
    key = new_key()
    row = query(
        """
        INSERT INTO partners (name, key_prefix, key_hash, rate_limit_per_minute) VALUES (%s, %s, %s, %s)
        RETURNING id, name, key_prefix, rate_limit_per_minute, is_active, created_at
        """,
        (name, key[:10], key_hash(key), rate_limit),
    )[0]
    return {**row, "api_key": key}  # 只在建立時回傳一次，之後查不到原始金鑰


def list_partners():
    return query(
        """
        SELECT p.id, p.name, p.key_prefix, p.rate_limit_per_minute, p.is_active, p.created_at, p.last_used_at,
               (SELECT count(*) FROM partner_calls c WHERE c.partner_id = p.id AND c.created_at > now() - interval '1 day') AS calls_24h,
               (SELECT count(*) FROM partner_calls c WHERE c.partner_id = p.id AND c.status = 429
                  AND c.created_at > now() - interval '1 day') AS limited_24h,
               (SELECT count(*) FROM quotes q WHERE q.partner_id = p.id) AS quotes
        FROM partners p ORDER BY p.id
        """
    )


def set_active(partner_id, active):
    rows = query("UPDATE partners SET is_active = %s WHERE id = %s RETURNING id, name, is_active", (active, partner_id))
    if not rows:
        raise HTTPException(404, "找不到合作夥伴")
    return rows[0]


def recent_calls(limit=50):
    return query(
        """
        SELECT c.created_at, p.name, c.method, c.path, c.status
        FROM partner_calls c JOIN partners p ON p.id = c.partner_id
        ORDER BY c.id DESC LIMIT %s
        """,
        (limit,),
    )


def require_partner(request: Request, x_api_key: str = Header(default="", description="合作夥伴 API 金鑰")):
    """驗證金鑰並檢查每分鐘呼叫上限。"""
    rows = query("SELECT * FROM partners WHERE key_hash = %s", (key_hash(x_api_key),)) if x_api_key else []
    if not rows or not rows[0]["is_active"]:
        raise HTTPException(401, "API 金鑰無效或已停用")
    partner = rows[0]
    request.state.partner_id = partner["id"]
    # 「數次數＋登記這次」在同一個交易裡、先鎖住這個合作夥伴：同時湧入的請求要排隊數，
    # 不會好幾個請求同時看到「還沒滿」而多放（人工驗收發現上限 60 實際放行 69 次）。
    with connect() as conn:
        conn.execute("SELECT id FROM partners WHERE id = %s FOR UPDATE", (partner["id"],))
        used = conn.execute(
            """SELECT count(*) AS n FROM partner_calls
               WHERE partner_id = %s AND status <> 429 AND created_at > now() - interval '60 seconds'""",
            (partner["id"],),
        ).fetchone()["n"]
        if used < partner["rate_limit_per_minute"]:
            # 先佔一筆紀錄（狀態 0＝處理中），回應後再補上真正的狀態碼
            request.state.call_id = conn.execute(
                "INSERT INTO partner_calls (partner_id, method, path, status) VALUES (%s, %s, %s, 0) RETURNING id",
                (partner["id"], request.method, request.url.path),
            ).fetchone()["id"]
            conn.execute("UPDATE partners SET last_used_at = now() WHERE id = %s", (partner["id"],))
    if used >= partner["rate_limit_per_minute"]:
        raise HTTPException(429, f"呼叫太頻繁：每分鐘上限 {partner['rate_limit_per_minute']} 次",
                            headers={"Retry-After": "60"})
    return partner


@partner_app.middleware("http")
async def log_calls(request: Request, call_next):
    """每次呼叫記錄路徑與結果（含被擋下的 429），用來算呼叫上限與給管理員查看。"""
    response = await call_next(request)
    partner_id = getattr(request.state, "partner_id", None)
    call_id = getattr(request.state, "call_id", None)
    if call_id:
        query("UPDATE partner_calls SET status = %s WHERE id = %s RETURNING id", (response.status_code, call_id))
    elif partner_id:
        query(
            "INSERT INTO partner_calls (partner_id, method, path, status) VALUES (%s, %s, %s, %s) RETURNING id",
            (partner_id, request.method, request.url.path, response.status_code),
        )
    return response


@partner_app.exception_handler(quotes.QuoteError)
async def quote_error(request, error):
    return JSONResponse({"detail": error.message}, status_code=error.status)


class PartnerQuoteRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=50, description="客人姓名")
    package_id: int = Field(gt=0, description="行程編號（從 /v1/packages 取得）")
    hotel_id: int = Field(gt=0, description="飯店編號（從 /v1/hotels 取得）")
    people: int = Field(ge=1, le=20, description="人數 1–20")
    departure_date: date = Field(description="出發日期（明天到一年內）")

    @field_validator("customer_name")
    @classmethod
    def strip_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("姓名不可空白")
        return value


class PartnerPreviewRequest(BaseModel):
    package_id: int = Field(gt=0)
    hotel_id: int = Field(gt=0)
    people: int = Field(ge=1, le=20)
    departure_date: date | None = None


@partner_app.get("/v1/destinations", summary="目的地清單", tags=["查詢"])
def destinations(partner=Depends(require_partner)):
    return quotes.list_destinations()


@partner_app.get("/v1/packages", summary="查詢行程", tags=["查詢"])
def packages(destination: str | None = None, max_price: int | None = Query(default=None, gt=0),
             people: int = Query(default=1, ge=1, le=20), partner=Depends(require_partner)):
    return quotes.search_packages(destination, max_price, people)


@partner_app.get("/v1/hotels", summary="查詢飯店", tags=["查詢"])
def hotels(destination: str, partner=Depends(require_partner)):
    return quotes.list_hotels(destination)


@partner_app.post("/v1/quotes/preview", summary="試算報價（不存檔）", tags=["報價"])
def preview(request: PartnerPreviewRequest, partner=Depends(require_partner)):
    return quotes.preview_quote(request.package_id, request.hotel_id, request.people, request.departure_date)


@partner_app.post("/v1/quotes", status_code=201, summary="建立報價單", tags=["報價"])
def create(request: PartnerQuoteRequest, partner=Depends(require_partner)):
    return quotes.create_quote(request.customer_name, request.package_id, request.hotel_id, request.people,
                               source="partner", departure_date=request.departure_date, partner_id=partner["id"])


@partner_app.get("/v1/quotes/{quote_id}", summary="查詢自己建立的報價單", tags=["報價"])
def get_quote(quote_id: int, partner=Depends(require_partner)):
    rows = query(
        """
        SELECT q.id, q.customer_name, p.name AS package, h.name AS hotel, q.people, q.rooms, q.nights,
               q.total_price, q.status, q.departure_date, q.created_at
        FROM quotes q JOIN packages p ON p.id = q.package_id JOIN hotels h ON h.id = q.hotel_id
        WHERE q.id = %s AND q.partner_id = %s
        """,
        (quote_id, partner["id"]),
    )
    if not rows:
        raise HTTPException(404, "找不到這張報價單")  # 別家的報價也回 404，不透露是否存在
    return rows[0]
