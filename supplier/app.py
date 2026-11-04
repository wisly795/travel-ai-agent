"""模擬供應商網站「雲遊旅宿比價網」：給爬蟲抓的對象（全部虛構，不是任何真實網站）。

故意做出真實網站常見的情況，讓爬蟲要處理：
- 列表分頁（每頁 8 家，「下一頁」連結）、詳細頁（房型與價格表格）
- robots.txt：不准抓 /admin、/checkout，要求每次間隔 1 秒
- 限流：同一個來源 1 秒內超過 3 次回 429 並附 Retry-After
- 價格每天變動（依日期決定，同一天內固定）；可用 /admin/advance-day 模擬「隔天」讓價格變動
- 售完的房型沒有價格、偶爾有「限時特價」標記
"""
import hashlib
import html
import random
import time
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

app = FastAPI(title="模擬供應商網站", docs_url=None, redoc_url=None, openapi_url=None)
TAIPEI = timezone(timedelta(hours=8))
PAGE_SIZE = 8
STATE = {"day_offset": 0, "limit": 3}
_hits = defaultdict(deque)

CITIES = {"沖繩": ["海風", "珊瑚", "椰林", "藍灣", "日落", "潮聲"], "京都": ["町屋", "庭園", "竹林", "古都", "楓葉", "鴨川"],
          "首爾": ["明洞", "漢江", "南山", "景福", "弘大", "江南"], "花蓮": ["太魯閣", "七星潭", "海岸", "清水", "鯉魚潭", "山月"],
          "臺東": ["池上", "稻浪", "都蘭", "鹿野", "三仙台", "金針山"]}
KINDS = [("飯店", 4), ("旅館", 3), ("民宿", 2), ("度假村", 5)]
ROOMS = [("標準雙人房", 1.0), ("豪華雙人房", 1.35), ("家庭四人房", 1.8)]
BASE = {"沖繩": 3600, "京都": 4800, "首爾": 3200, "花蓮": 2600, "臺東": 2400}


def build_hotels():
    hotels, n = [], 0
    for city, words in CITIES.items():
        for i, word in enumerate(words):
            kind, stars = KINDS[i % len(KINDS)]
            n += 1
            hotels.append({"id": f"S{n:03d}", "name": f"{word}{kind}", "city": city, "stars": stars,
                           "base": BASE[city] + stars * 450 + (i * 137) % 600})
    return hotels


HOTELS = build_hotels()
BY_ID = {h["id"]: h for h in HOTELS}


def today():
    return datetime.now(TAIPEI).date() + timedelta(days=STATE["day_offset"])


