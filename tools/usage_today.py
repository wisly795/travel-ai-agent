"""今天（台灣時間）AI 用了幾次、花多少錢，和每日上限比較。在 app 容器內執行：python usage_today.py"""
from app import agent
from app.db import query

row = query(
    """SELECT count(*) AS turns, coalesce(sum(cost_usd), 0) AS cost FROM ai_turns
       WHERE created_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Taipei') AT TIME ZONE 'Asia/Taipei'"""
)[0]
print(f"今日 AI：{row['turns']} / {agent.DAILY_CHAT_LIMIT} 次，US$ {float(row['cost']):.4f} / {agent.DAILY_COST_LIMIT_USD}")
