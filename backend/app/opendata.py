"""政府開放資料：交通部觀光署「觀光資料庫」的景點與旅宿（真實資料，政府資料開放授權條款第 1 版）。

ETL 流程：下載 zip → 解析 JSON → 整理欄位 → 和資料庫比對（新增／更新／不變／下架）→ 寫入 → 記錄這次匯入。
每天由 n8n 觸發；第一次啟動資料庫沒有資料時，在背景自動匯入一次。
行程與報價仍是模擬資料；這裡的房價只是業者向官方登記的價格區間，僅供參考。
"""
import hashlib
import io
import json
import os
import threading
import urllib.request
import zipfile
from datetime import datetime

from .db import connect, query

SOURCE = "交通部觀光署 觀光資料庫"
LICENSE = "政府資料開放授權條款-第1版"
BASE_URL = os.environ.get("OPENDATA_BASE_URL", "https://media.taiwan.net.tw/XMLReleaseAll_public/v2.0/Zh_tw")
DATASETS = {
    "attractions": {"file": "Attraction-json.zip", "list": "AttractionList.json", "key": "Attractions", "table": "od_attractions"},
    "hotels": {"file": "Hotel-json.zip", "list": "HotelList.json", "key": "Hotels", "table": "od_hotels"},
}
# 代碼表出自《觀光資料標準 V2.0》第 14 節景點類型代碼、第 20 節旅宿類型代碼；查不到的代碼顯示「其他」
ATTRACTION_CLASSES = {1: "文化", 2: "生態", 3: "文化資產", 4: "宗教廟宇", 5: "藝術", 6: "商圈商店", 7: "國家公園",
                      8: "國家風景區", 9: "休閒農業", 10: "溫泉", 11: "自然風景", 12: "遊憩", 13: "體育健身",
                      14: "觀光工廠", 15: "都會公園", 16: "森林遊樂區", 17: "平地森林園區", 18: "國家自然公園",
                      19: "公園綠地", 20: "觀光遊樂業", 21: "原住民文化", 22: "客家文化", 23: "交通場站",
                      24: "水域環境", 25: "藝文場館", 26: "生態場館", 27: "娛樂場館", 254: "其他"}
HOTEL_CLASSES = {1: "國際觀光旅館", 2: "一般觀光旅館", 3: "一般旅館", 4: "民宿", 5: "露營區", 9: "其他"}

_lock = threading.Lock()


def _text(value, limit=None):
    value = (value or "").strip() if isinstance(value, str) else ""
    return value[:limit] if limit else value


def _images(item):
    """只留圖片網址與說明，最多 3 張。"""
    out = []
    for image in item.get("Images") or []:
        url = image.get("URL") if isinstance(image, dict) else None
        if url and url.startswith("http"):
            out.append({"url": url, "name": _text(image.get("Name"), 100)})
    return out[:3]


def normalize(dataset, item):
    """把官方欄位整理成系統用的欄位；歇業（ServiceStatus 不是 1）的不收。統一編號等不需要的欄位不存。"""
    if item.get("ServiceStatus", 1) != 1:
        return None
    address = item.get("PostalAddress") or {}
    common = {
        "city": _text(address.get("City")), "town": _text(address.get("Town")),
        "address": _text(address.get("City")) + _text(address.get("Town")) + _text(address.get("StreetAddress")),
        "lat": item.get("PositionLat"), "lon": item.get("PositionLon"),
        "description": _text(item.get("Description"), 2000), "images": _images(item),
        "website": _text(item.get("WebsiteURL"), 300),
    }
    if dataset == "attractions":
        if not item.get("AttractionID") or not item.get("AttractionName"):
            return None
        return {"id": item["AttractionID"], "name": _text(item["AttractionName"], 200),
                "classes": [c for c in item.get("AttractionClasses") or [] if isinstance(c, int)],
                "free": bool(item.get("IsAccessibleForFree")), **common}
    if not item.get("HotelID") or not item.get("HotelName"):
        return None
    low, high = item.get("LowestPrice") or None, item.get("CeilingPrice") or None
    return {"id": item["HotelID"], "name": _text(item["HotelName"], 200),
            "classes": [c for c in item.get("HotelClasses") or [] if isinstance(c, int)],
            "stars": item.get("HotelStars") or 0, "lowest_price": low, "ceiling_price": high,
            "total_rooms": item.get("TotalRooms") or 0, "services": _text(item.get("ServiceInfo"), 500).strip(", "),
            **common}


def parse(dataset, data):
    """讀 zip 裡的清單 JSON，回傳（官方更新時間, 整理後的資料）。"""
    spec = DATASETS[dataset]
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        raw = json.loads(archive.read(spec["list"]).decode("utf-8-sig"))
    rows = [row for row in (normalize(dataset, item) for item in raw.get(spec["key"], [])) if row]
    return raw.get("UpdateTime"), rows


