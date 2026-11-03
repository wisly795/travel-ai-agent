"""用真實瀏覽器操作網頁，並保存過程截圖。"""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "http://travelquote-app-1:8000/")
OUT = os.environ.get("OUT", "/shots")
SALES_PASSWORD = os.environ["SALES_PASSWORD"]

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    page.wait_for_function("document.getElementById('destination').options.length > 1")
    page.wait_for_function("document.getElementById('chat-status').textContent.length > 0")
    ai_enabled = "尚未啟用" not in page.inner_text("#chat-status")
    # 沒有金鑰時預設打開「查行程」，有金鑰時預設打開「AI 客服」
    assert page.is_visible("#chat" if ai_enabled else "#customer")

    page.click("#tab-chat")
    assert page.locator(".bubble.ai").count() == 1
    assert page.locator(".chip").count() == 3
    page.screenshot(path=f"{OUT}/01_AI客服畫面.png")
    if not ai_enabled:
        page.locator(".chip").first.click()
        page.wait_for_selector(".bubble.error")
        assert "尚未啟用" in page.inner_text(".bubble.error")
        assert page.locator(".bubble.user").count() == 1
        page.screenshot(path=f"{OUT}/02_AI未啟用提示.png")
    page.click("#chat-new")
    assert page.locator(".bubble").count() == 1 and page.is_visible("#chat-examples")

    page.click("#tab-customer")
    page.select_option("#destination", "沖繩")
    page.fill("#people", "3")
    page.click("#search-form button")
    page.wait_for_selector(".card")
    assert page.locator(".card").count() == 2
    page.screenshot(path=f"{OUT}/03_查詢結果.png", full_page=True)

    page.locator(".card", has_text="海島放鬆").get_by_role("button", name="選擇").click()
    page.wait_for_selector("#quote-form:not([hidden])")
    page.select_option("#hotel", label="海風飯店（雙人房，每晚 NT$ 3,200）")
    page.fill("#departure-date", page.get_attribute("#departure-date", "min"))
    page.fill("#customer-name", "王小明")
    page.click("#quote-form button")
    page.wait_for_selector("#result:not([hidden])")
    assert "NT$ 85,200" in page.inner_text("#result")
    assert "出發" in page.inner_text("#result") and "回程" in page.inner_text("#result")
    page.screenshot(path=f"{OUT}/04_建立報價.png", full_page=True)

    page.click("#tab-policy")
    page.wait_for_selector("#policy-list details")
    assert page.locator("#policy-list details").count() == 6
    page.fill("#policy-input", "出發前一週取消可以退多少？")
    page.click("#policy-form button")
    page.wait_for_selector(".policy-hit")
    assert "取消與退費規定 第3條" in page.inner_text("#policy-results")
    page.screenshot(path=f"{OUT}/07_查規定向量搜尋.png", full_page=True)
    page.fill("#policy-input", "推薦我好看的電影")
    page.click("#policy-form button")
    page.wait_for_function("document.getElementById('policy-results').innerText.includes('找不到')")

    page.click("#tab-staff")
    page.fill("#login-username", "sales")
    page.fill("#login-password", "wrong-password1")
    page.click("#staff-form button")
    page.wait_for_selector("#message:not([hidden])")
    assert "不正確" in page.inner_text("#message")
    page.fill("#login-password", SALES_PASSWORD)
    page.click("#staff-form button")
    page.wait_for_selector("#staff-result:not([hidden])")
    assert "示範業務" in page.inner_text("#whoami")
    assert page.is_hidden("#subtab-users"), "業務不應該看到帳號管理"
    assert page.is_visible("#view-dashboard"), "登入後預設顯示儀表板"
    page.click("[data-view=view-quotes]")
    assert "王小明" in page.inner_text("#quote-rows")
    assert "網頁" in page.inner_text("#quote-rows")
    page.screenshot(path=f"{OUT}/05_業務後台.png", full_page=True)

    with page.expect_download() as info:
        page.click("#export")
    assert info.value.suggested_filename == "quotes.csv"

    phone = browser.new_page(viewport={"width": 375, "height": 812})
    phone.goto(URL)
    phone.wait_for_function("document.getElementById('chat-status').textContent.length > 0")
    phone.click("#tab-chat")
    overflow = phone.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    assert not overflow, "手機版 AI 客服有橫向捲動"
    phone.screenshot(path=f"{OUT}/06_手機版AI客服.png")
    phone.click("#tab-customer")
    phone.click("#search-form button")
    phone.wait_for_selector(".card")
    overflow = phone.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    assert not overflow, "手機版查行程有橫向捲動"

    assert not errors, errors
    print("UI 測試全部通過")
    browser.close()
