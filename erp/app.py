"""模擬 ERP：代表公司另一套系統，用 API 接收訂單。資料存在 SQLite。

真實情況下這是系統商的產品，我們只能透過它公開的 API 串接。
"""
import hmac
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

API_KEY = os.environ["ERP_API_KEY"]
DB = os.environ.get("ERP_DB", "/data/erp.db")

app = FastAPI(title="模擬 ERP", docs_url=None, redoc_url=None, openapi_url=None)
state = {"fail_mode": False}


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


with closing(db()) as conn:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_no TEXT PRIMARY KEY,
            external_id TEXT UNIQUE NOT NULL,
            customer_name TEXT NOT NULL,
            item TEXT NOT NULL,
            people INTEGER NOT NULL,
            amount INTEGER NOT NULL,
            received_at TEXT NOT NULL
        )
    """)
    conn.commit()


def require_key(x_api_key: str = Header(default="")):
    if not hmac.compare_digest(x_api_key, API_KEY):
        raise HTTPException(401, "invalid api key")


class Order(BaseModel):
    external_id: str = Field(min_length=1, max_length=50)
    customer_name: str = Field(min_length=1, max_length=50)
    item: str = Field(min_length=1, max_length=200)
    people: int = Field(ge=1, le=20)
    amount: int = Field(gt=0)


class FailMode(BaseModel):
    on: bool


@app.get("/health")
def health():
    return {"status": "ok", "fail_mode": state["fail_mode"]}


@app.post("/api/orders", dependencies=[Depends(require_key)])
def create_order(order: Order):
    if state["fail_mode"]:
        raise HTTPException(503, "ERP maintenance")
    with closing(db()) as conn:
        # 同一張報價重送不會產生第二筆訂單（冪等），重試才安全。
        existing = conn.execute("SELECT * FROM orders WHERE external_id = ?", (order.external_id,)).fetchone()
        if existing:
            return {**dict(existing), "duplicate": True}
        count = conn.execute("SELECT count(*) FROM orders").fetchone()[0]
        row = {
            "order_no": f"ERP-{count + 1:05d}",
            **order.model_dump(),
            "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        conn.execute(
            "INSERT INTO orders VALUES (:order_no, :external_id, :customer_name, :item, :people, :amount, :received_at)",
            row,
        )
        conn.commit()
    return {**row, "duplicate": False}


class SupplierBooking(BaseModel):
    po_id: int = Field(gt=0)
    supplier: str = Field(min_length=1, max_length=50)
    hotel: str = Field(min_length=1, max_length=50)
    rooms: int = Field(ge=1, le=20)
    nights: int = Field(ge=0, le=30)
    amount: int = Field(gt=0)


bookings = {}


@app.post("/api/supplier-bookings", dependencies=[Depends(require_key)])
def book_supplier(booking: SupplierBooking):
    """模擬供應商訂房 API：同一張採購單重送會拿到同一個確認編號。"""
    if state["fail_mode"]:
        raise HTTPException(503, "supplier system maintenance")
    if booking.po_id not in bookings:
        bookings[booking.po_id] = {**booking.model_dump(), "confirmation_no": f"SUP-{len(bookings) + 1:05d}"}
    return bookings[booking.po_id]


@app.get("/api/orders", dependencies=[Depends(require_key)])
def list_orders():
    with closing(db()) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM orders ORDER BY received_at DESC")]


@app.post("/admin/reset", dependencies=[Depends(require_key)])
def reset():
    """展示用：清空所有訂單與供應商訂房，重建展示資料時使用。"""
    with closing(db()) as conn:
        conn.execute("DELETE FROM orders")
        conn.commit()
    bookings.clear()
    state["fail_mode"] = False
    return {"ok": True}


@app.post("/admin/fail-mode", dependencies=[Depends(require_key)])
def set_fail_mode(mode: FailMode):
    """展示用：模擬 ERP 維修中，所有新訂單回 503。"""
    state["fail_mode"] = mode.on
    return state


@app.get("/", response_class=HTMLResponse)
def page():
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM orders ORDER BY received_at DESC").fetchall()
    cells = "".join(
        f"<tr><td>{r['order_no']}</td><td>{r['external_id']}</td><td>{r['customer_name']}</td>"
        f"<td>{r['item']}</td><td>{r['people']}</td><td>{r['amount']:,}</td><td>{r['received_at']}</td></tr>"
        for r in rows
    ) or "<tr><td colspan='7'>尚無訂單</td></tr>"
    status = "維修中（模擬故障）" if state["fail_mode"] else "正常"
    return f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>模擬 ERP</title>
<style>body{{font-family:"Microsoft JhengHei",sans-serif;margin:24px;color:#1f2a37;background:#fafaf7}}
table{{border-collapse:collapse;width:100%;background:#fff}}th,td{{border:1px solid #ccc;padding:8px;text-align:left}}
th{{background:#3b4a6b;color:#fff}}.tag{{color:#b42318;font-weight:700}}</style></head><body>
<h1>模擬 ERP 訂單系統</h1><p>模擬資料，代表系統商的 ERP。狀態：<span class="tag">{status}</span></p>
<table><tr><th>ERP 單號</th><th>來源編號</th><th>客人</th><th>品項</th><th>人數</th><th>金額</th><th>收到時間（UTC）</th></tr>
{cells}</table></body></html>"""
