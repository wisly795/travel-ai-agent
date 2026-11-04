"""政府開放資料匯入測試（不連網、不動真實資料）：用假的 zip 測解析、比對、下架、查詢、AI 工具與 API。

在 app 容器內執行：python opendata_test.py
測試期間把資料表換成暫存的複製表，真實的 2 萬多筆資料不受影響。
"""
import io
import json
import urllib.error
import urllib.request
import zipfile

from app import agent, opendata
from app.db import connect, query

results = []


def check(name, passed, detail=""):
    passed = bool(passed)
    results.append(passed)
    print(("PASS" if passed else "FAIL"), name, detail)


def attraction(i, name, city="花蓮縣", status=1, images=True, desc="很美的地方，適合全家一起來走走看看，欣賞山海景色。"):
    return {"AttractionID": f"TEST_A_{i}", "AttractionName": name, "Description": desc, "PositionLat": 23.9,
            "PositionLon": 121.6, "AttractionClasses": [11, 24], "ServiceStatus": status, "IsAccessibleForFree": True,
            "PostalAddress": {"City": city, "Town": "秀林鄉", "StreetAddress": "測試路1號"},
            "Images": [{"Name": name, "URL": f"https://example.test/{i}.jpg"}] if images else [],
            "Organizations": [{"TaxCode": "12345678"}], "WebsiteURL": ""}


def hotel(i, name, low, high, city="臺東縣"):
    return {"HotelID": f"TEST_H_{i}", "HotelName": name, "Description": "海景民宿", "HotelClasses": [4], "HotelStars": 0,
            "PostalAddress": {"City": city, "Town": "成功鎮", "StreetAddress": "海岸路2號"}, "ServiceStatus": 1,
            "LowestPrice": low, "CeilingPrice": high, "TotalRooms": 4, "ServiceInfo": "無線網路,,,停車場",
            "Images": [], "Organizations": [{"TaxCode": "87654321"}]}


def make_zip(dataset, items, update_time="2026-11-04T08:00:00+08:00"):
    spec = opendata.DATASETS[dataset]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(spec["list"], "﻿" + json.dumps({"UpdateTime": update_time, spec["key"]: items}, ensure_ascii=False))
    return buffer.getvalue()


# 換成暫存表
REAL = {k: v["table"] for k, v in opendata.DATASETS.items()}
with connect() as conn:
    for dataset, table in REAL.items():
        conn.execute(f"DROP TABLE IF EXISTS {table}_test")
        conn.execute(f"CREATE TABLE {table}_test (LIKE {table} INCLUDING ALL)")
        opendata.DATASETS[dataset]["table"] = f"{table}_test"
first_import = query("SELECT coalesce(max(id), 0) AS n FROM od_imports")[0]["n"]
real_count = query(f"SELECT count(*) AS n FROM {REAL['attractions']}")[0]["n"]

