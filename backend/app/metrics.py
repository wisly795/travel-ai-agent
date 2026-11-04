"""監控指標：給 Prometheus 定期來抓（/metrics），Grafana 畫成圖、超過門檻發告警。

兩種指標：
- 請求類（每次請求即時累加）：請求數、錯誤數、回應時間
- 營運類（Prometheus 來抓時才查資料庫）：今日 AI 次數與花費、ERP 同步失敗、待核准採購、最新評測分數
"""
import os
import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily, REGISTRY

from .db import query

METRICS_TOKEN = os.environ.get("METRICS_TOKEN", "")

REQUESTS = Counter("travel_http_requests_total", "HTTP 請求數", ["method", "route", "status"])
LATENCY = Histogram("travel_http_request_seconds", "HTTP 回應時間（秒）", ["route"],
                    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60))


def route_of(request):
    """用路由樣板（/api/quotes/{quote_id}）當標籤，不用實際網址，避免標籤數量爆炸。"""
    route = request.scope.get("route")
    return getattr(route, "path", None) or "其他"


async def middleware(request, call_next):
    start = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = route_of(request)
        if route != "/metrics":
            REQUESTS.labels(request.method, route, str(status)).inc()
            LATENCY.labels(route).observe(time.perf_counter() - start)


class BusinessCollector:
    def collect(self):
        def gauge(name, doc, value):
            g = GaugeMetricFamily(name, doc)
            g.add_metric([], float(value or 0))
            return g

        try:
            today = query(
                """
                SELECT count(*) AS turns, coalesce(sum(cost_usd), 0) AS cost
                FROM ai_turns
                WHERE created_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Taipei') AT TIME ZONE 'Asia/Taipei'
                """
            )[0]
            erp_failed = query("SELECT count(*) AS n FROM erp_syncs WHERE status = '失敗'")[0]["n"]
            pending = query("SELECT count(*) AS n FROM purchase_orders WHERE status = '待核准'")[0]["n"]
            handoffs = query("SELECT count(*) AS n FROM handoffs WHERE status = '待處理'")[0]["n"]
            latest = query("SELECT passed, total FROM eval_runs WHERE status = '完成' ORDER BY id DESC LIMIT 1")
        except Exception:
            yield gauge("travel_db_up", "資料庫是否可查詢（1＝正常）", 0)
            return
        from . import agent
        yield gauge("travel_db_up", "資料庫是否可查詢（1＝正常）", 1)
        yield gauge("travel_ai_turns_today", "今日 AI 對話次數", today["turns"])
        yield gauge("travel_ai_cost_today_usd", "今日 AI 花費（美元）", today["cost"])
        yield gauge("travel_ai_cost_limit_usd", "每日 AI 花費上限（美元）", agent.DAILY_COST_LIMIT_USD)
        yield gauge("travel_ai_turn_limit", "每日 AI 對話次數上限", agent.DAILY_CHAT_LIMIT)
        yield gauge("travel_erp_sync_failed", "ERP 同步失敗、等待重送的報價數", erp_failed)
        yield gauge("travel_purchase_orders_pending", "等待核准的採購單數", pending)
        yield gauge("travel_handoffs_open", "待處理的轉接單數", handoffs)
        if latest and latest[0]["total"]:
            yield gauge("travel_eval_pass_ratio", "最新一次 AI 評測通過比例", latest[0]["passed"] / latest[0]["total"])


REGISTRY.register(BusinessCollector())


def render():
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
