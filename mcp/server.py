"""旅遊報價系統的 MCP 伺服器：讓 Claude Desktop、Claude Code 等 AI 工具直接查行程、算報價、查規定。

MCP（Model Context Protocol）是讓 AI 工具連接外部系統的標準。這支程式不碰資料庫，
只呼叫旅遊系統公開的 REST API，所以權限和網頁一樣，價格也一律由旅遊系統計算。

執行方式：
- python server.py http   → Streamable HTTP，網址 http://localhost:8102/mcp（Claude Code 用）
- python server.py stdio  → 標準輸入輸出（Claude Desktop 用 docker run -i 啟動）
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

API = os.environ.get("TRAVEL_API", "http://app:8000")

mcp = FastMCP(
    "旅遊報價系統",
    instructions="查詢模擬旅遊行程、飯店、報價與旅遊規定。所有資料皆為模擬資料。報價與退費金額一律用工具計算，不要自己算。",
    host="0.0.0.0",
    port=8000,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["localhost:*", "127.0.0.1:*", "mcp:*"],
        allowed_origins=["http://localhost:*", "http://127.0.0.1:*"],
    ),
)


def call(method, path, body=None):
    request = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        detail = json.loads(error.read() or b"{}").get("detail", error.reason)
        if isinstance(detail, list):
            detail = "參數不正確"
        raise ValueError(f"旅遊系統回應 {error.code}：{detail}")


@mcp.tool()
def list_destinations() -> list[str]:
    """列出系統有的所有目的地。"""
    return call("GET", "/api/destinations")


@mcp.tool()
def search_packages(people: int, destination: str | None = None, max_price_per_person: int | None = None) -> list[dict]:
    """依人數、目的地、每人預算查詢行程，只回傳剩餘名額足夠的行程，價格由低到高。

    Args:
        people: 人數 1 到 20
        destination: 目的地，例如 沖繩；不限就不填
        max_price_per_person: 每人預算上限（新台幣）；不限就不填
    """
    params = {"people": people}
    if destination:
        params["destination"] = destination
    if max_price_per_person:
        params["max_price"] = max_price_per_person
    return call("GET", "/api/packages?" + urllib.parse.urlencode(params))


@mcp.tool()
def list_hotels(destination: str) -> list[dict]:
    """列出某個目的地可搭配的飯店與每晚房價。"""
    return call("GET", "/api/hotels?" + urllib.parse.urlencode({"destination": destination}))


@mcp.tool()
def calculate_quote(package_id: int, hotel_id: int, people: int, departure_date: str | None = None) -> dict:
    """計算報價明細（行程費、住宿費、房間數、晚數、總價），不會存檔。給出發日期（YYYY-MM-DD）會一併算回程日。"""
    return call("POST", "/api/quotes/preview", {"package_id": package_id, "hotel_id": hotel_id, "people": people,
                                                "departure_date": departure_date})


@mcp.tool()
def search_policy(question: str) -> list[dict]:
    """從旅遊規定文件（取消退費、行李、簽證、保險、付款、兒童長者）找出最相關的條文與出處。空清單代表文件沒有提到。"""
    return call("GET", "/api/policies/search?" + urllib.parse.urlencode({"q": question}))


@mcp.tool()
def calculate_refund(total_price: int, days_before_departure: int | None = None,
                     departure_date: str | None = None) -> dict:
    """依取消與退費規定計算取消時扣多少、退多少。退費金額一律用這個工具，不要自己算。

    Args:
        total_price: 團費（報價總價，含行程與住宿，新台幣）
        days_before_departure: 距離出發還有幾天，出發當天是 0（和 departure_date 擇一）
        departure_date: 出發日期 YYYY-MM-DD，系統會用今天算天數（和 days_before_departure 擇一）
    """
    return call("POST", "/api/refunds/calculate", {"total_price": total_price,
                                                   "days_before_departure": days_before_departure,
                                                   "departure_date": departure_date})


@mcp.tool()
def create_quote(customer_name: str, package_id: int, hotel_id: int, people: int,
                 departure_date: str | None = None) -> dict:
    """正式建立報價單並存檔。只在使用者明確要求建立報價、而且已看過 calculate_quote 的明細後才使用。"""
    return call("POST", "/api/quotes", {
        "customer_name": customer_name, "package_id": package_id, "hotel_id": hotel_id, "people": people,
        "departure_date": departure_date,
    })


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "http"
    mcp.run(transport="stdio" if mode == "stdio" else "streamable-http")
