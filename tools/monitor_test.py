"""監控測試（不花 API 額度）：指標端點、Prometheus 抓取與告警規則、Grafana 儀表板、告警信。

在 app 容器內執行（Grafana 密碼要另外帶進來）：
  docker exec -e GRAFANA_PASSWORD=... <專案名>-app-1 python monitor_test.py
"""
import base64
import json
import os
import re
import time
import urllib.error
import urllib.request

results = []
TOKEN = os.environ["METRICS_TOKEN"]
GRAFANA_PASSWORD = os.environ.get("GRAFANA_PASSWORD", "")


def check(name, passed, detail=""):
    passed = bool(passed)
    results.append(passed)
    print(("PASS" if passed else "FAIL"), name, detail)


def get(url, headers=None, data=None, method=None):
    request = urllib.request.Request(url, headers=headers or {}, data=data, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


# 1. 主系統的指標端點
status, _ = get("http://localhost:8000/metrics")
check("沒帶權杖看不到指標", status == 404)
status, _ = get("http://localhost:8000/metrics", {"Authorization": "Bearer wrong"})
check("權杖錯誤看不到指標", status == 404)
get("http://localhost:8000/api/packages")
get("http://localhost:8000/api/quotes/999999/events")
get("http://localhost:8000/no-such-page-12345")
status, body = get("http://localhost:8000/metrics", {"Authorization": f"Bearer {TOKEN}"})
check("帶權杖可以看到指標", status == 200)
# 只看 route 標籤（數值裡可能剛好有 0.0999999 這種數字，不能整份搜尋，見錯誤紀錄 I4-5）
routes = set(re.findall(r'route="([^"]*)"', body))
check("請求數依路由樣板記錄（不是實際網址）",
      "/api/quotes/{quote_id}/events" in routes and not any("999999" in r for r in routes), sorted(routes)[:8])
check("不存在的網址歸到「其他」，不會讓指標無限增加", "其他" in routes and not any("no-such-page" in r for r in routes))
for name in ("travel_http_request_seconds_bucket", "travel_ai_cost_today_usd", "travel_ai_cost_limit_usd",
             "travel_erp_sync_failed", "travel_purchase_orders_pending", "travel_db_up 1.0"):
    check(f"指標 {name.split()[0]}", name in body)

# 2. Prometheus：有在抓、規則有載入
target = None
for _ in range(30):
    _, raw = get("http://prometheus:9090/api/v1/targets")
    targets = json.loads(raw)["data"]["activeTargets"]
    target = next((t for t in targets if t["labels"]["job"] == "travel-app"), None)
    if target and target["health"] == "up":
        break
    time.sleep(2)
check("Prometheus 抓得到主系統", target and target["health"] == "up", target and target.get("lastError"))
_, raw = get("http://prometheus:9090/api/v1/rules")
rules = [r["name"] for g in json.loads(raw)["data"]["groups"] for r in g["rules"]]
check("告警規則全部載入（7 條）", len(rules) == 7, rules)
_, raw = get("http://prometheus:9090/api/v1/query?query=travel_ai_cost_limit_usd")
series = json.loads(raw)["data"]["result"]
check("Prometheus 查得到營運指標", series and float(series[0]["value"][1]) > 0, series)
_, raw = get("http://prometheus:9090/api/v1/alertmanagers")
check("Prometheus 有接上 Alertmanager", json.loads(raw)["data"]["activeAlertmanagers"])

# 3. Grafana：資料來源與儀表板自動建立
auth = {"Authorization": "Basic " + base64.b64encode(f"admin:{GRAFANA_PASSWORD}".encode()).decode()}
status, _ = get("http://grafana:3000/api/health")
check("Grafana 正常", status == 200)
# 剛啟動的 Grafana 健康檢查通過後，還要幾秒才會載入儀表板（全新環境才會遇到，見錯誤紀錄 I4-4）
for _ in range(30):
    status, raw = get("http://grafana:3000/api/dashboards/uid/travel-ops", auth)
    if status == 200:
        break
    time.sleep(2)
found = get("http://grafana:3000/api/search", auth)[1][:300] if status != 200 else ""
check("監控儀表板自動建立", status == 200 and json.loads(raw)["dashboard"]["title"] == "旅遊系統監控", f"{status} {found}")
status, _ = get("http://grafana:3000/api/dashboards/uid/travel-ops")
check("沒登入看不到 Grafana 儀表板", status == 401)
status, raw = get("http://grafana:3000/api/datasources/uid/prometheus/health", auth)
check("Grafana 連得到 Prometheus", status == 200 and json.loads(raw)["status"] == "OK", raw[:200])

# 4. 告警信：送一筆測試告警給 Alertmanager → 模擬信箱收到
name = f"監控測試告警{int(time.time())}"
alert = [{"labels": {"alertname": name, "severity": "warning"}, "annotations": {"summary": "測試用"}}]
status, _ = get("http://alertmanager:9093/api/v2/alerts", {"Content-Type": "application/json"},
                json.dumps(alert).encode(), "POST")
check("Alertmanager 收下告警", status == 200, status)
found = None
for _ in range(45):
    _, raw = get("http://mailpit:8025/api/v1/messages?limit=20")
    found = next((m for m in json.loads(raw)["messages"] if name in m["Subject"]), None)
    if found:
        break
    time.sleep(2)
check("告警信寄到 IT 信箱", found and found["To"][0]["Address"] == "it@travel.example", found and found["Subject"])

print(f"\n{sum(results)}/{len(results)} 通過")
raise SystemExit(0 if all(results) else 1)
