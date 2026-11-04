# 旅遊 AI 客服與報價系統

[![CI](https://github.com/wisly795/travel-ai-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/wisly795/travel-ai-agent/actions/workflows/ci.yml)

> 求職作品，作者：杜正威（以 Claude Code 輔助開發；本人負責需求、驗收與測試）。所有行程、飯店、價格、規定、供應商、客人皆為**模擬資料**。

客人用中文問行程，AI 查資料、算報價、依規定文件回答；業務在後台追蹤成交，系統自動同步到 ERP；AI 比價向供應商訂房、由人核准；官網透過合作夥伴 API 串接；n8n 負責通知、Email、報表與失敗重試；主管看儀表板；AI 品質用 20 題自動評測把關；其他 AI 工具可透過 MCP 直接操作本系統。

## 功能
| 模組 | 重點 |
|---|---|
| 查行程與報價 | 前端＋REST API＋PostgreSQL；價格一律由後端計算；出發日期（明天～一年內）、回程日 |
| AI 客服（Agent＋Tool Use） | Claude 自己決定呼叫 8 個工具；會換算「下個月 15 號」；建立報價前需客人同意 |
| RAG 規定問答 | 6 份規定 29 條，pgvector 向量搜尋，回答附出處，查不到就說沒提到 |
| 業務後台 | 儀表板、報價狀態（記錄操作者）、AI 對話與工具紀錄、轉接單、通知中心 |
| 帳號與角色 | 業務／主管／管理員；密碼 PBKDF2 加鹽雜湊；連錯 5 次鎖定；登入紀錄；管理員不能核准採購 |
| 營運儀表板 | 報價、成交率、營收趨勢、熱門行程、來源比例、AI 花費、待處理事項、AI 評測分數 |
| ERP 串接 | 成交自動送單，失敗記錄並重送，冪等不重複建單，可模擬故障 |
| 採購 Agent | 較強模型比價三家供應商（含免費取消期限），人核准（大額需主管），退回原因回饋給 AI |
| 官網串接 API | 合作夥伴金鑰（只存雜湊）、每分鐘上限（429）、資料隔離、API 文件；附模擬官網 |
| n8n 自動化與 Email | 新報價、每日報表、採購提醒、ERP 失敗重試；寄到模擬信箱 Mailpit，不重複寄 |
| AI 自動評測 | 20 題標準問答自動評分，後台一鍵執行，儀表板顯示分數 |
| MCP | 7 個工具，Claude Desktop／Claude Code 可直接使用 |
| 多 Agent 協作（LangGraph） | 分流拆題 → 報價／規定／接待專員（工具權限分離、平行）→ 程式檢查員（金額來源、條號、稱謂、假轉接）不通過退回重答；可和單一 Agent 切換、用同一套評測比較 |
| 微調向量模型 | 用客服口語問法微調 RAG 的多語向量模型，訓練／驗證／測試分開；沒看過的測試題前 3 名命中 23→25，轉 ONNX 量化上線 |
| 監控與告警 | /metrics（權杖保護）、Prometheus 7 條告警（含 AI 花費、評測分數）、Alertmanager 寄信、Grafana 儀表板 |
| React 前端 | React 18＋Vite，元件測試（Vitest），在 Docker 多階段建置 |
| CI | GitHub Actions：每次上傳建置全部容器、跑全部測試（假 AI，不花額度） |
| 旅遊網站前台 | 「晴空旅遊」：大圖首頁與搜尋、行程列表（條件在網址）、詳細頁即時試算與建立報價、探索台灣 22 縣市、旅遊須知、每頁右下角 AI 聊天泡泡；後台在 `/admin` |
| 政府開放資料 | 交通部觀光署景點 6,044、旅宿 15,652 筆，每天自動更新（比對新增／更新／不變／下架）；網站與 AI 客服都能查，註明來源 |
| 爬蟲 | 爬自建的模擬供應商網站（真實訂房網站禁止爬取）：遵守 robots.txt 與 Crawl-delay、429 重試、翻頁、價格歷史、漲跌 15% 通知 |

## 架構
```text
瀏覽器 ── app（FastAPI＋React 前端）── PostgreSQL＋pgvector
              │  ├─ Claude API（客服 Haiku、採購 Opus＋fallback；多 Agent 用 LangGraph 編排）
              │  ├─ erp：模擬 ERP／供應商
              │  ├─ /partner：合作夥伴 API ←── website：模擬官網（後端帶金鑰呼叫）
              │  └─ 呼叫 n8n Webhook
          n8n（排程、Webhook）── 呼叫 app 的自動化 API、寄信到 mailpit
          mcp（MCP 伺服器）── 呼叫 app 的公開 API
          prometheus ── 抓 app 的 /metrics ── alertmanager（寄信到 mailpit）、grafana（儀表板）
```

## 快速開始（Windows）
1. 安裝並開啟 Docker Desktop。
2. 執行 `Start.bat`。第一次會自動產生 `.env` 與 `登入資訊.txt`（隨機密碼、帳號、金鑰），並建置映像檔，約 10 分鐘。資料夾路徑有中文也可以（自動改用相容模式建置）。
3. 瀏覽器開啟 http://localhost:8100；業務後台用 `登入資訊.txt` 裡的帳號登入（sales／manager／admin）。
4. 要使用 AI 功能：到 console.anthropic.com 建立 API 金鑰，貼在 `.env` 的 `ANTHROPIC_API_KEY=` 後面，再執行一次 `Start.bat`。沒有金鑰時 AI 客服顯示「尚未啟用」，其他功能照常。
5. 停止：`Stop.bat`（資料會保留）。

| 服務 | 網址 |
|---|---|
| 主系統 | http://localhost:8100 |
| 模擬 ERP | http://localhost:8101 |
| 模擬官網（晴空旅遊） | http://localhost:8103 |
| 合作夥伴 API 文件 | http://localhost:8100/partner/docs |
| 模擬信箱 Mailpit | http://localhost:8025（只開在本機） |
| MCP | http://localhost:8102/mcp（只開在本機） |
| n8n 編輯畫面 | http://localhost:5678（只開在本機，第一次需建立本機帳號） |
| 業務後台 | http://localhost:8100/admin |
| 模擬供應商網站（爬蟲對象） | http://localhost:8104（只開在本機） |
| Grafana 監控儀表板 | http://localhost:3000（只開在本機，帳號 admin，密碼在 `登入資訊.txt`） |
| Prometheus | http://localhost:9090（只開在本機） |

## 安全設計
- 金鑰、密碼、權杖只在 `.env`，不進 Git、不進安裝包、不傳到前端；合作夥伴金鑰與登入工作階段只存雜湊。
- AI 的價格、退費、採購金額一律由程式計算；建立報價前需客人同意；採購只能建草稿，由人核准。
- 帳號分角色、操作留紀錄、登入失敗鎖定；合作夥伴每分鐘上限與資料隔離。
- 每日 AI 次數與費用上限；SQL 參數化；CSV 公式注入防護；n8n、MCP、Mailpit 只開在本機。

## 測試
| 測試 | 指令（在容器內） | 結果 |
|---|---|---|
| 全部 API | `python api_test.py http://localhost:8000` | 68/68 |
| 帳號 | `python auth_test.py` | 27/27 |
| 合作夥伴 API | `python partner_test.py` | 21/21 |
| AI 流程（假 AI，不花錢） | `python agent_test.py` | 29/29 |
| 多 Agent（假 AI） | `python multi_agent_test.py` | 24/24 |
| 採購流程（假 AI） | `python procurement_test.py` | 32/32 |
| 自動化 | `python automation_test.py` | 11/11 |
| Email（搭配 n8n 執行） | `python email_test.py prepare／check／dedupe` | 7/7 |
| 評測機制（假 AI） | `python eval_test.py` | 15/15 |
| RAG 檢索評測 | `python rag_eval.py` | 前 3 名 16/16（微調模型） |
| RAG 模型比較 | `python rag_compare.py` | 測試題前 3 名 23→25 |
| 監控 | `python monitor_test.py` | 21/21 |
| MCP（mcp 容器） | `python mcp_test.py` | 15/15 |
| 開放資料匯入 | `python opendata_test.py` | 23/23 |
| 爬蟲（和網站真實價格逐筆核對） | `python crawler_test.py` | 19/19 |
| 前端元件（Vitest，建置時執行） | `npm test` | 8/8 |
| 前台畫面（瀏覽器） | `tools/ui_site_test.py` | 通過 |
| 真實 AI 評測 | `python ai_eval.py [說明] [single|multi]` | 單一 20/20、多 Agent 20/20 |
| 全部一次跑（同 CI） | `bash tools/ci_run.sh` | GitHub Actions |

各階段的真實 Claude 測試與瀏覽器截圖見 `docs/*_測試報告.md`，截圖在 `docs/過程截圖/`。

## 文件
- `docs/從零重建指南.md`：從空白電腦到系統跑起來、測試通過、模型重新訓練、CI 設定（第一次看這份）
- `docs/交接文件.md`：架構、啟動、設定、維運、常見問題
- `docs/系統規格.md`、`docs/MCP接入說明.md`
- `docs/錯誤紀錄.md`：開發中遇到的問題與處理（含真實 AI 測試抓到的問題）
- `docs/評測/`：AI 評測報告（含單一與多 Agent 對照）

## 技術
Python 3.11、FastAPI、psycopg 3、PostgreSQL 15＋pgvector、fastembed、sentence-transformers（微調）、ONNX、Anthropic Claude API、LangGraph、BeautifulSoup（爬蟲）、政府開放資料、React 18、React Router、Vite、Vitest、n8n 2.45、Mailpit、MCP Python SDK、Prometheus、Alertmanager、Grafana、Docker Compose、GitHub Actions、Playwright。
