"""正式網址的畫面截圖與檢查（不登入、不用 AI，不花額度）。
用法：docker run --rm -v <專案>/tools:/t -v <專案>/docs/過程截圖:/shots -e OUT=/shots/I6_正式上線 travelquote-uitest python /t/ui_public_shots.py
"""
import os
from playwright.sync_api import sync_playwright

URL = "https://travel.34-80-26-168.sslip.io/"
OUT = os.environ.get("OUT", "/shots")
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    response = page.goto(URL)
    print("首頁：", response.status, "HTTPS" if page.url.startswith("https://") else "沒有 HTTPS", page.title())
    page.wait_for_timeout(1500)
    page.screenshot(path=f"{OUT}/正式網址_首頁.png")
    page.goto(URL + "explore")
    page.wait_for_timeout(1500)
    print("探索台灣：", page.locator("body").inner_text()[:80].replace("\n", " "))
    page.screenshot(path=f"{OUT}/正式網址_探索台灣.png")
    page.goto(URL + "tours")
    page.wait_for_timeout(1200)
    page.screenshot(path=f"{OUT}/正式網址_行程.png")
    mobile = browser.new_page(viewport={"width": 390, "height": 844})
    mobile.goto(URL)
    mobile.wait_for_timeout(1200)
    mobile.screenshot(path=f"{OUT}/正式網址_手機.png")
    browser.close()
