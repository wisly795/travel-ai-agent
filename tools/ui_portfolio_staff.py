"""作品集補截：後台儀表板與報價列表（不呼叫 AI）。"""
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
    page.wait_for_selector("#chart-deals svg")
    page.wait_for_timeout(800)
    assert "官網串接 1" in page.inner_text("#chart-sources")
    page.screenshot(path="/shots/11_儀表板.png", full_page=True)
    page.click("[data-view=view-quotes]")
    page.wait_for_timeout(800)
    page.screenshot(path="/shots/04_後台報價與ERP.png", full_page=True)
    print("補截完成")
    browser.close()
