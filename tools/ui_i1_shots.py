"""I1 截圖：GitHub 倉庫首頁與 CI 執行結果（公開頁面，不需登入）。"""
import os
import sys

from playwright.sync_api import sync_playwright

OUT = os.environ.get("OUT", "/shots")
RUN = sys.argv[1]
REPO = "https://github.com/wisly795/travel-ai-agent"

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1400, "height": 900}, locale="zh-TW")
    page.goto(REPO, wait_until="domcontentloaded", timeout=90000); page.wait_for_timeout(4000)
    page.screenshot(path=f"{OUT}/01_GitHub倉庫首頁.png")
    page.goto(f"{REPO}/actions/runs/{RUN}", wait_until="domcontentloaded", timeout=90000); page.wait_for_timeout(4000)
    page.screenshot(path=f"{OUT}/02_CI執行成功.png")
    job = page.locator("a[href*='/job/']").first
    if job.count():
        job.click()
        page.wait_for_load_state("load")
        page.wait_for_timeout(3000)
        page.screenshot(path=f"{OUT}/03_CI每個步驟.png", full_page=True)
    browser.close()
print("done")
