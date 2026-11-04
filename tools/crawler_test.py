"""爬蟲測試（不花 API 額度）：對模擬供應商網站實際爬取，和網站的真實價格逐筆核對。

在 app 容器內執行：python crawler_test.py
會清空爬蟲資料表後重爬（測試結束保留最後一次的結果，後台與前台有資料可看）。
"""
import json
import time
import urllib.error
import urllib.request

from app import crawler
from app.db import connect, query

SUPPLIER = crawler.BASE_URL
results = []


def check(name, passed, detail=""):
    passed = bool(passed)
    results.append(passed)
    print(("PASS" if passed else "FAIL"), name, detail)


def supplier(path, method="POST"):
    request = urllib.request.Request(SUPPLIER + path, method=method)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


def clean():
    with connect() as conn:
        conn.execute("DELETE FROM crawled_prices")
        conn.execute("DELETE FROM crawled_hotels")
        conn.execute("DELETE FROM notifications WHERE kind = '供應商價格'")


supplier("/admin/reset")
clean()
first_run = query("SELECT coalesce(max(id), 0) AS n FROM crawl_runs")[0]["n"]

# 1. robots.txt
fetcher = crawler.Fetcher(SUPPLIER, min_delay=0.4)
check("讀到 robots.txt 的 Crawl-delay", crawler.Fetcher(SUPPLIER).delay == 1.0)
try:
    fetcher.get("/admin/truth")
    check("不抓 robots.txt 禁止的路徑", False)
except PermissionError:
    check("不抓 robots.txt 禁止的路徑", fetcher.blocked == ["/admin/truth"])

# 2. 第一次完整爬取，和網站真實價格逐筆核對
time.sleep(1.1)  # 上面連讀了兩次 robots.txt，先等限流的 1 秒視窗過去（見錯誤紀錄 J2-3）
start = time.monotonic()
first = crawler.run("測試", fetcher)
truth = supplier("/admin/truth", "GET")
check("爬完全部住宿與分頁（30 家、4 頁）", first["hotels"] == 30 and first["pages"] == 4, first)
check("每次請求有間隔（沒有被限流）", first["retries"] == 0 and time.monotonic() - start >= 0.4 * 33, first["retries"])
latest = {h["id"]: {r["room"]: r["price"] for r in h["rooms"]} for h in crawler.latest_prices()}
expected = {h["id"]: {p["room"]: p["price"] for p in h["prices"]} for h in truth["hotels"]}
check("抓到的價格和網站完全一致（含售完）", latest == expected,
      [k for k in expected if latest.get(k) != expected[k]][:3])
sold_out = sum(1 for h in expected.values() for p in h.values() if p is None)
check("售完的房型記成沒有價格", sold_out > 0 and sum(1 for h in latest.values() for p in h.values() if p is None) == sold_out, sold_out)
check("第一次爬取沒有「變動」", first["changes"] == 0 and first["alerts"] == 0)
log = query("SELECT * FROM crawl_runs WHERE id = %s", (first["id"],))[0]
check("爬取紀錄", log["status"] == "完成" and log["requests"] == first["requests"] and log["trigger"] == "測試")

# 3. 同一天再爬一次：價格沒變就不寫歷史
rows_before = query("SELECT count(*) AS n FROM crawled_prices")[0]["n"]
again = crawler.run("測試", crawler.Fetcher(SUPPLIER, min_delay=0.4))
check("價格沒變不重複寫入", again["changes"] == 0 and query("SELECT count(*) AS n FROM crawled_prices")[0]["n"] == rows_before)

# 4. 模擬隔天：價格變動 → 寫歷史、漲跌超過 15% 發通知
supplier("/admin/advance-day")
changed = crawler.run("測試", crawler.Fetcher(SUPPLIER, min_delay=0.4))
check("偵測到價格變動", changed["changes"] > 0, changed["changes"])
notices = query("SELECT title, body FROM notifications WHERE kind = '供應商價格'")
check("大幅漲跌發通知", changed["alerts"] > 0 and len(notices) == changed["alerts"], notices[:2])
check("通知寫出新舊價格", all("→" in n["body"] or "價格日期" in n["body"] for n in notices))
history = crawler.recent_changes(200)
check("後台查得到變動前後價格", len(history) == changed["changes"] and all("old_price" in h for h in history))
check("同一天重爬不重複通知", crawler.run("測試", crawler.Fetcher(SUPPLIER, min_delay=0.4))["alerts"] == 0)

# 5. 被限流：429 → 依 Retry-After 等待後重試成功
supplier("/admin/rate-limit?per_second=1")
fast = crawler.Fetcher(SUPPLIER, min_delay=0)
pages = [fast.get(f"/hotels?page={n}") for n in (1, 2, 3)]
check("遇到 429 會等待後重試成功", fast.retries > 0 and all("雲遊旅宿比價網" in p for p in pages), fast.retries)
supplier("/admin/reset")

# 6. 網站改版：找不到欄位要記錄清楚的錯誤
try:
    crawler.parse_detail("<html><body><h1>改版後的頁面</h1></body></html>")
    check("網站改版時回報錯誤", False)
except ValueError as error:
    check("網站改版時回報錯誤", "改版" in str(error))
items, next_link = crawler.parse_listing("<html><body>沒有資料</body></html>")
check("列表沒有資料時不會無限翻頁", items == [] and next_link is None)

# 7. API
def http(path, method="GET"):
    request = urllib.request.Request("http://localhost:8000" + path, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, {}


status, body = http("/api/supplier-prices?city=%E6%B2%96%E7%B9%A9")
check("比價 API（依城市）", status == 200 and len(body["hotels"]) == 6 and "模擬" in body["source"], len(body.get("hotels", [])))
status, _ = http("/api/admin/crawler/run", "POST")
check("沒登入不能執行爬蟲", status == 401)

# 留下乾淨的一次爬取結果給畫面使用：回到今天、清掉測試資料再爬一次
clean()
query("DELETE FROM crawl_runs WHERE id > %s AND trigger = '測試' RETURNING id", (first_run,))
crawler.run("測試後重建", crawler.Fetcher(SUPPLIER, min_delay=0.4))
print(f"\n{sum(results)}/{len(results)} 通過")
raise SystemExit(0 if all(results) else 1)
