"""和 n8n 自動化流程的介面：通知中心、每日報表資料、觸發 n8n 的 Webhook。"""
import json
import os
import threading
import urllib.request

from .db import query

N8N_WEBHOOK_BASE = os.environ.get("N8N_WEBHOOK_BASE", "")


def notify_n8n(event, payload):
    """有新報價時通知 n8n。另開執行緒、失敗就算了，不能讓自動化拖慢或卡住主流程。"""
    if not N8N_WEBHOOK_BASE:
        return

    def send():
        request = urllib.request.Request(
            f"{N8N_WEBHOOK_BASE}/webhook/{event}",
            data=json.dumps(payload, ensure_ascii=False, default=str).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=3).close()
        except Exception:  # noqa: BLE001 — 自動化掛掉不影響報價
            pass

    threading.Thread(target=send, daemon=True).start()


def add_notification(kind, title, body, dedupe_key=None):
    rows = query(
        """
        INSERT INTO notifications (kind, title, body, dedupe_key) VALUES (%s, %s, %s, %s)
        ON CONFLICT (dedupe_key) DO NOTHING
        RETURNING *
        """,
        (kind, title, body, dedupe_key),
    )
    return {"created": bool(rows), "notification": rows[0] if rows else None}


def list_notifications(limit=50):
    return query("SELECT * FROM notifications ORDER BY id DESC LIMIT %s", (limit,))


def mark_read(notification_id=None):
    if notification_id is None:
        query("UPDATE notifications SET is_read = true WHERE NOT is_read RETURNING id")
    else:
        query("UPDATE notifications SET is_read = true WHERE id = %s RETURNING id", (notification_id,))


def daily_report():
    """昨天（台灣時間）的報價數、成交金額、熱門行程與 AI 花費。"""
    today = "date_trunc('day', now() AT TIME ZONE 'Asia/Taipei') AT TIME ZONE 'Asia/Taipei'"

    def yesterday(column):
        return f"{column} >= {today} - interval '1 day' AND {column} < {today}"

    quotes = query(f"""
        SELECT count(*) AS quotes,
               count(*) FILTER (WHERE source = 'ai') AS ai_quotes,
               count(*) FILTER (WHERE status = '成交') AS deals,
               coalesce(sum(total_price) FILTER (WHERE status = '成交'), 0) AS deal_amount
        FROM quotes WHERE {yesterday('created_at')}
    """)[0]
    top = query(f"""
        SELECT p.name, count(*) AS n FROM quotes q JOIN packages p ON p.id = q.package_id
        WHERE {yesterday('q.created_at')}
        GROUP BY p.name ORDER BY n DESC, p.name LIMIT 3
    """)
    ai = query(f"SELECT count(*) AS turns, coalesce(sum(cost_usd), 0) AS cost FROM ai_turns WHERE {yesterday('created_at')}")[0]
    date = query("SELECT to_char((now() AT TIME ZONE 'Asia/Taipei')::date - 1, 'YYYY-MM-DD') AS d")[0]["d"]
    return {
        "date": date,
        **quotes,
        "top_packages": [f"{row['name']}（{row['n']} 張）" for row in top],
        "ai_turns": ai["turns"],
        "ai_cost_usd": float(ai["cost"]),
    }
