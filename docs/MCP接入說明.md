# MCP 接入說明

旅遊報價系統提供 MCP 伺服器，讓支援 MCP 的 AI 工具直接查行程、算報價、算退費、查規定、建立報價單。系統要先用 `Start.bat` 或 `docker compose -p travelquote up -d` 啟動。

## 提供的 7 個工具
| 工具 | 用途 | 會不會改資料 |
|---|---|---|
| list_destinations | 列出目的地 | 不會 |
| search_packages | 依人數、目的地、預算查行程 | 不會 |
| list_hotels | 列出目的地的飯店 | 不會 |
| calculate_quote | 試算報價明細（不存檔） | 不會 |
| search_policy | 查旅遊規定條文與出處（RAG） | 不會 |
| calculate_refund | 依規定計算取消扣款與退款 | 不會 |
| create_quote | 正式建立報價單 | 會 |

MCP 伺服器只呼叫系統公開的 REST API，看不到業務後台、採購或客人資料。

## Claude Code（Streamable HTTP）
```bash
claude mcp add --transport http travel-quote http://localhost:8102/mcp
```
加好後在 Claude Code 問「2 個人去京都 5 天多少錢？」就會使用這些工具。

## Claude Desktop（stdio）
在 Claude Desktop 的設定檔 `claude_desktop_config.json` 加入：
```json
{
  "mcpServers": {
    "travel-quote": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "--network", "travelquote_default",
               "-e", "TRAVEL_API=http://app:8000",
               "travelquote-mcp", "python", "server.py", "stdio"]
    }
  }
}
```
存檔後重新開啟 Claude Desktop。

## 安全
- MCP 的 HTTP 埠只開在本機（127.0.0.1:8102），並啟用 DNS rebinding 防護（只接受 localhost、127.0.0.1、容器內的 mcp 主機名）。
- 公開網站部署時不開放 MCP 埠。

## 測試
- `tools/mcp_test.py`：用官方 MCP 用戶端，以 HTTP 與 stdio 兩種方式列出工具並逐一呼叫，15/15 通過。
- `tools/mcp_claude_demo.py`：Claude（claude-haiku-5-5）透過 MCP 回答「2 人京都 5 天最便宜總價＋出發前 10 天取消扣多少」，實際輸出存在 `docs/過程截圖/F_MCP/`。
