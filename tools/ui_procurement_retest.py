"""修正後重測：退回原因交給 AI、大額核准的提示訊息（會花一點 API 額度）。"""
import json
import os
import urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://travelquote-app-1:8000"
OUT = os.environ.get("OUT", "/shots")
STAFF = os.environ["STAFF_TOKEN"]


def call(method, path, body=None):
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None, method=method,
                                     headers={"Content-Type": "application/json", "X-Staff-Token": STAFF})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read())


packages = {p["name"]: p["id"] for p in call("GET", "/api/packages?people=1")}
hotels = {h["name"]: h["id"] for h in call("GET", "/api/hotels")}
quote = call("POST", "/api/quotes", {"customer_name": "退回重測", "package_id": packages["海島放鬆 4 日"],
                                     "hotel_id": hotels["海風飯店"], "people": 4})
pr = call("PATCH", f"/api/quotes/{quote['id']}/status", {"status": "成交"})["purchase_request"]
first = call("POST", f"/api/procurement/{pr['id']}/analyze")
print("第一次建議：", first["draft"]["supplier"])
call("POST", f"/api/purchase-orders/{first['draft']['id']}/decision",
     {"approve": False, "reason": "客人可能改期，要能在出發前 14 天以前免費取消"})
second = call("POST", f"/api/procurement/{pr['id']}/analyze")
print("退回後建議：", second["draft"]["supplier"])
print("AI 說明：", second["analysis"])

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1280, "height": 1000})
    page.goto(BASE + "/")
    page.goto(URL + "admin")
    page.fill("#staff-token", STAFF)
    page.click("#staff-form button")
    page.wait_for_selector("#staff-result:not([hidden])")
    page.click("[data-view=view-procurement]")
    page.locator(".pr-card", has_text="退回重測").first.scroll_into_view_if_needed()
    page.screenshot(path=f"{OUT}/08_退回原因交給AI後重新建議.png", full_page=True)

    big = page.locator(".pr-card", has_text="需要主管核准").filter(has=page.get_by_role("button", name="核准並下單")).first
    big.get_by_role("button", name="核准並下單").click()
    page.wait_for_selector("#message:not([hidden])")
    assert "請先輸入主管權杖" in page.inner_text("#message")
    page.screenshot(path=f"{OUT}/05_大額需要主管核准.png", full_page=True)
    print("重測截圖完成")
    browser.close()
