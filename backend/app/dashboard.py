"""營運儀表板：近 30 天的關鍵數字，以及每日趨勢（以台灣日期分組）。"""
from .db import query

TAIPEI_DAY = "(({col}) AT TIME ZONE 'Asia/Taipei')::date"


def summary(days):
    since = f"now() - interval '{int(days)} days'"
    row = query(f"""
        SELECT
            (SELECT count(*) FROM quotes WHERE created_at >= {since}) AS quotes,
            (SELECT count(*) FROM quotes WHERE created_at >= {since} AND source = 'ai') AS ai_quotes,
            (SELECT count(DISTINCT e.quote_id) FROM quote_events e
              WHERE e.to_status = '成交' AND e.created_at >= {since}) AS deals,
            (SELECT coalesce(sum(q.total_price), 0) FROM quote_events e JOIN quotes q ON q.id = e.quote_id
              WHERE e.to_status = '成交' AND e.created_at >= {since}) AS deal_amount,
            (SELECT count(*) FROM ai_turns WHERE created_at >= {since}) AS ai_turns,
            (SELECT coalesce(sum(cost_usd), 0) FROM ai_turns WHERE created_at >= {since}) AS ai_cost_usd,
            (SELECT count(*) FROM purchase_orders WHERE status = '待核准') AS pending_approvals,
            (SELECT count(*) FROM erp_syncs WHERE status = '失敗') AS erp_failed,
            (SELECT count(*) FROM handoffs WHERE status = '待處理') AS open_handoffs
    """)[0]
    row["conversion_rate"] = round(row["deals"] / row["quotes"], 3) if row["quotes"] else 0
    row["ai_cost_usd"] = float(row["ai_cost_usd"])
    return row


def daily(days):
    """每天一列，沒有資料的日子補 0，圖表才不會缺日期。"""
    rows = query(f"""
        WITH days AS (
            SELECT generate_series(
                (now() AT TIME ZONE 'Asia/Taipei')::date - {int(days) - 1},
                (now() AT TIME ZONE 'Asia/Taipei')::date, interval '1 day')::date AS day
        ),
        q AS (SELECT {TAIPEI_DAY.format(col='created_at')} AS day, count(*) AS n FROM quotes GROUP BY 1),
        d AS (SELECT {TAIPEI_DAY.format(col='e.created_at')} AS day, count(*) AS n, sum(qt.total_price) AS amount
              FROM quote_events e JOIN quotes qt ON qt.id = e.quote_id WHERE e.to_status = '成交' GROUP BY 1),
        a AS (SELECT {TAIPEI_DAY.format(col='created_at')} AS day, count(*) AS n, sum(cost_usd) AS cost
              FROM ai_turns GROUP BY 1)
        SELECT days.day, coalesce(q.n, 0) AS quotes, coalesce(d.n, 0) AS deals,
               coalesce(d.amount, 0) AS deal_amount, coalesce(a.n, 0) AS ai_turns,
               coalesce(a.cost, 0) AS ai_cost_usd
        FROM days LEFT JOIN q USING (day) LEFT JOIN d USING (day) LEFT JOIN a USING (day)
        ORDER BY days.day
    """)
    for row in rows:
        row["day"] = row["day"].isoformat()
        row["ai_cost_usd"] = float(row["ai_cost_usd"])
    return rows


def top_packages(days, limit=5):
    return query(f"""
        SELECT p.name, count(*) AS quotes,
               count(*) FILTER (WHERE q.status = '成交') AS deals
        FROM quotes q JOIN packages p ON p.id = q.package_id
        WHERE q.created_at >= now() - interval '{int(days)} days'
        GROUP BY p.name ORDER BY quotes DESC, p.name LIMIT %s
    """, (limit,))


def sources(days):
    return query(f"""
        SELECT source, count(*) AS quotes FROM quotes
        WHERE created_at >= now() - interval '{int(days)} days'
        GROUP BY source ORDER BY source DESC
    """)


def latest_eval():
    rows = query("SELECT passed, total, finished_at, model FROM eval_runs WHERE status = '完成' ORDER BY id DESC LIMIT 1")
    return rows[0] if rows else None


def overview(days=14):
    return {
        "days": days,
        "eval": latest_eval(),
        "summary": summary(30),
        "daily": daily(days),
        "top_packages": top_packages(30),
        "sources": sources(30),
    }
