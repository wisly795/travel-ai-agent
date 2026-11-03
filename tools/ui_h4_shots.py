"""H4 官網串接：模擬官網報價 → 後台看到來源「官網串接」→ 管理員建立合作夥伴金鑰 → API 文件頁，並截圖。"""
import os
from datetime import date, timedelta
from playwright.sync_api import sync_playwright

APP = "http://travelquote-app-1:8000"
SITE = "http://travelquote-website-1:8000"
OUT = os.environ.get("OUT", "/shots")
ADMIN = os.environ["ADMIN_PASSWORD"]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    site = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    site.goto(f"{SITE}/?destination=京都&people=2")
    site.wait_for_selector("form.card h3")
    assert "X-API-Key" not in site.content() and "pk_" not in site.content(), "金鑰不能出現在官網頁面"
    site.screenshot(path=f"{OUT}/01_模擬官網查行程.png")
    form = site.locator("form.card", has_text="古都散步").first
    form.locator("input[name=departure_date]").fill((date.today() + timedelta(days=30)).isoformat())
    form.locator("input[name=customer_name]").fill("官網示範客人")
    form.get_by_role("button", name="線上報價").click()
    site.wait_for_selector("text=報價完成")
    site.screenshot(path=f"{OUT}/02_官網報價完成.png")

    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto(APP + "/")
    page.click("#tab-staff")
    page.fill("#login-username", "admin")
    page.fill("#login-password", ADMIN)
    page.click("#staff-form button")
    page.wait_for_selector("#staff-result:not([hidden])")
    page.click("[data-view=view-quotes]")
    assert "官網串接" in page.inner_text("#quote-rows")
    page.screenshot(path=f"{OUT}/03_後台看到官網串接來源.png")

    page.click("[data-view=view-users]")
    page.fill("#partner-name", "示範旅遊平台")
    page.fill("#partner-limit", "20")
    page.click("#partner-form button")
    page.wait_for_selector("#partner-key:not([hidden])")
    page.locator("#partner-calls").evaluate("el => el.closest('details').open = true")
    page.locator("#partner-rows").scroll_into_view_if_needed()
    page.screenshot(path=f"{OUT}/04_建立合作夥伴金鑰只顯示一次.png", full_page=True)

    page.click("[data-view=view-dashboard]")
    page.wait_for_selector("#chart-sources .legend-item")
    page.locator("#chart-sources").screenshot(path=f"{OUT}/05_儀表板報價來源三類.png")

    docs = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    docs.goto(APP + "/partner/docs")
    docs.wait_for_selector(".opblock", timeout=60000)
    docs.screenshot(path=f"{OUT}/06_合作夥伴API文件.png", full_page=True)
    print("H4 截圖完成")
    browser.close()
