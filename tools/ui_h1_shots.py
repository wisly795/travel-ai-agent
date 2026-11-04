"""H1 出發日期：真實 AI 換算相對日期、用出發日算退費、採購判斷免費取消期限，並截圖（會花一點 API 額度）。"""
import json
import os
import urllib.request
from datetime import date, timedelta
from playwright.sync_api import sync_playwright

BASE = os.environ.get("APP_URL", "http://travelquote-app-1:8000").rstrip("/")
OUT = os.environ.get("OUT", "/shots")
STAFF = os.environ["STAFF_TOKEN"]


def call(method, path, body=None):
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None, method=method,
                                     headers={"Content-Type": "application/json", "X-Staff-Token": STAFF})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read())


def ask(page, text):
    done = page.locator(".bubble.ai:not(.waiting), .bubble.error").count()
    page.fill("#chat-input", text)
    page.click("#chat-form button")
    page.wait_for_function(
        f"document.querySelectorAll('.bubble.ai:not(.waiting), .bubble.error').length > {done}", timeout=180000)
    return page.locator(".bubble.ai, .bubble.error").last.inner_text()


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(BASE + "/")
    page.wait_for_selector("#chat:not([hidden])")

    # 1. 相對日期換算
    print("AI：", ask(page, "2 個人下個月 15 號出發去首爾 4 天，住最便宜的飯店，總共多少？"))
    print("AI：", ask(page, "好，我叫日期測試，請建立報價單"))
    page.screenshot(path=f"{OUT}/01_AI換算相對日期.png", full_page=True)

    # 2. 用出發日期算退費
    page.click("#chat-new")
    in9 = (date.today() + timedelta(days=9)).strftime("%m 月 %d 日").lstrip("0")
    print("AI：", ask(page, f"我的團費是 82,400 元，{in9}出發，現在取消會扣多少？"))
    page.screenshot(path=f"{OUT}/02_用出發日期算退費.png", full_page=True)

    # 3. 網頁報價表單的出發日期
    page.click("#tab-customer")
    page.select_option("#destination", "京都")
    page.fill("#people", "2")
    page.click("#search-form button")
    page.wait_for_selector(".card")
    page.locator(".card").first.get_by_role("button", name="選擇").click()
    page.wait_for_selector("#quote-form:not([hidden])")
    page.fill("#departure-date", (date.today() + timedelta(days=45)).isoformat())
    page.fill("#customer-name", "網頁日期測試")
    page.click("#quote-form button")
    page.wait_for_selector("#result:not([hidden])")
    page.screenshot(path=f"{OUT}/03_網頁報價含出發與回程.png", full_page=True)

    # 4. 採購：10 天後出發，直訂的 14 天免費取消期限已過
    packages = {x["name"]: x["id"] for x in call("GET", "/api/packages?people=1")}
    hotels = {x["name"]: x["id"] for x in call("GET", "/api/hotels")}
    quote = call("POST", "/api/quotes", {"customer_name": "期限示範", "package_id": packages["海島放鬆 4 日"],
                                         "hotel_id": hotels["海風飯店"], "people": 4,
                                         "departure_date": (date.today() + timedelta(days=10)).isoformat()})
    pr = call("PATCH", f"/api/quotes/{quote['id']}/status", {"status": "成交"})["purchase_request"]
    result = call("POST", f"/api/procurement/{pr['id']}/analyze")
    print("採購 AI：", result["analysis"])
    page.goto(URL + "admin")
    page.fill("#staff-token", STAFF)
    page.click("#staff-form button")
    page.wait_for_selector("#staff-result:not([hidden])")
    page.screenshot(path=f"{OUT}/04_後台報價列表出發日.png", full_page=True)
    page.click("[data-view=view-procurement]")
    page.locator(".pr-card", has_text="期限示範").first.scroll_into_view_if_needed()
    page.locator(".pr-card", has_text="期限示範").first.screenshot(path=f"{OUT}/05_採購判斷免費取消期限.png")
    print("H1 截圖完成")
    browser.close()
