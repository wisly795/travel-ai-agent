"""用真的 Claude（較強模型）在瀏覽器做採購比價與核准，保存截圖（會花一點 API 額度）。"""
import json
import os
import urllib.request
from playwright.sync_api import sync_playwright

BASE = "http://travelquote-app-1:8000"
OUT = os.environ.get("OUT", "/shots")
STAFF = os.environ["STAFF_TOKEN"]
MANAGER = os.environ["MANAGER_TOKEN"]


def call(method, path, body=None):
    request = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None, method=method,
                                     headers={"Content-Type": "application/json", "X-Staff-Token": STAFF})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def deal(package_id, hotel_id, people, name):
    quote = call("POST", "/api/quotes", {"customer_name": name, "package_id": package_id, "hotel_id": hotel_id, "people": people})
    call("PATCH", f"/api/quotes/{quote['id']}/status", {"status": "成交"})
    return quote


packages = {p["name"]: p["id"] for p in call("GET", "/api/packages?people=1")}
hotels = {h["name"]: h["id"] for h in call("GET", "/api/hotels")}
deal(packages["賞楓慢旅 6 日"], hotels["庭園溫泉館"], 8, "大額採購示範")
deal(packages["海島放鬆 4 日"], hotels["海風飯店"], 4, "採購示範")


def card(page, text):
    return page.locator(".pr-card", has_text=text).first


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1280, "height": 1000})
    page.on("dialog", lambda dialog: dialog.accept("想改成可以免費取消的方案"))
    page.goto(BASE + "/")
    page.goto(URL + "admin")
    page.fill("#staff-token", STAFF)
    page.click("#staff-form button")
    page.wait_for_selector("#staff-result:not([hidden])")
    page.click("[data-view=view-procurement]")
    page.screenshot(path=f"{OUT}/01_成交後自動產生請購單.png", full_page=True)

    # 小額：AI 比價 → 業務核准
    card(page, "採購示範").get_by_role("button", name="AI 比價").click()
    page.wait_for_function("[...document.querySelectorAll('.pr-card')].some(c => c.innerText.includes('採購示範') && c.innerText.includes('待核准'))",
                           timeout=240000)
    page.screenshot(path=f"{OUT}/02_AI比價建議與草稿.png", full_page=True)

    # 退回一次，再重新比價
    card(page, "採購示範").get_by_role("button", name="退回").click()
    page.wait_for_function("[...document.querySelectorAll('.pr-card')].some(c => c.innerText.includes('採購示範') && c.innerText.includes('已退回'))")
    page.screenshot(path=f"{OUT}/03_退回並寫原因.png", full_page=True)
    card(page, "採購示範").get_by_role("button", name="AI 比價").click()
    page.wait_for_function("[...document.querySelectorAll('.pr-card')].some(c => c.innerText.includes('採購示範') && c.innerText.includes('待核准'))",
                           timeout=240000)
    card(page, "採購示範").get_by_role("button", name="核准並下單").click()
    page.wait_for_function("[...document.querySelectorAll('.pr-card')].some(c => c.innerText.includes('採購示範') && c.innerText.includes('SUP-'))")
    page.screenshot(path=f"{OUT}/04_業務核准後下單.png", full_page=True)

    # 大額：AI 比價 → 業務不能核准 → 主管核准
    card(page, "大額採購示範").get_by_role("button", name="AI 比價").click()
    page.wait_for_function("[...document.querySelectorAll('.pr-card')].some(c => c.innerText.includes('大額採購示範') && c.innerText.includes('待核准'))",
                           timeout=240000)
    card(page, "大額採購示範").get_by_role("button", name="核准並下單").click()
    page.wait_for_selector("#message:not([hidden])")
    page.screenshot(path=f"{OUT}/05_大額需要主管核准.png", full_page=True)
    page.fill("#manager-token", MANAGER)
    card(page, "大額採購示範").get_by_role("button", name="核准並下單").click()
    page.wait_for_function("[...document.querySelectorAll('.pr-card')].some(c => c.innerText.includes('大額採購示範') && c.innerText.includes('SUP-'))")
    page.screenshot(path=f"{OUT}/06_主管核准後下單.png", full_page=True)

    page.click("[data-view=view-turns]")
    page.locator(".turn summary", has_text="採購").first.click()
    page.screenshot(path=f"{OUT}/07_採購AI的工具紀錄.png", full_page=True)
    print("採購截圖完成")
    browser.close()
