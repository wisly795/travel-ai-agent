"""爬蟲：抓模擬供應商網站「雲遊旅宿比價網」的住宿與每晚價格，保存歷史、偵測價格變動。

有禮貌的爬蟲（真實工作也要這樣做）：
- 先讀 robots.txt，不抓被禁止的路徑，遵守 Crawl-delay（每次請求之間至少間隔）
- User-Agent 表明身分；遇到 429／5xx 依 Retry-After 等待後重試，最多 3 次
- 跟著「下一頁」連結翻頁，有頁數上限，避免無限迴圈
- 解析失敗（網站改版找不到欄位）記錄錯誤，不中斷整次爬取
- 價格只在有變動時寫入歷史；漲跌超過門檻就發通知
"""
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime

from bs4 import BeautifulSoup

from . import automation
from .db import connect, query

BASE_URL = os.environ.get("SUPPLIER_URL", "http://supplier:8000")
# HTTP 標頭只能用英文字元（latin-1），寫中文會出錯（見錯誤紀錄 J2-2）
USER_AGENT = "TravelQuoteBot/1.0 (+demo project; crawls the simulated supplier site only)"
MAX_PAGES = 30
MAX_RETRIES = 3
ALERT_RATIO = 0.15  # 漲跌超過 15% 通知採購
_lock = threading.Lock()


class Fetcher:
    """負責「怎麼抓」：robots.txt、間隔、重試。和「抓什麼、怎麼解析」分開，方便測試與換網站。"""

    def __init__(self, base_url, min_delay=None, sleep=time.sleep):
        self.base_url = base_url.rstrip("/")
        self.sleep = sleep
        self.requests, self.retries, self.blocked, self._last, self.delay = 0, 0, [], 0.0, 1.0
        # 先讀 robots.txt，再依它的 Crawl-delay 決定間隔（測試可以用 min_delay 指定）
        self.robots = urllib.robotparser.RobotFileParser()
        self.robots.set_url(f"{self.base_url}/robots.txt")
        self.robots.parse(self._get(f"{self.base_url}/robots.txt", check_robots=False).splitlines())
        delay = self.robots.crawl_delay(USER_AGENT)
        self.delay = float(delay if delay is not None else 1) if min_delay is None else min_delay

    def allowed(self, url):
        return self.robots.can_fetch(USER_AGENT, url)

    def get(self, path):
        url = urllib.parse.urljoin(self.base_url + "/", path.lstrip("/"))
        if not self.allowed(url):
            self.blocked.append(path)
            raise PermissionError(f"robots.txt 不允許：{path}")
        return self._get(url)

    def _get(self, url, check_robots=True):
        for attempt in range(MAX_RETRIES + 1):
            wait = self.delay - (time.monotonic() - self._last)
            if check_robots and wait > 0:
                self.sleep(wait)
            self._last = time.monotonic()
            self.requests += 1
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    return response.read().decode("utf-8")
            except urllib.error.HTTPError as error:
                if error.code in (429, 500, 502, 503) and attempt < MAX_RETRIES:
                    self.retries += 1
                    self.sleep(float(error.headers.get("Retry-After") or 2 ** attempt))
                    continue
                raise


def parse_listing(text):
    """列表頁：每家住宿的編號與詳細頁連結，以及下一頁連結。"""
    soup = BeautifulSoup(text, "html.parser")
    hotels = [{"id": card["data-id"], "href": card.select_one(".name a")["href"]}
              for card in soup.select("article.hotel[data-id]") if card.select_one(".name a")]
    next_link = soup.select_one("nav.pager a[rel=next]")
    return hotels, next_link["href"] if next_link else None


