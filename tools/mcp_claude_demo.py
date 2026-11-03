"""示範：Claude 透過 MCP 操作旅遊系統（會花一點 API 額度）。

這裡的 Claude 不是系統內建的 AI 客服，而是一個「外部」的 AI 應用：
它不知道系統怎麼寫，只透過 MCP 拿到工具清單，就能自己查行程、算報價、查規定。
"""
import asyncio

from anthropic import AsyncAnthropic
from anthropic.lib.tools.mcp import async_mcp_tool
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

QUESTION = ("我們 2 個人想去京都 5 天，住最便宜的飯店，總價多少？"
            "另外如果出發前 10 天取消，會扣多少比例？請用繁體中文簡短回答，並附上規定出處。")


async def main():
    client = AsyncAnthropic()
    async with streamablehttp_client("http://mcp:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            print("從 MCP 取得的工具：", [tool.name for tool in tools])
            runner = client.beta.messages.tool_runner(
                model="claude-haiku-5-5",
                max_tokens=4000,
                tools=[async_mcp_tool(tool, session) for tool in tools],
                messages=[{"role": "user", "content": QUESTION}],
            )
            print("\n問題：", QUESTION)
            async for message in runner:
                for block in message.content:
                    if block.type == "tool_use":
                        print(f"\n→ Claude 呼叫 MCP 工具 {block.name}：{block.input}")
                    elif block.type == "text" and block.text.strip():
                        print("\nClaude：", block.text)


asyncio.run(main())