def prices(hotel, day):
    """依「飯店＋日期」決定價格：同一天固定、隔天變動，偶爾大漲大跌（測試爬蟲的價格變動通知）。"""
    seed = int(hashlib.sha256(f"{hotel['id']}{day.isoformat()}".encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    swing = rng.choice([0.85, 0.95, 1.0, 1.0, 1.05, 1.1, 1.25])
    rows = []
    for room, ratio in ROOMS:
        sold_out = rng.random() < 0.12
        price = None if sold_out else int(round(hotel["base"] * ratio * swing / 10) * 10)
        rows.append({"room": room, "price": price, "promo": not sold_out and rng.random() < 0.15})
    return rows


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    """同一個來源 1 秒內超過上限就回 429；/admin 不限。"""
    if not request.url.path.startswith("/admin"):
        who, now = request.client.host if request.client else "?", time.monotonic()
        window = _hits[who]
        while window and now - window[0] > 1:
            window.popleft()
        if len(window) >= STATE["limit"]:
            return PlainTextResponse("Too Many Requests：請放慢速度", status_code=429, headers={"Retry-After": "2"})
        window.append(now)
    return await call_next(request)


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return "User-agent: *\nDisallow: /admin\nDisallow: /checkout\nCrawl-delay: 1\n"


def page(title, body):
    return HTMLResponse(f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>{html.escape(title)}｜雲遊旅宿比價網</title>
<style>body{{font-family:sans-serif;max-width:900px;margin:auto;padding:16px;color:#223}} .card{{border:1px solid #ccd;border-radius:8px;padding:12px;margin:8px 0}}
table{{border-collapse:collapse}} td,th{{border:1px solid #ccd;padding:4px 8px}} .promo{{color:#c0392b}} .demo{{color:#c0392b}}</style></head>
<body><header><a href="/">雲遊旅宿比價網</a> <span class="demo">（模擬網站，資料皆為虛構）</span></header>{body}</body></html>""")


@app.get("/", response_class=HTMLResponse)
def home():
    links = "".join(f'<li><a href="/hotels?city={c}">{c}</a></li>' for c in CITIES)
    return page("首頁", f'<h1>找住宿</h1><ul class="cities">{links}</ul><p><a href="/hotels">全部住宿</a></p>')


@app.get("/hotels", response_class=HTMLResponse)
def listing(city: str | None = None, page_no: int = Query(default=1, alias="page", ge=1)):
    rows = [h for h in HOTELS if not city or h["city"] == city]
    start = (page_no - 1) * PAGE_SIZE
    day = today()
    cards = []
    for h in rows[start:start + PAGE_SIZE]:
        available = [p["price"] for p in prices(h, day) if p["price"]]
        lowest = f"NT$ {min(available):,} 起" if available else "全部售完"
        cards.append(f'<article class="card hotel" data-id="{h["id"]}"><h2 class="name"><a href="/hotels/{h["id"]}">{h["name"]}</a></h2>'
                     f'<span class="city">{h["city"]}</span>｜<span class="stars">{"★" * h["stars"]}</span>'
                     f'｜<span class="from-price">{lowest}</span></article>')
    nav = []
    query = f"city={city}&" if city else ""
    if page_no > 1:
        nav.append(f'<a rel="prev" href="/hotels?{query}page={page_no - 1}">上一頁</a>')
    if start + PAGE_SIZE < len(rows):
        nav.append(f'<a rel="next" class="next" href="/hotels?{query}page={page_no + 1}">下一頁</a>')
    title = f"{city or '全部'}住宿"
    return page(title, f'<h1>{title}（共 {len(rows)} 家）</h1><p class="updated">價格更新：{day.isoformat()}</p>'
                       f'{"".join(cards)}<nav class="pager">{" ".join(nav)}</nav>')


def room_row(p):
    price_text = f"NT$ {p['price']:,}" if p["price"] else "售完"
    promo = '<span class="promo">限時特價</span>' if p["promo"] else ""
    return (f'<tr class="room"><td class="room-name">{p["room"]}</td>'
            f'<td class="price" data-price="{p["price"] or ""}">{price_text}</td><td>{promo}</td></tr>')


@app.get("/hotels/{hotel_id}", response_class=HTMLResponse)
def detail(hotel_id: str):
    hotel = BY_ID.get(hotel_id)
    if not hotel:
        return page("找不到", "<h1>找不到這家住宿</h1>")
    day = today()
    rows = "".join(room_row(p) for p in prices(hotel, day))
    return page(hotel["name"], f'<article class="hotel-detail" data-id="{hotel["id"]}"><h1 class="name">{hotel["name"]}</h1>'
                               f'<p><span class="city">{hotel["city"]}</span>｜<span class="stars" data-stars="{hotel["stars"]}">{"★" * hotel["stars"]}</span></p>'
                               f'<p class="updated" data-date="{day.isoformat()}">價格日期：{day.isoformat()}（每晚、含稅）</p>'
                               f'<table class="rooms"><tr><th>房型</th><th>每晚價格</th><th></th></tr>{rows}</table>'
                               f'<p><a href="/checkout/{hotel["id"]}">立即訂房</a></p></article>')


@app.get("/checkout/{hotel_id}", response_class=HTMLResponse)
def checkout(hotel_id: str):
    return page("訂房", "<h1>訂房頁（robots.txt 禁止爬蟲進入）</h1>")


# ---------- 模擬用的管理功能（robots.txt 禁止爬蟲；只開在本機與內部網路） ----------

@app.post("/admin/advance-day")
def advance_day(days: int = 1):
    """模擬時間往後一天：價格會變。"""
    STATE["day_offset"] += days
    return {"day": today().isoformat()}


@app.post("/admin/reset")
def reset():
    STATE.update({"day_offset": 0, "limit": 3})
    _hits.clear()
    return {"day": today().isoformat()}


@app.post("/admin/rate-limit")
def set_limit(per_second: int = 3):
    STATE["limit"] = max(1, per_second)
    _hits.clear()
    return {"limit": STATE["limit"]}


@app.get("/admin/truth")
def truth():
    """測試用：網站當天真正的價格，用來核對爬蟲抓得對不對。"""
    day = today()
    return JSONResponse({"day": day.isoformat(), "hotels": [{**h, "prices": prices(h, day)} for h in HOTELS]})
