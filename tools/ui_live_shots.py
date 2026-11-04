"""用真的 Claude 在瀏覽器裡對話，保存作品集截圖（會花一點 API 額度）。"""
import os
from playwright.sync_api import sync_playwright

URL = "http://travelquote-app-1:8000/"
OUT = os.environ.get("OUT", "/shots")
TOKEN = os.environ["STAFF_TOKEN"]


def ask(page, text):
    count = page.locator(".bubble.ai").count()
    page.fill("#chat-input", text)
    page.click("#chat-form button")
    page.wait_for_function(
        f"document.querySelectorAll('.bubble.ai:not(.waiting), .bubble.error').length > {count}",
        timeout=120000,
    )
    assert page.locator(".bubble.error").count() == 0, page.inner_text(".bubble.error")


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(URL)
    page.wait_for_selector("#chat:not([hidden])")

    ask(page, "2 個人想去京都，每人預算 4 萬，有推薦的嗎？")
    page.screenshot(path=f"{OUT}/07_真實AI推薦行程.png", full_page=True)
    ask(page, "選最便宜的組合，我叫測試小華，請建立報價單")
    page.screenshot(path=f"{OUT}/08_真實AI建立報價.png", full_page=True)

    page.goto(URL + "admin")
    page.fill("#staff-token", TOKEN)
    page.click("#staff-form button")
    page.wait_for_selector("#staff-result:not([hidden])")
    page.screenshot(path=f"{OUT}/09_後台看到AI報價.png", full_page=True)
    print("截圖完成")
    browser.close()
