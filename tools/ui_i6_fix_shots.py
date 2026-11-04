"""I6 人工驗收畫面問題（4～6）修正後的截圖與檢查，不花 API 額度。
用法：powershell -File tools\run_shots.ps1 ui_i6_fix_shots.py -Out I6_人工驗收
"""
import os
from playwright.sync_api import sync_playwright

URL = "http://travelquote-app-1:8000/"
OUT = os.environ.get("OUT", "/shots")

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=os.environ.get("CHROME"), args=["--no-sandbox"])
    # 1366×768：一般筆電螢幕，驗收時報價表要左右捲動的寬度
    page = browser.new_page(viewport={"width": 1366, "height": 768})
    page.goto(URL + "admin")
    page.fill("#login-username", "sales")
    page.fill("#login-password", os.environ["SALES_PASSWORD"])
    page.click("#staff-form button")
    page.wait_for_selector("#kpis .stat")
    page.wait_for_timeout(800)

    # 問題 4：圖表日期標籤不重疊
    labels = page.eval_on_selector_all(
        "#chart-quotes svg text.tick[text-anchor=middle]",
        "els => els.map(e => { const b = e.getBBox(); return [e.textContent, b.x, b.x + b.width]; })")
    overlap = any(a[2] > b[1] for a, b in zip(labels, labels[1:]))
    print("問題 4 日期標籤：", [l[0] for l in labels], "重疊" if overlap else "不重疊")
    page.locator("#chart-quotes").screenshot(path=f"{OUT}/修正4_圖表日期不重疊.png")

    # 問題 5：報價表不用左右捲動
    page.click("[data-view=view-quotes]")
    page.wait_for_selector("#quote-rows tr")
    wrap = page.eval_on_selector("#view-quotes .table-wrap", "e => [e.scrollWidth, e.clientWidth]")
    print("問題 5 報價表寬度（內容／可見）：", wrap, "要捲動" if wrap[0] > wrap[1] else "不用捲動")
    page.screenshot(path=f"{OUT}/修正5_報價表不用捲動_1366.png")

    # 問題 6：採購 AI 的紀錄標成「採購系統」。畫面只列最近 30 筆，採購那筆已被評測擠到後面，
    # 所以用 API 查最近 200 筆確認標示，再把那一筆用同樣的畫面元件顯示出來截圖
    token = page.request.post(URL + "api/auth/login", data={"username": "sales", "password": os.environ["SALES_PASSWORD"]}).json()["token"]
    turns = page.request.get(URL + "api/admin/turns?limit=200", headers={"Authorization": f"Bearer {token}"}).json()
    buys = [t for t in turns if t["user_message"].startswith("【採購】")]
    print("問題 6 採購紀錄：", [(t["id"], t["speaker"]) for t in buys], "／客人紀錄標示：", {t["speaker"] for t in turns if t not in buys})
    page.click("[data-view=view-turns]")
    page.wait_for_selector("#turn-list details")
    page.route("**/api/admin/turns*", lambda route: route.fulfill(json=buys[:1] + [t for t in turns if t not in buys][:1]))
    page.click("[data-view=view-quotes]")
    page.click("[data-view=view-turns]")
    page.reload()
    page.wait_for_selector("#kpis .stat")
    page.click("[data-view=view-turns]")
    page.wait_for_selector("#turn-list details")
    page.locator("#turn-list details").first.locator("summary").click()
    print("問題 6 畫面標題：", [s[:40] for s in page.locator("#turn-list summary").all_inner_texts()])
    page.locator("#view-turns").screenshot(path=f"{OUT}/修正6_採購紀錄標示.png")
    browser.close()
