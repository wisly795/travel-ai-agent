"""通知中心截圖：n8n 產生的新報價、每日報表、採購提醒、同步失敗通知。"""
import os
from playwright.sync_api import sync_playwright

URL = "http://travelquote-app-1:8000/"
OUT = os.environ.get("OUT", "/shots")
TOKEN = os.environ["STAFF_TOKEN"]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1280, "height": 1000})
    page.goto(URL)
    page.goto(URL + "admin")
    page.fill("#staff-token", TOKEN)
    page.click("#staff-form button")
    page.wait_for_selector("#staff-result:not([hidden])")
    page.click("[data-view=view-notifications]")
    page.wait_for_selector(".notice")
    assert page.locator(".notice.unread").count() > 0
    page.screenshot(path=f"{OUT}/01_通知中心.png", full_page=True)
    page.click("#read-all")
    page.wait_for_function("document.querySelectorAll('.notice.unread').length === 0")
    page.screenshot(path=f"{OUT}/02_全部已讀.png")
    print("通知截圖完成")
    browser.close()
