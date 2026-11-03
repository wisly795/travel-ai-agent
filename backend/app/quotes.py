"""查行程、算報價、建立報價。網頁 API 和 AI 工具共用這裡，確保算法只有一份。"""
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import automation
from .db import connect, query

TAIPEI = ZoneInfo("Asia/Taipei")
MAX_DAYS_AHEAD = 365


class QuoteError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def today():
    """以台灣時間為準的今天，避免伺服器時區造成日期差一天。"""
    return datetime.now(TAIPEI).date()


def days_until(departure_date):
    return (departure_date - today()).days


def check_departure(departure_date):
    """出發日期必須是明天以後、一年以內。沒有填就跳過（舊報價沒有出發日期）。"""
    if departure_date is None:
        return None
    days = days_until(departure_date)
    if days < 1:
        raise QuoteError(400, "出發日期必須是明天以後")
    if days > MAX_DAYS_AHEAD:
        raise QuoteError(400, "只能報價一年內出發的行程")
    return departure_date


def calculate_quote(price_per_person, price_per_night, days, people):
    rooms = math.ceil(people / 2)
    nights = days - 1
    total = price_per_person * people + price_per_night * rooms * nights
    return rooms, nights, total


# 與 data/policies/01_取消與退費規定.md 第3條一致：(出發前至少幾天, 扣除比例 %)
REFUND_RULES = [(31, 5), (21, 10), (8, 30), (2, 50), (1, 70), (0, 100)]


def calculate_refund(total_price, days_before=None, departure_date=None):
    """給天數或出發日期其中一個；給出發日期時，用今天（台灣時間）算還有幾天。"""
    if days_before is None:
        if departure_date is None:
            raise QuoteError(400, "請提供距離出發的天數或出發日期")
        days_before = max(days_until(departure_date), 0)
    deduct_percent = next(percent for days, percent in REFUND_RULES if days_before >= days)
    deduction = total_price * deduct_percent // 100
    result = {
        "total_price": total_price,
        "days_before_departure": days_before,
        "deduct_percent": deduct_percent,
        "deduction": deduction,
        "refund": total_price - deduction,
        "source": "取消與退費規定 第3條",
    }
    if departure_date is not None:
        result.update({"departure_date": departure_date.isoformat(), "today": today().isoformat()})
    return result


def list_destinations():
    rows = query("SELECT DISTINCT destination FROM packages ORDER BY destination")
    return [row["destination"] for row in rows]


def search_packages(destination=None, max_price=None, people=1):
    sql = """
        SELECT id, name, destination, days, price_per_person, seats_left, description
        FROM packages
        WHERE seats_left >= %s
    """
    params = [people]
    if destination:
        sql += " AND destination = %s"
        params.append(destination)
    if max_price:
        sql += " AND price_per_person <= %s"
        params.append(max_price)
    return query(sql + " ORDER BY price_per_person", params)


def list_hotels(destination=None):
    sql = "SELECT id, name, destination, room_type, price_per_night FROM hotels"
    params = []
    if destination:
        sql += " WHERE destination = %s"
        params.append(destination)
    return query(sql + " ORDER BY price_per_night", params)


def _load_checked(conn, package_id, hotel_id, people):
    package = conn.execute("SELECT * FROM packages WHERE id = %s", (package_id,)).fetchone()
    hotel = conn.execute("SELECT * FROM hotels WHERE id = %s", (hotel_id,)).fetchone()
    if not package or not hotel:
        raise QuoteError(404, "找不到行程或飯店")
    if package["destination"] != hotel["destination"]:
        raise QuoteError(400, "行程與飯店的目的地不同")
    if package["seats_left"] < people:
        raise QuoteError(400, "剩餘名額不足")
    return package, hotel


def _schedule(package, departure_date):
    """有出發日期時，算出回程日與距離出發還有幾天。"""
    if departure_date is None:
        return {"departure_date": None}
    return {
        "departure_date": departure_date.isoformat(),
        "return_date": (departure_date + timedelta(days=package["days"] - 1)).isoformat(),
        "days_until_departure": days_until(departure_date),
    }


def preview_quote(package_id, hotel_id, people, departure_date=None):
    """只計算不存檔，讓 AI 先把明細給客人確認。"""
    check_departure(departure_date)
    with connect() as conn:
        package, hotel = _load_checked(conn, package_id, hotel_id, people)
    rooms, nights, total = calculate_quote(
        package["price_per_person"], hotel["price_per_night"], package["days"], people,
    )
    return {
        "package": package["name"],
        "hotel": hotel["name"],
        "people": people,
        "rooms": rooms,
        "nights": nights,
        "package_fee": package["price_per_person"] * people,
        "hotel_fee": hotel["price_per_night"] * rooms * nights,
        "total_price": total,
        **_schedule(package, departure_date),
    }


# 報價狀態只能照這個方向改，例如取消後不能再成交。
TRANSITIONS = {"已報價": {"成交", "取消"}, "成交": {"取消"}, "取消": set()}


def change_status(quote_id, status, note="", changed_by=""):
    with connect() as conn:
        row = conn.execute("SELECT status FROM quotes WHERE id = %s FOR UPDATE", (quote_id,)).fetchone()
        if not row:
            raise QuoteError(404, "找不到報價")
        if status not in TRANSITIONS.get(row["status"], set()):
            raise QuoteError(400, f"報價目前是「{row['status']}」，不能改成「{status}」")
        conn.execute("UPDATE quotes SET status = %s WHERE id = %s", (status, quote_id))
        conn.execute(
            "INSERT INTO quote_events (quote_id, from_status, to_status, note, changed_by) VALUES (%s, %s, %s, %s, %s)",
            (quote_id, row["status"], status, note, changed_by),
        )
    return {"id": quote_id, "from_status": row["status"], "status": status}


def create_quote(customer_name, package_id, hotel_id, people, source="web", departure_date=None, partner_id=None):
    check_departure(departure_date)
    with connect() as conn:
        package, hotel = _load_checked(conn, package_id, hotel_id, people)
        rooms, nights, total = calculate_quote(
            package["price_per_person"], hotel["price_per_night"], package["days"], people,
        )
        row = conn.execute(
            """
            INSERT INTO quotes (customer_name, package_id, hotel_id, people, rooms, nights, total_price, source,
                                departure_date, partner_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (customer_name, package_id, hotel_id, people, rooms, nights, total, source, departure_date, partner_id),
        ).fetchone()
    quote = {
        "id": row["id"],
        "created_at": row["created_at"],
        "customer_name": customer_name,
        "package": package["name"],
        "hotel": hotel["name"],
        "people": people,
        "rooms": rooms,
        "nights": nights,
        "total_price": total,
        **_schedule(package, departure_date),
    }
    automation.notify_n8n("new-quote", {**quote, "source": source})
    return quote
