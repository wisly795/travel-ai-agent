"""J3 截圖：前台右下角 AI 聊天泡泡，用真實 AI 問台灣景點（會用到開放資料工具，約 0.002 美元）。"""
import os

from playwright.sync_api import sync_playwright

URL = "http://travelquote-app-1:8000/"
OUT = os.environ.get("OUT", "/shots")
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_context(viewport={"width": 1366, "height": 900}, locale="zh-TW").new_page()
    page.goto(URL + "tours/8")
    page.wait_for_selector("#book-total")
    page.click(".s-chat-fab")
    page.wait_for_selector(".s-chat.open #chat-status:not(:empty)")
    page.fill("#chat-input", "台東有什麼溫泉景點？推薦兩個")
    page.click("#chat-form button")
    page.wait_for_selector(".bubble.ai small", timeout=120000)
    page.wait_for_timeout(500)
    text = page.locator(".bubble.ai").last.inner_text()
    print(text)
    assert "查景點" in text or "交通部觀光署" in text, "沒有用到開放資料工具"
    page.screenshot(path=f"{OUT}/18_AI客服查台東溫泉景點.png")
    browser.close()
