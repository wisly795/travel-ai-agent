"""補截：儀表板的 AI 評測分數卡片。"""
import os
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
    page.goto("http://travelquote-app-1:8000/")
    page.goto(URL + "admin")
    page.fill("#login-username", "manager")
    page.fill("#login-password", os.environ["MANAGER_PASSWORD"])
    page.click("#staff-form button")
    page.wait_for_function("document.getElementById('kpis').innerText.includes('AI 評測')")
    assert "20 / 20" in page.inner_text("#kpis")
    page.locator("#kpis").screenshot(path="/shots/03_儀表板顯示評測分數.png")
    page.click("[data-view=view-evals]")
    page.wait_for_selector("#eval-rows tr")
    assert page.locator("#eval-rows td", has_text="通過").count() >= 20
    page.screenshot(path="/shots/02_評測結果.png", full_page=True)
    print("補截完成")
    browser.close()