try:
    # 1. 解析：BOM、歇業不收、不存統一編號
    items = [attraction(1, "清水斷崖"), attraction(2, "七星潭"), attraction(3, "已歇業的景點", status=2),
             attraction(1, "清水斷崖"), attraction(4, "臺東海岸", city="臺東縣", images=False, desc="短")]
    source_time, rows = opendata.parse("attractions", make_zip("attractions", items))
    check("解析官方格式（含 BOM）", source_time.startswith("2026-11-04") and len(rows) == 4, len(rows))
    check("歇業的不收", all(r["name"] != "已歇業的景點" for r in rows))
    check("不存統一編號等不需要的欄位", "12345678" not in json.dumps(rows))
    check("地址組合、圖片整理", rows[0]["address"] == "花蓮縣秀林鄉測試路1號" and rows[0]["images"][0]["url"].endswith("1.jpg"))

    # 2. 第一次匯入：重複的只算一次
    first = opendata.run_import("attractions", make_zip("attractions", items), trigger="測試")
    check("第一次匯入：新增 3 筆（重複的只算一次）", first["status"] == "完成" and first["inserted"] == 3, first)
    log = query("SELECT * FROM od_imports WHERE id = %s", (first["id"],))[0]
    check("匯入紀錄", log["status"] == "完成" and log["trigger"] == "測試" and log["source_time"].startswith("2026-11-04"))

    # 3. 第二次匯入：改一筆、少一筆、其他不變
    changed = [attraction(1, "清水斷崖", desc="介紹改了：太魯閣國家公園裡的海岸斷崖，景色壯觀。"), attraction(2, "七星潭")]
    second = opendata.run_import("attractions", make_zip("attractions", changed), trigger="測試")
    check("第二次匯入：更新 1、不變 1、下架 1", (second["updated"], second["unchanged"], second["removed"]) == (1, 1, 1), second)
    gone = query("SELECT active FROM od_attractions_test WHERE id = 'TEST_A_4'")[0]
    check("下架的不刪除，只標記", gone["active"] is False)

    # 4. 壞掉的檔案：記錄失敗，舊資料保留
    broken = opendata.run_import("attractions", b"not a zip", trigger="測試")
    check("下載或解析失敗會記錄原因", broken["status"] == "失敗" and query(
        "SELECT error FROM od_imports WHERE id = %s", (broken["id"],))[0]["error"])
    check("失敗時舊資料保留", query("SELECT count(*) AS n FROM od_attractions_test WHERE active")[0]["n"] == 2)

    # 5. 查詢
    opendata.run_import("hotels", make_zip("hotels", [hotel(1, "海風民宿", 2000, 3500), hotel(2, "高級海景飯店", 8000, 12000)]), trigger="測試")
    found = opendata.search("attractions", city="花蓮縣", keyword="斷崖")
    check("依縣市與關鍵字搜尋", found["total"] == 1 and found["items"][0]["name"] == "清水斷崖")
    check("景點類型轉成中文", found["items"][0]["class_names"] == ["自然風景", "水域環境"], found["items"][0]["class_names"])
    check("回傳資料來源與授權", found["source"] == "交通部觀光署 觀光資料庫" and "開放授權" in found["license"])
    cheap = opendata.search("hotels", city="臺東縣", max_price=3000)
    check("住宿依預算篩選", [h["name"] for h in cheap["items"]] == ["海風民宿"])
    check("縣市統計", {"city": "臺東縣", "attractions": 0, "hotels": 2} in opendata.cities())

    # 6. AI 工具：「台東」自動換成「臺東縣」，房價註明只是參考
    output, is_error = agent.run_tool("search_local_info", {"kind": "hotels", "city": "台東"}, None)
    check("AI 工具：縣市名稱自動轉換", not is_error and output["city"] == "臺東縣" and output["total"] == 2, output.get("city"))
    check("AI 工具：註明房價不是報價", "不是本系統報價" in output["note"] and output["items"][0]["registered_price_range"])
    _, is_error = agent.run_tool("search_local_info", {"kind": "food", "city": "花蓮"}, None)
    check("AI 工具：不支援的種類回錯誤", is_error)

    # 7. API
    def get(path):
        try:
            with urllib.request.urlopen("http://localhost:8000" + path, timeout=20) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, {}
    status, body = get("/api/explore/attractions?city=%E8%8A%B1%E8%93%AE%E7%B8%A3&limit=5")
    check("API 可以搜尋（真實資料表）", status == 200 and "items" in body and body["source"])
    status, _ = get("/api/explore/food")
    check("API 不支援的種類回 422", status == 422)
    status, _ = get("/api/explore/attractions/NO_SUCH_ID")
    check("API 找不到回 404", status == 404)
    request = urllib.request.Request("http://localhost:8000/api/admin/opendata/import", method="POST")
    try:
        urllib.request.urlopen(request, timeout=20)
        status = 200
    except urllib.error.HTTPError as error:
        status = error.code
    check("沒登入不能觸發匯入", status == 401)
finally:
    for dataset, table in REAL.items():
        opendata.DATASETS[dataset]["table"] = table
    with connect() as conn:
        for table in REAL.values():
            conn.execute(f"DROP TABLE IF EXISTS {table}_test")
        conn.execute("DELETE FROM od_imports WHERE id > %s AND trigger = '測試'", (first_import,))

check("真實資料沒有被動到", query(f"SELECT count(*) AS n FROM {REAL['attractions']}")[0]["n"] == real_count)
print(f"\n{sum(results)}/{len(results)} 通過")
raise SystemExit(0 if all(results) else 1)
