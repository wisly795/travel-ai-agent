"""J1、J2 截圖：模擬供應商網站（列表、詳細頁、robots.txt、429）、開放資料 API 回應。不花 API 額度。"""
import json
import os

from playwright.sync_api import sync_playwright

OUT = os.environ.get("OUT", "/shots")
J1, J2 = f"{OUT}/J1_開放資料", f"{OUT}/J2_爬蟲"
for folder in (J1, J2):
    os.makedirs(folder, exist_ok=True)
SUPPLIER = "http://travelquote-supplier-1:8000"
APP = "http://travelquote-app-1:8000"

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1100, "height": 800}, locale="zh-TW")

    page.goto(f"{SUPPLIER}/hotels")
    page.screenshot(path=f"{J2}/01_模擬供應商網站列表第1頁.png", full_page=True)
    page.wait_for_timeout(1200)
    page.goto(f"{SUPPLIER}/hotels/S001")
    page.screenshot(path=f"{J2}/02_詳細頁房型與價格.png")
    page.wait_for_timeout(1200)
    page.goto(f"{SUPPLIER}/robots.txt")
    page.screenshot(path=f"{J2}/03_robots規則.png", clip={"x": 0, "y": 0, "width": 600, "height": 160})
    # 太快連續請求 → 429
    for _ in range(4):
        response = page.goto(f"{SUPPLIER}/hotels?page=2")
    assert response.status == 429, response.status
    page.screenshot(path=f"{J2}/04_太快被限流429.png", clip={"x": 0, "y": 0, "width": 600, "height": 120})
    page.wait_for_timeout(2500)

    # 爬蟲結果與開放資料：用格式化的 JSON 呈現 API 回應
    def show_json(url, path, title):
        data = page.request.get(url).json()
        page.set_content("<meta charset=utf-8><style>body{font:14px/1.5 monospace;padding:16px;white-space:pre-wrap}"
                         "h3{font-family:sans-serif}</style><h3>" + title + "</h3>"
                         + json.dumps(data, ensure_ascii=False, indent=2)[:3500].replace("<", "&lt;"))
        page.screenshot(path=path, full_page=True)

    show_json(f"{APP}/api/supplier-prices?city=%E8%8A%B1%E8%93%AE", f"{J2}/05_爬到的花蓮價格API.png",
              "GET /api/supplier-prices?city=花蓮（爬蟲抓到的最新價格）")
    show_json(f"{APP}/api/explore/cities", f"{J1}/01_各縣市景點與住宿數量API.png", "GET /api/explore/cities")
    show_json(f"{APP}/api/explore/attractions?city=%E8%8A%B1%E8%93%AE%E7%B8%A3&limit=2", f"{J1}/02_花蓮景點API.png",
              "GET /api/explore/attractions?city=花蓮縣&limit=2")
    show_json(f"{APP}/api/explore/hotels?city=%E8%87%BA%E6%9D%B1%E7%B8%A3&max_price=2500&limit=2", f"{J1}/03_臺東平價住宿API.png",
              "GET /api/explore/hotels?city=臺東縣&max_price=2500&limit=2")
    print("J1、J2 截圖完成")
    browser.close()
