"""作品集截圖：在乾淨的展示資料上，依頁面順序截圖（AI 客服部分會花一點 API 額度）。

後台用主管帳號登入；圖片存到 OUT（預設 /shots），檔名就是作品集引用的名稱。
"""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "http://travelquote-app-1:8000/")
ERP = "http://travelquote-erp-1:8000/"
SITE = "http://travelquote-website-1:8000/"
MAIL = "http://travelquote-mailpit-1:8025/"
OUT = os.environ.get("OUT", "/shots")
MANAGER = os.environ["MANAGER_PASSWORD"]


def ask(page, text):
    done = page.locator(".bubble.ai:not(.waiting), .bubble.error").count()
    page.fill("#chat-input", text)
    page.click("#chat-form button")
    page.wait_for_function(
        f"document.querySelectorAll('.bubble.ai:not(.waiting), .bubble.error').length > {done}", timeout=180000)


def view(page, name, file, full=True):
    page.click(f"[data-view={name}]")
    page.wait_for_timeout(800)
    page.screenshot(path=f"{OUT}/{file}", full_page=full)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto(URL)
    page.wait_for_selector("#chat:not([hidden])")
    ask(page, "2 個人想去京都 5 天，每人預算 4 萬，住最便宜的飯店總共多少？")
    page.screenshot(path=f"{OUT}/01_AI客服報價.png", full_page=True)
    page.click("#chat-new")
    ask(page, "出發前 10 天取消，團費 65,600 元會扣多少？")
    page.screenshot(path=f"{OUT}/02_AI依規定算退費.png", full_page=True)

    page.click("#tab-policy")
    page.fill("#policy-input", "去沖繩要辦簽證嗎？")
    page.click("#policy-form button")
    page.wait_for_selector(".policy-hit")
    page.screenshot(path=f"{OUT}/03_RAG向量搜尋.png")

    page.click("#tab-staff")
    page.fill("#login-username", "manager")
    page.fill("#login-password", MANAGER)
    page.click("#staff-form button")
    page.wait_for_selector("#chart-deals svg")
    page.wait_for_timeout(800)
    page.screenshot(path=f"{OUT}/11_儀表板.png", full_page=True)
    view(page, "view-quotes", "04_後台報價與ERP.png")
    page.click("[data-view=view-turns]")
    page.locator(".turn summary", has_text="退多少").first.click()
    page.screenshot(path=f"{OUT}/05_AI對話紀錄.png", full_page=True)
    view(page, "view-procurement", "06_採購Agent.png")
    view(page, "view-erp", "07_ERP同步.png")
    view(page, "view-notifications", "08_n8n通知中心.png")
    view(page, "view-evals", "12_AI評測.png")

    erp = browser.new_context(viewport={"width": 1280, "height": 500}).new_page()
    erp.goto(ERP)
    erp.screenshot(path=f"{OUT}/09_模擬ERP.png")

    site = browser.new_context(viewport={"width": 1280, "height": 760}).new_page()
    site.goto(SITE + "?destination=沖繩&people=2")
    site.wait_for_selector("form.card h3")
    site.screenshot(path=f"{OUT}/13_模擬官網.png")

    mail = browser.new_context(viewport={"width": 1280, "height": 700}).new_page()
    mail.goto(MAIL)
    mail.wait_for_selector("text=旅遊報價系統", timeout=30000)
    mail.get_by_text("新報價 #", exact=False).first.click()
    mail.wait_for_timeout(1200)
    mail.screenshot(path=f"{OUT}/14_通知信.png")

    phone = browser.new_context(viewport={"width": 390, "height": 844}).new_page()
    phone.goto(URL)
    phone.wait_for_selector("#chat:not([hidden])")
    phone.screenshot(path=f"{OUT}/10_手機版.png")
    print("作品集截圖完成")
    browser.close()