def download(dataset):
    request = urllib.request.Request(f"{BASE_URL}/{DATASETS[dataset]['file']}",
                                     headers={"User-Agent": "travel-quote-demo/1.0 (open data import)"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def row_hash(row):
    return hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def save(dataset, source_time, rows):
    """和資料庫比對：內容沒變的不寫，官方已經沒有的標記下架（不刪除，保留紀錄）。"""
    table = DATASETS[dataset]["table"]
    stats = {"total": len(rows), "inserted": 0, "updated": 0, "unchanged": 0, "removed": 0}
    with connect() as conn:
        existing = {r["id"]: r["hash"] for r in conn.execute(f"SELECT id, hash FROM {table} WHERE active").fetchall()}
        seen = set()
        for row in rows:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            digest = row_hash(row)
            if existing.get(row["id"]) == digest:
                stats["unchanged"] += 1
                continue
            stats["inserted" if row["id"] not in existing else "updated"] += 1
            conn.execute(
                f"""INSERT INTO {table} (id, data, city, name, hash, active, updated_at) VALUES (%s, %s, %s, %s, %s, true, now())
                    ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, city = EXCLUDED.city, name = EXCLUDED.name,
                    hash = EXCLUDED.hash, active = true, updated_at = now()""",
                (row["id"], json.dumps(row, ensure_ascii=False), row["city"], row["name"], digest),
            )
        gone = [key for key in existing if key not in seen]
        if gone:
            conn.execute(f"UPDATE {table} SET active = false, updated_at = now() WHERE id = ANY(%s)", (gone,))
        stats["removed"] = len(gone)
    return stats


def run_import(dataset, data=None, trigger="手動"):
    """匯入一個資料集；data 不給就從官方網站下載。同時間只跑一個。"""
    if not _lock.acquire(blocking=False):
        return {"status": "busy"}
    run_id = query("INSERT INTO od_imports (dataset, trigger) VALUES (%s, %s) RETURNING id", (dataset, trigger))[0]["id"]
    try:
        source_time, rows = parse(dataset, data if data is not None else download(dataset))
        stats = save(dataset, source_time, rows)
        query(
            """UPDATE od_imports SET status = '完成', finished_at = now(), source_time = %s, total = %s, inserted = %s,
               updated = %s, unchanged = %s, removed = %s WHERE id = %s RETURNING id""",
            (source_time, stats["total"], stats["inserted"], stats["updated"], stats["unchanged"], stats["removed"], run_id),
        )
        return {"status": "完成", "id": run_id, **stats}
    except Exception as error:  # 下載或解析失敗：記錄原因，舊資料保留
        query("UPDATE od_imports SET status = '失敗', finished_at = now(), error = %s WHERE id = %s RETURNING id",
              (f"{type(error).__name__}: {error}"[:500], run_id))
        return {"status": "失敗", "id": run_id, "error": str(error)[:200]}
    finally:
        _lock.release()


def import_all_background(trigger):
    def work():
        for dataset in DATASETS:
            run_import(dataset, trigger=trigger)
    threading.Thread(target=work, daemon=True).start()


def bootstrap():
    """第一次啟動（資料庫還沒有開放資料）就在背景匯入一次，不擋住網站啟動。"""
    if os.environ.get("OPENDATA_AUTO_IMPORT", "1") != "1":
        return
    if not query("SELECT 1 AS x FROM od_attractions LIMIT 1"):
        import_all_background("首次啟動")


# ---------- 查詢 ----------

def _public(row, dataset):
    data = row["data"]
    labels = ATTRACTION_CLASSES if dataset == "attractions" else HOTEL_CLASSES
    data["class_names"] = [labels.get(c, "其他") for c in data.get("classes", [])]
    return data


def cities():
    attractions, hotels = DATASETS["attractions"]["table"], DATASETS["hotels"]["table"]
    rows = query(
        f"""SELECT city, sum(a) AS attractions, sum(h) AS hotels FROM (
             SELECT city, 1 AS a, 0 AS h FROM {attractions} WHERE active
             UNION ALL SELECT city, 0, 1 FROM {hotels} WHERE active) t
           WHERE city <> '' GROUP BY city ORDER BY sum(a) + sum(h) DESC"""
    )
    return [{"city": r["city"], "attractions": int(r["attractions"]), "hotels": int(r["hotels"])} for r in rows]


def search(dataset, city=None, keyword=None, max_price=None, with_image=False, limit=12, offset=0):
    table = DATASETS[dataset]["table"]
    where, params = ["active"], []
    if city:
        where.append("city = %s")
        params.append(city)
    if keyword:
        where.append("(name ILIKE %s OR data->>'description' ILIKE %s OR data->>'town' ILIKE %s)")
        params += [f"%{keyword}%"] * 3
    if max_price and dataset == "hotels":
        where.append("(data->>'lowest_price')::int <= %s")
        params.append(max_price)
    if with_image:
        where.append("jsonb_array_length(data->'images') > 0")
    total = query(f"SELECT count(*) AS n FROM {table} WHERE {' AND '.join(where)}", tuple(params))[0]["n"]
    # 有照片、有介紹的排前面，同分用名稱排序（結果固定，方便測試與分頁）
    rows = query(
        f"""SELECT data FROM {table} WHERE {' AND '.join(where)}
            ORDER BY jsonb_array_length(data->'images') > 0 DESC, length(data->>'description') > 30 DESC, name
            LIMIT %s OFFSET %s""",
        (*params, limit, offset),
    )
    return {"total": total, "items": [_public(r, dataset) for r in rows], "source": SOURCE, "license": LICENSE}


def get(dataset, item_id):
    rows = query(f"SELECT data FROM {DATASETS[dataset]['table']} WHERE id = %s AND active", (item_id,))
    return _public(rows[0], dataset) if rows else None


def imports(limit=20):
    rows = query("SELECT * FROM od_imports ORDER BY id DESC LIMIT %s", (limit,))
    for row in rows:
        for key in ("started_at", "finished_at"):
            row[key] = row[key].isoformat() if isinstance(row[key], datetime) else row[key]
    return rows
