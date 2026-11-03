# F 階段 MCP：測試報告

- 日期：2026-11-03
- 伺服器：`mcp/server.py`（官方 MCP Python SDK 1.30.0，FastMCP），容器 `travelquote-mcp`，本機 http://localhost:8102/mcp
- 接入說明：`docs/MCP接入說明.md`
- 輸出紀錄：`docs/過程截圖/F_MCP/Claude透過MCP操作系統_實際輸出.txt`

## 1. MCP 用戶端測試（不花 API 額度，`tools/mcp_test.py`）：15/15
| 連線方式 | 檢查 |
|---|---|
| Streamable HTTP | 列出 7 個工具、查目的地、查行程、試算報價 107,200、查規定（行李第 4 條）、計算退費（65,600 × 30% = 19,680）、錯誤參數回報錯誤、建立報價單 |
| stdio | 同上（不含建立報價） |

## 2. Claude 透過 MCP 操作系統（`tools/mcp_claude_demo.py`）
外部的 Claude 不知道系統怎麼寫，只透過 MCP 拿到工具清單，自己決定呼叫順序：
`search_packages → list_hotels → search_policy → calculate_quote → calculate_refund`
回答總價 NT$ 82,400、出發前 10 天取消扣 30%，附出處取消與退費規定第 3 條。

## 3. 回歸
全部 API 54/54（新增試算報價、退費計算 API）。

## 實測發現
1. **MCP 少了退費工具，外部 AI 就自己算錢**：第一次示範時，Claude 自己算出扣款 19,680 元。新增 `POST /api/refunds/calculate` 與 MCP 工具 `calculate_refund`，重跑後 Claude 改用工具計算。
2. **規定文件「團費」定義不清**：Claude 用總價（含住宿）82,400 計算扣款；條文只寫「扣除團費」，沒說明是否含住宿。真實上線前要請業務確認並改寫條文，這是文件問題，不是程式問題。
3. 外部 AI 用了 Markdown 粗體（**…**）；這是 MCP 用戶端自己的格式，不受系統規則控制。

## 未測
- 實際在使用者的 Claude Desktop 加入設定（需要使用者電腦上的 Claude Desktop 設定檔）
