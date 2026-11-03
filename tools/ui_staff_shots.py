"""業務後台與 ERP 串接的瀏覽器實測與截圖（AI 部分會花一點 API 額度）。"""
import os
from playwright.sync_api import sync_playwright

URL = "http://travelquote-app-1:8000/"
ERP = "http://travelquote-erp-1:8000/"
OUT = os.environ.get("OUT", "/shots")
TOKEN = os.environ["STAFF_TOKEN"]


def ask(page, text):
    done = page.locator(".bubble.ai:not(.waiting), .bubble.error").count()
    page.fill("#chat-input", text)
    page.click("#chat-form button")
    page.wait_for_function(
        f"document.querySelectorAll('.bubble.ai:not(.waiting), .bubble.error').length > {done}",
        timeout=120000,
    )


def reload_staff(page):
    page.click("#staff-form button")
    page.wait_for_timeout(800)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(URL)
    page.wait_for_selector("#chat:not([hidden])")

    # 先用 AI 客服產生一張報價和一張轉接單
    ask(page, "2 個人去首爾 4 天，住最便宜的飯店，我叫後台測試，確認後直接幫我建立報價單")
    if "編號" not in page.locator(".bubble.ai").last.inner_text():
        ask(page, "確認，請建立")
    page.click("#chat-new")
    ask(page, "我想把行程改到下個月，可以嗎？")

    page.click("#tab-staff")
    page.fill("#staff-token", TOKEN)
    page.click("#staff-form button")
    page.wait_for_selector("#staff-result:not([hidden])")
    page.screenshot(path=f"{OUT}/01_後台報價列表.png", full_page=True)

    # 成交 → 自動送 ERP
    first = page.locator("#quote-rows tr").first
    first.get_by_role("button", name="成交").click()
    page.wait_for_function("document.querySelector('#quote-rows tr').innerText.includes('ERP-')")
    page.screenshot(path=f"{OUT}/02_成交後同步ERP成功.png", full_page=True)

    # AI 對話紀錄
    page.click("[data-view=view-turns]")
    page.locator(".turn summary").first.click()
    page.locator(".turn summary").nth(1).click()
    page.screenshot(path=f"{OUT}/03_AI對話紀錄與工具明細.png", full_page=True)

    # 轉接單
    page.click("[data-view=view-handoffs]")
    page.screenshot(path=f"{OUT}/04_轉接單.png", full_page=True)
    page.locator("#handoff-rows tr").first.get_by_role("button").click()
    page.wait_for_timeout(800)

    # 模擬 ERP 故障 → 成交失敗 → 恢復 → 重送
    page.click("[data-view=view-erp]")
    page.click("#erp-fail-on")
    page.wait_for_function("document.getElementById('erp-health').innerText.includes('維修中')")
    page.click("[data-view=view-quotes]")
    page.locator("#quote-rows tr", has_text="已報價").first.get_by_role("button", name="成交").click()
    page.wait_for_function("[...document.querySelectorAll('#quote-rows tr')].some(r => r.innerText.includes('失敗'))")
    page.click("[data-view=view-erp]")
    page.screenshot(path=f"{OUT}/05_ERP故障同步失敗.png", full_page=True)
    page.click("#erp-fail-off")
    page.wait_for_function("document.getElementById('erp-health').innerText.includes('正常')")
    page.click("#erp-retry-all")
    page.wait_for_function("![...document.querySelectorAll('#erp-rows tr')].some(r => r.innerText.includes('失敗'))")
    page.screenshot(path=f"{OUT}/06_恢復後重送成功.png", full_page=True)

    erp = browser.new_page(viewport={"width": 1280, "height": 600})
    erp.goto(ERP)
    erp.screenshot(path=f"{OUT}/07_模擬ERP收到的訂單.png", full_page=True)

    phone = browser.new_page(viewport={"width": 375, "height": 812})
    phone.goto(URL)
    phone.click("#tab-staff")
    phone.fill("#staff-token", TOKEN)
    phone.click("#staff-form button")
    phone.wait_for_selector("#staff-result:not([hidden])")
    assert not phone.evaluate("document.documentElement.scrollWidth > window.innerWidth"), "手機版後台有橫向捲動"
    phone.screenshot(path=f"{OUT}/08_手機版後台.png", full_page=True)
    print("後台截圖完成")
    browser.close()
