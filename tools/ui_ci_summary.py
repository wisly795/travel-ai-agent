"""讀 GitHub Actions 執行頁面上的測試摘要（公開頁面，不需登入），並截圖。

docker run --rm -v <tools>:/t -v <截圖資料夾>:/shots travelquote-uitest python /t/ui_ci_summary.py <run_id> [檔名]
"""
import os
import sys

from playwright.sync_api import sync_playwright

RUN = sys.argv[1]
NAME = sys.argv[2] if len(sys.argv) > 2 else "CI摘要"
OUT = os.environ.get("OUT", "/shots")

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1300, "height": 1000}, locale="zh-TW")
    page.goto(f"https://github.com/wisly795/travel-ai-agent/actions/runs/{RUN}", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(6000)
    summary = page.locator("text=測試結果").first
    if summary.count():
        summary.scroll_into_view_if_needed()
        page.wait_for_timeout(1000)
    page.screenshot(path=f"{OUT}/{NAME}.png", full_page=True)
    body = page.inner_text("body")
    start = body.find("測試結果")
    print(body[start:start + 2500] if start >= 0 else body[:1500])
    browser.close()
