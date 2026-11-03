"""用真的 Claude 在瀏覽器問規定，保存 RAG 截圖（會花一點 API 額度）。"""
import os
from playwright.sync_api import sync_playwright

URL = "http://travelquote-app-1:8000/"
OUT = os.environ.get("OUT", "/shots")


def ask(page, text):
    done = page.locator(".bubble.ai:not(.waiting), .bubble.error").count()
    page.fill("#chat-input", text)
    page.click("#chat-form button")
    page.wait_for_function(
        f"document.querySelectorAll('.bubble.ai:not(.waiting), .bubble.error').length > {done}",
        timeout=120000,
    )
    assert page.locator(".bubble.error").count() == 0


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(URL)
    page.wait_for_selector("#chat:not([hidden])")

    ask(page, "出發前 7 天取消，團費 107,200 元可以退多少？")
    assert "53,600" in page.locator(".bubble.ai").last.inner_text()
    page.screenshot(path=f"{OUT}/10_AI依規定計算退費.png", full_page=True)

    page.click("#chat-new")
    ask(page, "可以在飛機上抽菸嗎？")
    page.screenshot(path=f"{OUT}/11_文件沒寫就說沒提到.png", full_page=True)

    page.click("#chat-new")
    ask(page, "4 個人去沖繩每人預算 3 萬，順便問要不要辦簽證？")
    page.screenshot(path=f"{OUT}/12_報價加規定一起問.png", full_page=True)

    page.click("#tab-policy")
    page.wait_for_selector("#policy-list details")
    page.locator("#policy-list summary").first.click()
    page.screenshot(path=f"{OUT}/13_規定文件全文.png", full_page=True)
    print("RAG 截圖完成")
    browser.close()
