"""H6 AI 評測：管理員從後台按鈕執行評測（真實 AI，約 2 分鐘），等跑完後截圖結果與儀表板分數。"""
import os
from playwright.sync_api import sync_playwright

URL = "http://travelquote-app-1:8000/"
OUT = os.environ.get("OUT", "/shots")

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    sales = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    sales.goto(URL)
    sales.click("#tab-staff")
    sales.fill("#login-username", "sales")
    sales.fill("#login-password", os.environ["SALES_PASSWORD"])
    sales.click("#staff-form button")
    sales.wait_for_selector("#staff-result:not([hidden])")
    sales.click("[data-view=view-evals]")
    assert sales.is_hidden("#eval-run"), "業務看得到結果，但不能執行評測"

    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto(URL)
    page.click("#tab-staff")
    page.fill("#login-username", "admin")
    page.fill("#login-password", os.environ["ADMIN_PASSWORD"])
    page.click("#staff-form button")
    page.wait_for_selector("#staff-result:not([hidden])")
    page.click("[data-view=view-evals]")
    page.click("#eval-run")
    page.wait_for_function("document.getElementById('eval-run').textContent.includes('執行中')")
    page.screenshot(path=f"{OUT}/01_評測執行中.png")
    page.wait_for_function("!document.getElementById('eval-run').disabled", timeout=400000, polling=5000)
    page.screenshot(path=f"{OUT}/02_評測結果.png", full_page=True)
    page.click("[data-view=view-dashboard]")
    page.reload()
    page.click("#tab-staff")
    page.wait_for_selector("#kpis .stat")
    page.locator("#kpis").screenshot(path=f"{OUT}/03_儀表板顯示評測分數.png")
    print("H6 截圖完成")
    browser.close()