def parse_detail(text):
    """詳細頁：名稱、城市、星級、價格日期、各房型價格（售完為 None）。找不到必要欄位就丟出錯誤。"""
    soup = BeautifulSoup(text, "html.parser")
    root = soup.select_one("article.hotel-detail[data-id]")
    if not root:
        raise ValueError("找不到住宿資料區塊（網站可能改版）")
    rooms = []
    for row in root.select("table.rooms tr.room"):
        name, price = row.select_one(".room-name"), row.select_one(".price")
        if not name or not price:
            raise ValueError("房型表格欄位不完整（網站可能改版）")
        raw = price.get("data-price", "").strip()
        rooms.append({"room": name.get_text(strip=True), "price": int(raw) if raw.isdigit() else None,
                      "promo": row.select_one(".promo") is not None})
    if not rooms:
        raise ValueError("沒有任何房型（網站可能改版）")
    return {"id": root["data-id"], "name": root.select_one(".name").get_text(strip=True),
            "city": root.select_one(".city").get_text(strip=True),
            "stars": int(root.select_one(".stars").get("data-stars", 0)),
            "price_date": root.select_one(".updated").get("data-date"), "rooms": rooms}


def crawl(fetcher, start="/hotels"):
    """從列表第一頁開始，翻完所有頁，再逐一抓詳細頁。回傳（住宿資料, 錯誤清單, 頁數）。"""
    found, errors, pages, path = [], [], 0, start
    while path and pages < MAX_PAGES:
        hotels, path = parse_listing(fetcher.get(path))
        pages += 1
        found += hotels
    results = []
    for hotel in found:
        try:
            item = parse_detail(fetcher.get(hotel["href"]))
            item["url"] = urllib.parse.urljoin(fetcher.base_url + "/", hotel["href"].lstrip("/"))
            results.append(item)
        except Exception as error:  # 一家失敗不影響其他家
            errors.append(f"{hotel['id']}：{type(error).__name__}：{error}"[:300])
    return results, errors, pages


def save(items):
    """寫入住宿與價格；價格和上一次不同才寫一筆歷史。回傳價格變動清單。"""
    changes = []
    with connect() as conn:
        for item in items:
            conn.execute(
                """INSERT INTO crawled_hotels (supplier_id, name, city, stars, url, last_seen) VALUES (%s, %s, %s, %s, %s, now())
                   ON CONFLICT (supplier_id) DO UPDATE SET name = EXCLUDED.name, city = EXCLUDED.city, stars = EXCLUDED.stars,
                   url = EXCLUDED.url, last_seen = now()""",
                (item["id"], item["name"], item["city"], item["stars"], item["url"]),
            )
            for room in item["rooms"]:
                last = conn.execute(
                    "SELECT price FROM crawled_prices WHERE supplier_id = %s AND room = %s ORDER BY id DESC LIMIT 1",
                    (item["id"], room["room"]),
                ).fetchone()
                old = last["price"] if last else None
                if last and old == room["price"]:
                    continue
                conn.execute(
                    "INSERT INTO crawled_prices (supplier_id, room, price, promo, price_date) VALUES (%s, %s, %s, %s, %s)",
                    (item["id"], room["room"], room["price"], room["promo"], item["price_date"]),
                )
                if last:
                    changes.append({"id": item["id"], "name": item["name"], "city": item["city"], "room": room["room"],
                                    "old": old, "new": room["price"], "price_date": item["price_date"]})
    return changes


def alert(changes):
    """漲跌超過門檻、或售完／恢復販售，發通知給採購（同一天同一間房只通知一次）。"""
    sent = 0
    for c in changes:
        if c["old"] and c["new"]:
            ratio = (c["new"] - c["old"]) / c["old"]
            if abs(ratio) < ALERT_RATIO:
                continue
            title = f"{c['city']} {c['name']} {c['room']} {'漲' if ratio > 0 else '降'} {abs(ratio):.0%}"
            body = f"每晚 NT$ {c['old']:,} → NT$ {c['new']:,}（價格日期 {c['price_date']}，來源：模擬供應商網站）"
        else:
            title = f"{c['city']} {c['name']} {c['room']} {'售完' if not c['new'] else '恢復販售'}"
            body = f"價格日期 {c['price_date']}，來源：模擬供應商網站"
        result = automation.add_notification("供應商價格", title, body, f"price-{c['id']}-{c['room']}-{c['price_date']}")
        sent += bool(result and result.get("created"))
    return sent


