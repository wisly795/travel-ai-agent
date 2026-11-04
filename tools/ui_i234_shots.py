"""I2～I4 截圖：微調模型的規定搜尋、多 Agent 客服（真實 AI，約 0.01 美元）、監控（Grafana、Prometheus、告警信）。

docker run --rm --network travelquote_default -e SALES_PASSWORD=... -e ADMIN_PASSWORD=... -e GRAFANA_PASSWORD=...
  -v <tools>:/t -v <docs/過程截圖>:/shots travelquote-uitest python /t/ui_i234_shots.py
"""
import os
import sys

from playwright.sync_api import sync_playwright

URL = "http://travelquote-app-1:8000/"
OUT = os.environ.get("OUT", "/shots")
I2, I3, I4 = f"{OUT}/I2_微調模型", f"{OUT}/I3_多Agent", f"{OUT}/I4_監控"
for folder in (I2, I3, I4):
    os.makedirs(folder, exist_ok=True)


def login(page, user, password):
    page.goto(URL)
    page.goto(URL + "admin")
    page.fill("#login-username", user)
    page.fill("#login-password", password)
    page.click("#staff-form button")
    page.wait_for_selector("#staff-result:not([hidden])")


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    page = browser.new_context(viewport={"width": 1280, "height": 900}, locale="zh-TW").new_page()
    only_i4 = "i4" in sys.argv  # 只重拍監控，不再呼叫真實 AI

    if not only_i4:
        # I2：旅遊規定頁顯示微調模型；以前找不到的口語問法現在找得到
        page.goto(URL)
        page.click("#tab-policy")
        page.wait_for_selector("#policy-model:not(:empty)")
        page.fill("#policy-input", "人數不夠會不會開團")
        page.click("#policy-form button")
        page.wait_for_selector("#policy-results .policy-hit")
        page.locator("#policy-form").screenshot(path=f"{I2}/01_微調後口語問法找得到.png")

        # I3：多 Agent 模式，同時問報價和規定 → 兩位專員平行回答
        page.goto(URL)
        page.click("#tab-chat")
        page.check("input[name=chat-mode][value=multi]")
        page.fill("#chat-input", "4 個人去沖繩住海風飯店，海島放鬆 4 日多少錢？另外出發前一週取消會扣多少？")
        page.click("#chat-form button")
        page.wait_for_selector(".bubble.ai small", timeout=120000)
        page.wait_for_timeout(500)
        page.locator("#chat .panel").screenshot(path=f"{I3}/01_多Agent同時回答報價與規定.png")
        page.fill("#chat-input", "幫我寫一首詩")
        page.click("#chat-form button")
        page.wait_for_function("document.querySelectorAll('.bubble.ai small').length >= 3", timeout=120000)
        page.locator("#chat .panel").screenshot(path=f"{I3}/02_無關問題交給接待專員.png")

        login(page, "admin", os.environ["ADMIN_PASSWORD"])
        page.click("[data-view=view-turns]")
        page.locator("#turn-list details").nth(1).locator("summary").click()
        page.locator("#turn-list details").nth(1).screenshot(path=f"{I3}/03_後台看多Agent流程與每位專員的工具.png")
        page.click("[data-view=view-evals]")
        page.wait_for_selector("#eval-history tr")
        page.locator("#view-evals").screenshot(path=f"{I3}/04_評測單一與多Agent對照.png")

    # I4：Grafana 儀表板（先產生一些流量讓圖有資料）
    for _ in range(20):
        page.request.get(f"{URL}api/packages?people=2")
        page.request.get(f"{URL}api/policies/search?q=行李")
    g = browser.new_context(viewport={"width": 1500, "height": 1000}, locale="zh-TW").new_page()
    g.goto("http://grafana:3000/login")
    g.fill("input[name=user]", "admin")
    g.fill("input[name=password]", os.environ["GRAFANA_PASSWORD"])
    g.click("button[type=submit]")
    g.wait_for_load_state("networkidle")
    g.goto("http://grafana:3000/d/travel-ops?orgId=1&from=now-30m&to=now&kiosk")
    g.wait_for_timeout(8000)
    g.screenshot(path=f"{I4}/01_Grafana監控儀表板.png")
    g.goto("http://prometheus:9090/alerts")
    g.wait_for_timeout(3000)
    g.screenshot(path=f"{I4}/02_Prometheus告警規則.png", full_page=True)
    g.goto("http://prometheus:9090/targets")
    g.wait_for_timeout(3000)
    g.screenshot(path=f"{I4}/03_Prometheus抓取狀態.png")
    g.goto("http://mailpit:8025/")
    g.wait_for_timeout(2000)
    g.locator("text=系統告警").first.click()
    g.wait_for_timeout(2000)
    g.screenshot(path=f"{I4}/04_告警信寄到IT信箱.png")
    print("I2～I4 截圖完成")
    browser.close()
