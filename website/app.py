"""模擬官網：代表旅行社的官方網站（另一套系統），由「後端」帶 API 金鑰呼叫報價系統的合作夥伴 API。

金鑰只在這個伺服器上，瀏覽器看不到；客人在官網填表，官網後端轉送給報價系統。
"""
import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

API = os.environ.get("PARTNER_API", "http://app:8000/partner")
KEY = os.environ.get("PARTNER_KEY", "")

app = FastAPI(title="模擬官網", docs_url=None, redoc_url=None, openapi_url=None)


def call(method, path, body=None):
    request = urllib.request.Request(API + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "X-API-Key": KEY})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read()), None
    except urllib.error.HTTPError as error:
        detail = json.loads(error.read() or b"{}").get("detail", error.reason)
        return None, f"報價系統回應 {error.code}：{detail if isinstance(detail, str) else '資料有誤'}"
    except urllib.error.URLError:
        return None, "暫時連不上報價系統，請稍後再試"


def esc(value):
    return html.escape(str(value))


def money(value):
    return f"NT$ {int(value):,}"


def page(body):
    return HTMLResponse(f"""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>晴空旅遊（模擬官網）</title>
<style>
body{{margin:0;font-family:"Microsoft JhengHei",sans-serif;color:#2b2b2b;background:#fffaf3}}
header{{background:#c2410c;color:#fff;padding:18px 16px}} header h1{{margin:0;font-size:24px}} header p{{margin:4px 0 0;opacity:.9}}
main{{max-width:900px;margin:0 auto;padding:16px}}
.card{{background:#fff;border:1px solid #f1d9c4;border-radius:10px;padding:14px;margin-bottom:12px}}
label{{display:block;font-weight:700;margin:6px 0}} input,select{{width:100%;padding:8px;font:inherit;box-sizing:border-box}}
button{{background:#c2410c;color:#fff;border:0;border-radius:8px;padding:10px 16px;font:inherit;font-weight:700;cursor:pointer;margin-top:8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}}
.err{{color:#b42318;font-weight:700}} .note{{color:#7a6a5a;font-size:13px}}
</style></head><body><header><h1>晴空旅遊</h1><p>模擬官網｜示範「官網後端呼叫報價系統 API」｜所有資料皆為模擬</p></header>
<main>{body}</main></body></html>""")


@app.get("/")
def home(destination: str = "", people: int = 2):
    destinations, error = call("GET", "/v1/destinations")
    if error:
        return page(f'<p class="err">{esc(error)}</p>')
    options = "".join(f'<option {"selected" if d == destination else ""}>{esc(d)}</option>' for d in destinations)
    body = f"""<form class="card" method="get"><div class="grid">
      <label>目的地<select name="destination"><option value="">全部</option>{options}</select></label>
      <label>人數<input name="people" type="number" min="1" max="20" value="{int(people)}"></label></div>
      <button>查詢行程</button></form>"""
    params = {"people": max(1, min(int(people), 20))}
    if destination:
        params["destination"] = destination
    packages, error = call("GET", "/v1/packages?" + urllib.parse.urlencode(params))
    if error:
        return page(body + f'<p class="err">{esc(error)}</p>')
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    for item in packages:
        hotels, _ = call("GET", "/v1/hotels?" + urllib.parse.urlencode({"destination": item["destination"]}))
        hotel_options = "".join(
            f'<option value="{h["id"]}">{esc(h["name"])}（每晚 {money(h["price_per_night"])}）</option>' for h in hotels or [])
        body += f"""<form class="card" method="post" action="/quote">
          <h3>{esc(item["name"])}</h3><p>{esc(item["destination"])}｜{item["days"]} 天｜{money(item["price_per_person"])} / 人｜{esc(item["description"])}</p>
          <input type="hidden" name="package_id" value="{item["id"]}"><input type="hidden" name="people" value="{params["people"]}">
          <div class="grid"><label>飯店<select name="hotel_id">{hotel_options}</select></label>
          <label>出發日期<input type="date" name="departure_date" min="{tomorrow}" required></label>
          <label>姓名<input name="customer_name" maxlength="50" required></label></div>
          <button>線上報價</button></form>"""
    if not packages:
        body += '<p class="card">沒有符合條件的行程。</p>'
    return page(body + '<p class="note">本頁由官網伺服器呼叫報價系統的合作夥伴 API 產生；API 金鑰只存在官網伺服器上。</p>')


@app.post("/quote")
def quote(customer_name: str = Form(...), package_id: int = Form(...), hotel_id: int = Form(...),
          people: int = Form(...), departure_date: str = Form(...)):
    result, error = call("POST", "/v1/quotes", {"customer_name": customer_name, "package_id": package_id,
                                                "hotel_id": hotel_id, "people": people, "departure_date": departure_date})
    if error:
        return page(f'<p class="card err">{esc(error)}</p><p><a href="/">回首頁</a></p>')
    return page(f"""<div class="card"><h2>報價完成：報價單 #{result["id"]}</h2>
      <p>{esc(result["customer_name"])}｜{esc(result["package"])}＋{esc(result["hotel"])}</p>
      <p>{result["people"]} 人，{result["rooms"]} 間房，{result["nights"]} 晚｜出發 {esc(result["departure_date"])}，回程 {esc(result["return_date"])}</p>
      <h3>總價 {money(result["total_price"])}</h3><p class="note">價格由報價系統計算；業務人員會盡快與您聯繫。</p></div>
      <p><a href="/">繼續逛逛</a></p>""")
