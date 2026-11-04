"""前台旅遊網站畫面測試＋截圖（不呼叫真實 AI）：首頁、搜尋、行程列表、詳細頁試算與建立報價、探索台灣、旅遊須知、
AI 聊天泡泡、後台 /admin、手機版。

powershell -File tools\run_shots.ps1 -Script ui_site_test.py -Out J3_旅遊網站
"""
import os

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "http://travelquote-app-1:8000/")
OUT = os.environ.get("OUT", "/shots")
os.makedirs(OUT, exist_ok=True)
errors = []


def watch(page):
    page.on("pageerror", lambda e: errors.append(f"頁面錯誤：{e}"))
    page.on("console", lambda m: errors.append(f"console：{m.text}") if m.type == "error" and "Failed to load resource" not in m.text else None)


def no_sideways_scroll(page, name):
    assert not page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"), f"{name} 有橫向捲動"


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_context(viewport={"width": 1366, "height": 900}, locale="zh-TW").new_page()
    watch(page)
    # CI 不自動匯入開放資料（不依賴政府網站）：沒有資料時跳過開放資料相關的檢查
    has_opendata = bool(page.request.get(URL + "api/explore/cities").json()["cities"])
    print("開放資料：", "有" if has_opendata else "沒有（跳過景點相關檢查）")

    # 首頁
    page.goto(URL)
    page.wait_for_selector("#home-tours .s-card")
    if has_opendata:
        page.wait_for_selector("#home-cities .s-city", timeout=20000)
    page.wait_for_timeout(2500)  # 等照片載入
    assert page.locator("#home-tours .s-card").count() == 8
    page.screenshot(path=f"{OUT}/01_首頁.png")
    page.screenshot(path=f"{OUT}/02_首頁完整.png", full_page=True)

    # 搜尋 → 行程列表（條件在網址上）
    page.select_option("#home-destination", "沖繩")
    page.fill("#home-people", "4")
    page.click(".s-search button")
    page.wait_for_url("**/tours?**")
    page.wait_for_selector("#tour-list .s-card")
    assert "destination=" in page.url and page.locator("#tour-list .s-card").count() == 2, page.url
    page.screenshot(path=f"{OUT}/03_搜尋沖繩4人.png")

    # 行程詳細頁：試算 → 建立報價
    page.click("#tour-list .s-card >> nth=0")
    page.wait_for_selector("#book-total")
    first_total = page.inner_text("#book-total")
    page.fill("#book-people", "4")
    page.wait_for_function(f"document.querySelector('#book-total') && document.querySelector('#book-total').textContent !== '{first_total}'")
    assert page.inner_text("#book-total") == "NT$ 107,200", page.inner_text("#book-total")  # 22000×4＋3200×2間×3晚
    page.locator("input[type=date]").fill(page.locator("#book-date").get_attribute("min"))
    page.fill("#book-name", "網站測試客人")
    page.wait_for_timeout(500)
    page.screenshot(path=f"{OUT}/04_行程詳細頁試算.png", full_page=True)
    page.click("#book-form button[type=submit]")
    page.wait_for_selector("#book-result")
    assert "已建立" in page.inner_text("#book-result")
    page.locator("#book-form").screenshot(path=f"{OUT}/05_建立報價成功.png")

    # 台灣行程：附近景點（開放資料）與供應商參考價（爬蟲）
    page.goto(URL + "tours/7")
    page.wait_for_selector("#supplier-prices tbody tr")
    page.locator("#supplier-prices").screenshot(path=f"{OUT}/07_供應商參考價.png")
    if has_opendata:
        page.wait_for_selector("#nearby-spots .s-attr", timeout=20000)
        page.wait_for_timeout(2000)
        page.locator("#nearby-spots").screenshot(path=f"{OUT}/06_花蓮行程附近景點.png")

    # 探索台灣
    if has_opendata:
        page.goto(URL + "explore")
        page.wait_for_selector("#city-list .s-city")
        page.wait_for_timeout(3000)
        assert page.locator("#city-list .s-city").count() >= 20
        page.screenshot(path=f"{OUT}/08_探索台灣.png")
        page.click("#city-list .s-city >> text=臺東縣")
        page.wait_for_selector("#explore-list .s-attr")
        page.wait_for_timeout(2500)
        page.screenshot(path=f"{OUT}/09_臺東景點.png")
        # 點景點卡片要打開詳細內容（I6 驗收問題 8），可用 Esc 關閉
        page.locator("#explore-list .s-attr-btn").first.click()
        page.wait_for_selector(".s-modal #detail-title")
        assert "google.com/maps" in page.get_attribute(".s-modal a.s-btn", "href")
        assert "交通部觀光署" in page.inner_text(".s-modal")
        page.wait_for_timeout(1500)
        page.screenshot(path=f"{OUT}/09b_景點詳細內容.png")
        page.keyboard.press("Escape")
        page.wait_for_selector(".s-modal", state="detached")
        page.click(".s-chip >> text=溫泉")
        page.wait_for_function("document.querySelector('#explore-count').textContent.includes('筆')")
        page.wait_for_timeout(1500)
        page.click(".s-chip >> text=住宿")
        page.wait_for_selector("#hotel-budget")
        page.click(".s-chip >> text=全部")
        page.select_option("#hotel-budget", "2000")
        page.wait_for_timeout(2000)
        page.screenshot(path=f"{OUT}/10_臺東平價住宿.png")
        before = page.locator("#explore-list .s-attr").count()
        page.click(".s-more button")
        page.wait_for_function(f"document.querySelectorAll('#explore-list .s-attr').length > {before}")
    else:
        page.goto(URL + "explore")
        page.wait_for_selector("text=資料準備中")

    # 旅遊須知
    page.goto(URL + "guide")
    page.fill("#policy-input", "出發前一週取消可以退多少")
    page.click("#policy-form button")
    page.wait_for_selector("#policy-results .policy-hit")
    page.screenshot(path=f"{OUT}/11_旅遊須知搜尋.png")

    # AI 聊天泡泡（只打開看狀態，不送出，避免花費）
    page.click(".s-chat-fab")
    page.wait_for_selector(".s-chat.open #chat-status:not(:empty)")
    page.wait_for_timeout(400)
    page.screenshot(path=f"{OUT}/12_AI聊天泡泡.png")

    # 重新整理不會 404（單頁應用的網址）
    response = page.goto(URL + "explore/%E8%8A%B1%E8%93%AE%E7%B8%A3")
    assert response.status == 200
    page.wait_for_selector("#city-title")

    # 後台：/admin
    page.goto(URL + "admin")
    page.fill("#login-username", "admin")
    page.fill("#login-password", os.environ["ADMIN_PASSWORD"])
    page.click("#staff-form button")
    page.wait_for_selector("#staff-result:not([hidden])")
    page.click("[data-view=view-data]")
    page.wait_for_selector("#crawl-rows tr")
    page.screenshot(path=f"{OUT}/13_後台資料與爬蟲.png", full_page=True)

    # 手機版
    phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, locale="zh-TW").new_page()
    watch(phone)
    phone.goto(URL)
    phone.wait_for_selector("#home-tours .s-card")
    phone.wait_for_timeout(2500)
    no_sideways_scroll(phone, "手機首頁")
    phone.screenshot(path=f"{OUT}/14_手機首頁.png")
    phone.click(".s-menu-btn")
    phone.wait_for_selector(".s-links.open")
    phone.screenshot(path=f"{OUT}/15_手機選單.png")
    phone.goto(URL + "tours/1")
    phone.wait_for_selector("#book-total")
    no_sideways_scroll(phone, "手機行程頁")
    phone.screenshot(path=f"{OUT}/16_手機行程頁.png", full_page=True)
    phone.goto(URL + "explore/%E8%8A%B1%E8%93%AE%E7%B8%A3")
    phone.wait_for_selector("#explore-list .s-attr" if has_opendata else "#explore-count")
    no_sideways_scroll(phone, "手機探索頁")
    phone.click(".s-chat-fab")
    phone.wait_for_selector(".s-chat.open")
    phone.wait_for_timeout(400)
    phone.screenshot(path=f"{OUT}/17_手機AI客服.png")

    assert not errors, errors[:5]
    print("前台畫面測試全部通過")
    browser.close()
