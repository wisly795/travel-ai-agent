"""H2 帳號登入：瀏覽器實測登入失敗、業務權限、主管核准、管理員帳號管理，並截圖。"""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "http://travelquote-app-1:8000/")
OUT = os.environ.get("OUT", "/shots")
PASSWORDS = {"sales": os.environ["SALES_PASSWORD"], "manager": os.environ["MANAGER_PASSWORD"],
             "admin": os.environ["ADMIN_PASSWORD"]}


def login(browser, username, password=None, viewport=None):
    """每個角色開一個全新的瀏覽器視窗：登入狀態存在分頁裡，同一個分頁換帳號會自動恢復上一位的登入。"""
    page = browser.new_context(viewport=viewport or {"width": 1280, "height": 900}).new_page()
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(URL)
    page.click("#tab-staff")
    page.fill("#login-username", username)
    page.fill("#login-password", password or PASSWORDS[username])
    page.click("#staff-form button")
    return page


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = login(browser, "sales", "wrong-password1")
    page.wait_for_selector("#message:not([hidden])")
    page.screenshot(path=f"{OUT}/01_密碼錯誤.png")

    page = login(browser, "sales")
    page.wait_for_selector("#staff-result:not([hidden])")
    assert page.is_hidden("#subtab-users")
    page.screenshot(path=f"{OUT}/02_業務登入後.png")

    page.click("[data-view=view-procurement]")
    big = page.locator(".pr-card", has_text="需要主管核准").filter(has=page.get_by_role("button", name="核准並下單")).first
    big.get_by_role("button", name="核准並下單").click()
    page.wait_for_selector("#message:not([hidden])")
    assert "主管帳號" in page.inner_text("#message")
    big.scroll_into_view_if_needed()
    page.screenshot(path=f"{OUT}/03_業務不能核准大額.png")
    page.reload()
    page.click("#tab-staff")
    page.wait_for_selector("#staff-result:not([hidden])")
    assert "示範業務" in page.inner_text("#whoami"), "重新整理後應該保持登入"

    page = login(browser, "manager")
    page.wait_for_selector("#staff-result:not([hidden])")
    page.click("[data-view=view-procurement]")
    big = page.locator(".pr-card", has_text="需要主管核准").filter(has=page.get_by_role("button", name="核准並下單")).first
    title = big.locator("h3").inner_text().split("｜")[0]  # 「請購單 #N」，核准後狀態文字會變，只用編號找
    big.get_by_role("button", name="核准並下單").click()
    page.wait_for_function(f"[...document.querySelectorAll('.pr-card')].some(c => c.innerText.includes({title!r}) && c.innerText.includes('處理人：示範主管'))")
    page.locator(".pr-card", has_text=title).first.screenshot(path=f"{OUT}/04_主管核准並記錄處理人.png")

    page = login(browser, "admin")
    page.wait_for_selector("#staff-result:not([hidden])")
    assert page.is_visible("#subtab-users")
    page.click("[data-view=view-users]")
    page.fill("#new-username", "demo_sales2")
    page.fill("#new-display", "新進業務")
    page.fill("#new-password", "short")
    page.click("#user-form button")
    page.wait_for_selector("#message:not([hidden])")
    assert "8 碼" in page.inner_text("#message")
    page.fill("#new-password", "welcome2026")
    page.click("#user-form button")
    page.wait_for_function("document.getElementById('user-rows').innerText.includes('demo_sales2')")
    page.screenshot(path=f"{OUT}/05_管理員帳號管理與登入紀錄.png", full_page=True)

    page.click("#logout")
    page.wait_for_selector("#staff-form:not([hidden])")
    phone = login(browser, "sales", viewport={"width": 375, "height": 812})
    phone.wait_for_selector("#staff-result:not([hidden])")
    assert not phone.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    phone.screenshot(path=f"{OUT}/06_手機版登入後.png")
    print("H2 截圖完成")
    browser.close()
