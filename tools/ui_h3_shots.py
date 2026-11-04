"""H3 儀表板：瀏覽器實測與截圖（KPI、四張圖、滑過提示、數據表格、手機版）。"""
import os
from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "http://travelquote-app-1:8000/")
OUT = os.environ.get("OUT", "/shots")
PASSWORD = os.environ["MANAGER_PASSWORD"]


def login(browser, viewport):
    page = browser.new_context(viewport=viewport).new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    page.click("#tab-staff")
    page.fill("#login-username", "manager")
    page.fill("#login-password", PASSWORD)
    page.click("#staff-form button")
    page.wait_for_selector("#view-dashboard:not([hidden]) .stat")
    page.wait_for_selector("#chart-deals svg")
    return page, errors


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page, errors = login(browser, {"width": 1280, "height": 900})
    assert page.locator("#kpis .stat").count() == 6  # H6 加了「AI 評測」卡片
    assert page.locator("#chart-quotes .hit").count() == 14, "每日報價應該有 14 天"
    assert page.locator("#chart-packages .hbar-row").count() >= 3
    assert page.locator("#chart-sources .legend-item").count() == 3  # H4 加了「官網串接」來源
    page.screenshot(path=f"{OUT}/01_儀表板.png", full_page=True)

    hit = page.locator("#chart-deals .hit").nth(13)
    hit.hover()
    page.wait_for_selector(".chart-tip:not([hidden])")
    assert "成交金額" in page.inner_text(".chart-tip")
    # 提示框浮在圖表外面，截圖範圍要比圖表大一點才拍得到
    box = page.locator("#chart-deals").bounding_box()
    page.screenshot(path=f"{OUT}/02_滑過顯示數值.png", clip={
        "x": max(box["x"] - 20, 0), "y": max(box["y"] - 60, 0),
        "width": min(box["width"] + 260, 1280 - max(box["x"] - 20, 0)), "height": box["height"] + 80})

    page.locator("#chart-quotes .chart-table summary").click()
    page.locator("#chart-quotes").screenshot(path=f"{OUT}/03_數據表格.png")

    phone, phone_errors = login(browser, {"width": 375, "height": 812})
    assert not phone.evaluate("document.documentElement.scrollWidth > window.innerWidth"), "手機版儀表板有橫向捲動"
    phone.screenshot(path=f"{OUT}/04_手機版儀表板.png", full_page=True)
    assert not errors and not phone_errors, errors + phone_errors
    print("H3 截圖完成")
    browser.close()
