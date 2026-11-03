"""串接模擬 ERP：成交的報價用 API 送過去，結果記在 erp_syncs，失敗可以重送。"""
import json
import os
import urllib.error
import urllib.request

from .db import query

ERP_URL = os.environ.get("ERP_URL", "http://erp:8000")
ERP_API_KEY = os.environ.get("ERP_API_KEY", "")
TIMEOUT = 5


class ErpError(Exception):
    pass


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        ERP_URL + path, data=data, method=method,
        headers={"Content-Type": "application/json", "X-API-Key": ERP_API_KEY},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise ErpError(f"ERP 回應 {error.code}：{error.read().decode(errors='replace')[:200]}")
    except (urllib.error.URLError, TimeoutError) as error:
        raise ErpError(f"連不上 ERP：{error}")


def push_quote(quote_id):
    """把一張成交報價送到 ERP。成功或失敗都記錄，回傳最新的同步狀態。"""
    rows = query(
        """
        SELECT q.id, q.customer_name, q.people, q.total_price, p.name AS package, h.name AS hotel
        FROM quotes q JOIN packages p ON p.id = q.package_id JOIN hotels h ON h.id = q.hotel_id
        WHERE q.id = %s
        """,
        (quote_id,),
    )
    quote = rows[0]
    order = {
        "external_id": f"Q-{quote['id']}",
        "customer_name": quote["customer_name"],
        "item": f"{quote['package']}＋{quote['hotel']}",
        "people": quote["people"],
        "amount": quote["total_price"],
    }
    try:
        result = call("POST", "/api/orders", order)
        status, order_no, error = "成功", result["order_no"], None
    except ErpError as exc:
        status, order_no, error = "失敗", None, str(exc)
    return query(
        """
        INSERT INTO erp_syncs (quote_id, status, attempts, erp_order_no, last_error, updated_at)
        VALUES (%s, %s, 1, %s, %s, now())
        ON CONFLICT (quote_id) DO UPDATE SET
            status = EXCLUDED.status,
            attempts = erp_syncs.attempts + 1,
            erp_order_no = coalesce(EXCLUDED.erp_order_no, erp_syncs.erp_order_no),
            last_error = EXCLUDED.last_error,
            updated_at = now()
        RETURNING *
        """,
        (quote_id, status, order_no, error),
    )[0]


def list_syncs():
    return query(
        """
        SELECT s.*, q.customer_name, q.total_price
        FROM erp_syncs s JOIN quotes q ON q.id = s.quote_id
        ORDER BY s.updated_at DESC
        """
    )


def failed_quote_ids():
    return [row["quote_id"] for row in query("SELECT quote_id FROM erp_syncs WHERE status = '失敗' ORDER BY quote_id")]


def set_fail_mode(on):
    return call("POST", "/admin/fail-mode", {"on": on})


def health():
    try:
        with urllib.request.urlopen(ERP_URL + "/health", timeout=TIMEOUT) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, TimeoutError):
        return {"status": "down"}