def run(trigger="手動", fetcher=None):
    """完整爬一次並記錄。同時間只跑一次。"""
    if not _lock.acquire(blocking=False):
        return {"status": "busy"}
    run_id = query("INSERT INTO crawl_runs (trigger) VALUES (%s) RETURNING id", (trigger,))[0]["id"]
    started = time.monotonic()
    try:
        fetcher = fetcher or Fetcher(BASE_URL)
        items, errors, pages = crawl(fetcher)
        changes = save(items)
        alerts = alert(changes)
        stats = {"pages": pages, "hotels": len(items), "changes": len(changes), "alerts": alerts,
                 "requests": fetcher.requests, "retries": fetcher.retries, "errors": errors}
        status = "完成" if not errors else "部分失敗"
    except Exception as error:
        stats = {"errors": [f"{type(error).__name__}：{error}"[:300]]}
        status = "失敗"
    finally:
        _lock.release()
    query(
        """UPDATE crawl_runs SET status = %s, finished_at = now(), seconds = %s, pages = %s, hotels = %s, changes = %s,
           alerts = %s, requests = %s, retries = %s, errors = %s WHERE id = %s RETURNING id""",
        (status, round(time.monotonic() - started, 1), stats.get("pages"), stats.get("hotels"), stats.get("changes"),
         stats.get("alerts"), stats.get("requests"), stats.get("retries"),
         json.dumps(stats["errors"], ensure_ascii=False), run_id),
    )
    return {"status": status, "id": run_id, **stats}


def run_background(trigger):
    threading.Thread(target=run, args=(trigger,), daemon=True).start()


def latest_prices(city=None):
    """每家住宿每個房型的最新價格（給後台與前台比價參考）。"""
    rows = query(
        """SELECT h.supplier_id, h.name, h.city, h.stars, h.url, p.room, p.price, p.promo, p.price_date, p.created_at
           FROM crawled_hotels h
           JOIN LATERAL (SELECT DISTINCT ON (room) room, price, promo, price_date, created_at FROM crawled_prices
                         WHERE supplier_id = h.supplier_id ORDER BY room, id DESC) p ON true
           WHERE %s::text IS NULL OR h.city = %s
           ORDER BY h.city, h.supplier_id, p.room""",
        (city, city),
    )
    hotels = {}
    for r in rows:
        hotel = hotels.setdefault(r["supplier_id"], {"id": r["supplier_id"], "name": r["name"], "city": r["city"],
                                                     "stars": r["stars"], "url": r["url"], "rooms": []})
        hotel["rooms"].append({"room": r["room"], "price": r["price"], "promo": r["promo"], "price_date": r["price_date"]})
    return list(hotels.values())


def recent_changes(limit=30):
    """最近的價格變動（同一間房前後兩筆比較）。"""
    return query(
        """SELECT * FROM (
             SELECT p.supplier_id, h.name, h.city, p.room, p.price AS new_price, p.price_date, p.created_at,
                    lag(p.price) OVER (PARTITION BY p.supplier_id, p.room ORDER BY p.id) AS old_price,
                    lag(p.id) OVER (PARTITION BY p.supplier_id, p.room ORDER BY p.id) AS prev_id
             FROM crawled_prices p JOIN crawled_hotels h USING (supplier_id)) t
           WHERE prev_id IS NOT NULL ORDER BY created_at DESC LIMIT %s""",
        (limit,),
    )


def runs(limit=20):
    rows = query("SELECT * FROM crawl_runs ORDER BY id DESC LIMIT %s", (limit,))
    for row in rows:
        for key in ("started_at", "finished_at"):
            row[key] = row[key].isoformat() if isinstance(row[key], datetime) else row[key]
    return rows
