"""產生 n8n 流程檔（JSON）。改流程時改這支程式再重新產生，比直接手改 JSON 不容易出錯。"""
import json
from pathlib import Path

OUT = Path(__file__).parent / "workflows"
APP = "={{ $env.APP_URL }}"
TOKEN_HEADER = {"parameters": [{"name": "X-Staff-Token", "value": "={{ $env.AUTOMATION_TOKEN }}"}]}


def http(name, method, path, position, body=None):
    params = {"method": method, "url": f"{APP}{path}", "sendHeaders": True, "headerParameters": TOKEN_HEADER, "options": {}}
    if body:
        params.update({"sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify(" + body + ") }}"})
    return {"name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": position, "parameters": params}


def schedule(name, cron, position):
    return {"name": name, "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": position,
            "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": cron}]}}}


def code(name, js, position):
    return {"name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": position,
            "parameters": {"mode": "runOnceForAllItems", "jsCode": js}}


def only_new(name, position):
    """通知 API 回傳 created=false 代表這件事已經通知過，就不再寄信（避免排程重複寄）。"""
    return code(name, "return $input.all().filter(item => item.json.created);", position)


def email(name, to_expr, position):
    """寄到模擬信箱 Mailpit 的寄信 API；收件人由 to_expr 決定。"""
    body = ("{ From: { Email: 'noreply@travel.example', Name: '旅遊報價系統' }, To: [{ Email: " + to_expr + " }],"
            " Subject: '[旅遊報價系統] ' + $json.notification.title,"
            " Text: $json.notification.body + String.fromCharCode(10, 10) + '後台：' + $env.SITE_URL"
            " + String.fromCharCode(10) + '（模擬信件，由 n8n 自動寄出）' }")
    params = {"method": "POST", "url": "={{ $env.MAILPIT_URL }}/api/v1/send", "sendBody": True,
              "specifyBody": "json", "jsonBody": "={{ JSON.stringify(" + body + ") }}", "options": {}}
    return {"name": name, "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": position, "parameters": params}


def workflow(id, name, nodes, links):
    # 排程流程多加一個「手動執行」節點，接到同樣的下一步：方便在編輯畫面或用指令測試
    trigger = nodes[0]
    if trigger["type"] == "n8n-nodes-base.scheduleTrigger":
        manual = {"name": "手動執行", "type": "n8n-nodes-base.manualTrigger", "typeVersion": 1,
                  "position": [trigger["position"][0], trigger["position"][1] + 220], "parameters": {}}
        nodes = nodes + [manual]
        links = links + [("手動執行", target) for source, target in links if source == trigger["name"]]
    connections = {}
    for source, target in links:
        connections.setdefault(source, {"main": [[]]})["main"][0].append({"node": target, "type": "main", "index": 0})
    for i, node in enumerate(nodes):
        node["id"] = f"{id}-node{i}"
    return {"id": id, "name": name, "nodes": nodes, "connections": connections, "active": False,
            "settings": {"executionOrder": "v1", "timezone": "Asia/Taipei"}, "pinData": {}}


NOTIFY = "通知中心"

