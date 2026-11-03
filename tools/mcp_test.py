"""MCP 伺服器測試：用官方 MCP 用戶端連線，列出工具並逐一呼叫（不花 API 額度）。

在 mcp 容器內執行：python mcp_test.py
同時測兩種連線方式：Streamable HTTP（Claude Code 用）與 stdio（Claude Desktop 用）。
"""
import asyncio
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

results = []


def check(name, passed, detail=""):
    results.append(passed)
    print(("PASS" if passed else "FAIL"), name, detail)


def data(result):
    """工具結果：優先用結構化內容，沒有就解析文字。"""
    if result.structuredContent is not None:
        value = result.structuredContent
        return value.get("result", value) if isinstance(value, dict) and set(value) == {"result"} else value
    return json.loads(result.content[0].text)


async def exercise(session, label):
    await session.initialize()
    tools = {tool.name for tool in (await session.list_tools()).tools}
    expected = {"list_destinations", "search_packages", "list_hotels", "calculate_quote", "search_policy",
                "calculate_refund", "create_quote"}
    check(f"[{label}] 列出 7 個工具", tools == expected, sorted(tools))
    refund = data(await session.call_tool("calculate_refund", {"total_price": 65600, "days_before_departure": 10}))
    check(f"[{label}] 計算退費（系統計算）", refund["deduct_percent"] == 30 and refund["deduction"] == 19680, refund)

    destinations = data(await session.call_tool("list_destinations", {}))
    check(f"[{label}] 查目的地", "沖繩" in destinations, destinations)
    packages = data(await session.call_tool("search_packages", {"people": 4, "destination": "沖繩", "max_price_per_person": 30000}))
    check(f"[{label}] 查行程", {p["name"] for p in packages} == {"海島放鬆 4 日", "親子同樂 5 日"})
    hotels = data(await session.call_tool("list_hotels", {"destination": "沖繩"}))
    seaside = next(h for h in hotels if h["name"] == "海風飯店")
    island = next(p for p in packages if p["name"] == "海島放鬆 4 日")
    quote = data(await session.call_tool("calculate_quote", {"package_id": island["id"], "hotel_id": seaside["id"], "people": 4}))
    check(f"[{label}] 試算報價（系統計算）", quote["total_price"] == 107200, quote["total_price"])
    policy = data(await session.call_tool("search_policy", {"question": "充電寶可以放託運嗎"}))
    check(f"[{label}] 查規定", policy and policy[0]["source"].startswith("行李規定 第4條"))
    bad = await session.call_tool("calculate_quote", {"package_id": island["id"], "hotel_id": seaside["id"], "people": 0})
    check(f"[{label}] 錯誤參數回報錯誤", bad.isError)
    return island["id"], seaside["id"]


async def main():
    async with streamablehttp_client("http://localhost:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            package_id, hotel_id = await exercise(session, "HTTP")
            created = data(await session.call_tool("create_quote", {
                "customer_name": "MCP 測試", "package_id": package_id, "hotel_id": hotel_id, "people": 2,
            }))
            check("[HTTP] 建立報價單", created["id"] > 0 and created["total_price"] == 22000 * 2 + 3200 * 1 * 3)

    params = StdioServerParameters(command="python", args=["/code/server.py", "stdio"],
                                   env={"TRAVEL_API": "http://app:8000"})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await exercise(session, "stdio")

    print(f"\n{sum(results)}/{len(results)} 通過")
    raise SystemExit(0 if all(results) else 1)


asyncio.run(main())
