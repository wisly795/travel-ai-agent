"""API 覆蓋表：列出全部 API，逐一找出被哪支測試呼叫到，沒被測到的標出來。不用容器，直接讀原始碼。

python tools/api_coverage.py [輸出的 Markdown 路徑]
做法：從 main.py、partner.py 抓出每個路由（方法＋路徑），把 {quote_id} 這類參數換成「任意一段」，
再到 tools/*_test.py 與 ui_*test.py 找符合的網址字串（含 f-string 組出來的網址）。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROUTE = re.compile(r'^@(app|partner_app)\.(get|post|patch|put|delete)\("([^"]+)"', re.M)


def routes():
    found = []
    for path, prefix in ((ROOT / "backend/app/main.py", ""), (ROOT / "backend/app/partner.py", "/partner")):
        for app_name, method, url in ROUTE.findall(path.read_text(encoding="utf-8")):
            full = (prefix + url) if app_name == "partner_app" else url
            if full.startswith(("/api", "/partner", "/metrics")):
                found.append((method.upper(), full))
    return found


def pattern(url):
    """/api/quotes/{quote_id}/status → 可以比對 /api/quotes/123/status、/api/quotes/{q['id']}/status。"""
    parts = []
    for piece in re.split(r"(\{[^}]+\})", url):
        parts.append(r"[^/\"'?\s]+" if piece.startswith("{") else re.escape(piece))
    return re.compile("".join(parts) + r"(?=[\"'?\s]|$)")


def main():
    tests = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "tools").glob("*.py")
             if p.name.endswith("_test.py") or p.name in ("rag_eval.py",)}
    rows, missing = [], []
    for method, url in sorted(set(routes()), key=lambda r: (r[1], r[0])):
        rx = pattern(url)
        hits = sorted(name for name, text in tests.items() if rx.search(text))
        rows.append((method, url, hits))
        if not hits:
            missing.append((method, url))
    lines = ["# API 覆蓋表", "", f"共 {len(rows)} 支 API，有測試呼叫的 {len(rows) - len(missing)} 支，沒有的 {len(missing)} 支。", "",
             "| 方法 | 路徑 | 測試 |", "|---|---|---|"]
    lines += [f"| {m} | `{u}` | {'、'.join(h) if h else '**沒有**'} |" for m, u, h in rows]
    text = "\n".join(lines) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(text, encoding="utf-8")
    print(f"共 {len(rows)} 支，沒被測到 {len(missing)} 支")
    for m, u in missing:
        print("  沒有：", m, u)


if __name__ == "__main__":
    main()