flows = [
    workflow("tqNewQuote000001", "1 新報價通知", [
        {"name": "收到新報價", "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 0],
         "webhookId": "5d1f3c2a-7b8e-4f6a-9c0d-1e2f3a4b5c6d",
         "parameters": {"httpMethod": "POST", "path": "new-quote", "responseMode": "onReceived", "options": {}}},
        http(NOTIFY, "POST", "/api/notifications", [260, 0],
             "{ kind: '新報價', title: '新報價 #' + $json.body.id + '：' + $json.body.customer_name,"
             " body: $json.body.package + '＋' + $json.body.hotel + '｜' + $json.body.people + ' 人｜NT$ '"
             " + Number($json.body.total_price).toLocaleString('en-US') + '｜來源：'"
             " + ({ ai: 'AI 客服', partner: '官網串接' }[$json.body.source] || '網頁') + '。請在 24 小時內聯絡客人。',"
             " dedupe_key: 'quote-' + $json.body.id }"),
        only_new("只寄新的通知", [520, 0]),
        email("寄信給業務", "$env.SALES_EMAIL", [760, 0]),
    ], [("收到新報價", NOTIFY), (NOTIFY, "只寄新的通知"), ("只寄新的通知", "寄信給業務")]),

    workflow("tqDailyReport001", "2 每日報表", [
        schedule("每天 9 點", "0 9 * * *", [0, 0]),
        http("取得昨日數據", "GET", "/api/reports/daily", [240, 0]),
        code("整理報表文字", """const r = $input.first().json;
const lines = [
  `報價 ${r.quotes} 張（AI 客服 ${r.ai_quotes} 張）`,
  `成交 ${r.deals} 張，金額 NT$ ${Number(r.deal_amount).toLocaleString('en-US')}`,
  `熱門行程：${r.top_packages.length ? r.top_packages.join('、') : '無'}`,
  `AI 對話 ${r.ai_turns} 次，花費 US$ ${r.ai_cost_usd.toFixed(4)}`,
];
return [{ json: { date: r.date, text: lines.join(String.fromCharCode(10)) } }];""", [480, 0]),
        http(NOTIFY, "POST", "/api/notifications", [720, 0],
             "{ kind: '每日報表', title: $json.date + ' 每日報表', body: $json.text, dedupe_key: 'daily-' + $json.date }"),
        only_new("只寄新的通知", [960, 0]),
        email("寄信給主管", "$env.MANAGER_EMAIL", [1200, 0]),
    ], [("每天 9 點", "取得昨日數據"), ("取得昨日數據", "整理報表文字"), ("整理報表文字", NOTIFY),
        (NOTIFY, "只寄新的通知"), ("只寄新的通知", "寄信給主管")]),

    workflow("tqPoReminder0001", "3 採購核准提醒", [
        schedule("每小時", "0 * * * *", [0, 0]),
        http("待核准採購單", "GET", "/api/purchase-orders/pending?older_than_hours=0", [240, -100]),
        http("超過 24 小時", "GET", "/api/purchase-orders/pending?older_than_hours=24", [240, 100]),
        code("只留有資料的", "return $input.all().filter(item => item.json.id);", [480, -100]),
        code("只留有資料的（逾時）", "return $input.all().filter(item => item.json.id);", [480, 100]),
        http("通知待核准", "POST", "/api/notifications", [720, -100],
             "{ kind: '採購待核准', title: '採購單 #' + $json.id + ' 待' + $json.approver_role + '核准',"
             " body: '金額 NT$ ' + Number($json.amount).toLocaleString('en-US') + '（報價 #' + $json.quote_id + '），請到後台採購頁處理。',"
             " dedupe_key: 'po-' + $json.id }"),
        http("再次提醒", "POST", "/api/notifications", [720, 100],
             "{ kind: '採購待核准', title: '再次提醒：採購單 #' + $json.id + ' 超過 24 小時未處理',"
             " body: '需要' + $json.approver_role + '核准，金額 NT$ ' + Number($json.amount).toLocaleString('en-US') + '。',"
             " dedupe_key: 'po-' + $json.id + '-24h' }"),
        only_new("只寄新的通知", [960, -100]),
        only_new("只寄新的通知（逾時）", [960, 100]),
        # 標題含「主管」就寄主管，否則寄業務
        email("寄信給核准人", "($json.notification.title.includes('主管') ? $env.MANAGER_EMAIL : $env.SALES_EMAIL)", [1200, -100]),
        email("寄信給核准人（逾時）", "($json.notification.body.includes('主管') ? $env.MANAGER_EMAIL : $env.SALES_EMAIL)", [1200, 100]),
    ], [("每小時", "待核准採購單"), ("每小時", "超過 24 小時"), ("待核准採購單", "只留有資料的"),
        ("超過 24 小時", "只留有資料的（逾時）"), ("只留有資料的", "通知待核准"), ("只留有資料的（逾時）", "再次提醒"),
        ("通知待核准", "只寄新的通知"), ("再次提醒", "只寄新的通知（逾時）"),
        ("只寄新的通知", "寄信給核准人"), ("只寄新的通知（逾時）", "寄信給核准人（逾時）")]),

    workflow("tqErpRetry000001", "4 ERP 同步失敗重試", [
        schedule("每 10 分鐘", "*/10 * * * *", [0, 0]),
        http("重送失敗的同步", "POST", "/api/erp/retry-failed", [240, 0]),
        code("重試 3 次仍失敗", """const detail = $input.first().json.still_failed_detail || [];
return detail.filter(d => d.attempts >= 3).map(d => ({ json: d }));""", [480, 0]),
        http("通知負責人", "POST", "/api/notifications", [720, 0],
             "{ kind: '同步失敗', title: '報價 #' + $json.quote_id + ' 同步 ERP 已失敗 ' + $json.attempts + ' 次',"
             " body: '最後錯誤：' + $json.last_error + '。系統會繼續每 10 分鐘重試，請確認 ERP 狀態或聯絡系統商。',"
             " dedupe_key: 'erp-fail-' + $json.quote_id }"),
        only_new("只寄新的通知", [960, 0]),
        email("寄信給 IT", "$env.IT_EMAIL", [1200, 0]),
    ], [("每 10 分鐘", "重送失敗的同步"), ("重送失敗的同步", "重試 3 次仍失敗"), ("重試 3 次仍失敗", "通知負責人"),
        ("通知負責人", "只寄新的通知"), ("只寄新的通知", "寄信給 IT")]),

    # 政府開放資料每天更新一次（官方每天更新）；主系統在背景下載、比對、寫入，結果記在匯入紀錄
    workflow("tqOpenData000001", "5 政府開放資料每日更新", [
        schedule("每天 04:30", "30 4 * * *", [0, 0]),
        http("匯入景點與旅宿", "POST", "/api/admin/opendata/import", [240, 0]),
    ], [("每天 04:30", "匯入景點與旅宿")]),
]

for flow in flows:
    (OUT / f"{flow['id']}.json").write_text(json.dumps(flow, ensure_ascii=False, indent=2), encoding="utf-8")
    print("寫入", flow["name"])
