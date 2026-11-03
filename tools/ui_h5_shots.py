"""H5 Email 通知：模擬信箱 Mailpit 的收件匣與信件內容截圖。"""
import os
from playwright.sync_api import sync_playwright

MAIL = "http://travelquote-mailpit-1:8025"
OUT = os.environ.get("OUT", "/shots")

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_context(viewport={"width": 1280, "height": 800}).new_page()
    page.goto(MAIL)
    page.wait_for_selector("text=旅遊報價系統", timeout=30000)
    page.screenshot(path=f"{OUT}/01_模擬信箱收件匣.png")
    page.get_by_text("新報價 #", exact=False).first.click()
    page.wait_for_timeout(1500)
    page.screenshot(path=f"{OUT}/02_新報價通知信.png")
    page.goto(MAIL)
    page.get_by_text("每日報表", exact=False).first.click()
    page.wait_for_timeout(1500)
    page.screenshot(path=f"{OUT}/03_每日報表信.png")
    print("H5 截圖完成")
    browser.close()
