#!/usr/bin/env bash
# 上線前本機預演：用正式設定（不開埠號、記憶體上限、AI 上限調低）啟動一份 travelprod，前面放一個模擬正式主機的 Caddy，
# 跑全部測試＋壓力測試，同時每 2 秒記錄記憶體，最後檢查有沒有容器因為記憶體不足被砍掉。
# Git Bash：bash tools/prod_rehearsal.sh
set -uo pipefail
cd "$(dirname "$0")/.."
P=travelprod
OUT=docs/過程截圖/I6_部署預演
mkdir -p "$OUT"
rand() { openssl rand -hex 16; }
cat > prod.env <<EOF
DB_PASSWORD=$(rand)
ADMIN_PASSWORD=$(rand)
MANAGER_PASSWORD=$(rand)
SALES_PASSWORD=$(rand)
STAFF_TOKEN=$(rand)
MANAGER_TOKEN=$(rand)
ERP_API_KEY=$(rand)
AUTOMATION_TOKEN=$(rand)
PARTNER_DEMO_KEY=pk_$(rand)
METRICS_TOKEN=$(rand)
GRAFANA_PASSWORD=$(rand)
ANTHROPIC_API_KEY=
EDGE_NETWORK=rehearsal_edge
PUBLIC_URL=http://travel.localhost:8180
EOF
DC=(docker compose -p "$P" --env-file prod.env -f docker-compose.yml -f docker-compose.prod.yml)

echo "== 建立模擬的 Caddy 與共用網路"
docker network create rehearsal_edge >/dev/null 2>&1 || true
docker rm -f rehearsal-caddy >/dev/null 2>&1
MSYS_NO_PATHCONV=1 docker run -d --name rehearsal-caddy --network rehearsal_edge -p 127.0.0.1:8180:8180 \
  -v "$PWD/deploy/Caddyfile.rehearsal:/etc/caddy/Caddyfile:ro" caddy:2.8.4-alpine >/dev/null

echo "== 啟動正式設定"
"${DC[@]}" up -d --build 2>&1 | tail -n 3
echo "== 對外開放的埠號（應該只有 Caddy 的 8180）"
docker ps --filter "name=$P-" --format '{{.Names}} {{.Ports}}' | grep -E '0\.0\.0\.0|127\.0\.0\.1' || echo "travelprod 沒有任何對外埠號"

echo "== 等系統就緒"
for i in $(seq 1 90); do curl -fsS -H "Host: travel.localhost:8180" http://127.0.0.1:8180/api/health >/dev/null 2>&1 && break; sleep 2; done
curl -sS -H "Host: travel.localhost:8180" http://127.0.0.1:8180/api/health; echo
for i in $(seq 1 60); do docker logs "$P-n8n-1" 2>&1 | grep -q "published workflows" && break; sleep 2; done
for i in $(seq 1 60); do
  n=$(docker exec "$P-app-1" python -c "from app import opendata; print(sum(1 for x in opendata.imports() if x['status']=='完成'))" 2>/dev/null)
  [ "$n" = "2" ] && break; sleep 5
done

echo "== 開始記錄記憶體（每 2 秒）"
( while true; do docker stats --no-stream --format '{{.Name}},{{.MemUsage}}' | grep -E "^($P-|voldemo|rehearsal)" | sed "s/^/$(date +%T),/"; sleep 2; done ) > "$OUT/記憶體紀錄.csv" &
SAMPLER=$!

echo "== 全部測試（在正式設定、有記憶體上限的環境）"
val() { grep "^$1=" prod.env | cut -d= -f2-; }
export GRAFANA_PASSWORD=$(val GRAFANA_PASSWORD) ADMIN_PASSWORD=$(val ADMIN_PASSWORD)
docker cp tools/. "$P-app-1:/code/" >/dev/null
for t in api_test auth_test partner_test agent_test multi_agent_test procurement_test automation_test eval_test rag_eval monitor_test opendata_test crawler_test api_matrix_test; do
  out=$(docker exec -e GRAFANA_PASSWORD "$P-app-1" python "$t.py" 2>&1)
  echo "$t：$(echo "$out" | tail -n 1)"
  echo "$out" | grep -E "^FAIL|Traceback" | head -3
done
docker cp tools/mcp_test.py "$P-mcp-1:/code/" >/dev/null
echo "mcp_test：$(docker exec "$P-mcp-1" python mcp_test.py 2>&1 | tail -n 1)"

echo "== 經過 Caddy 的畫面測試（和客人走同一條路）"
docker network connect rehearsal_edge "$P-app-1" 2>/dev/null || true
MSYS_NO_PATHCONV=1 docker run --rm --network rehearsal_edge -e APP_URL=http://rehearsal-caddy:8180/ -e ADMIN_PASSWORD \
  --add-host travel.localhost:127.0.0.1 -v "$PWD/tools:/t" -v "$PWD/$OUT:/shots" travelquote-uitest \
  sh -c "python /t/ui_site_test.py 2>&1 | tail -n 2" || true

echo "== 壓力測試：經過 Caddy，模擬多人同時使用"
MSYS_NO_PATHCONV=1 docker run --rm --network rehearsal_edge -v "$PWD/tools:/t" python:3.11-slim \
  python /t/load_test.py http://rehearsal-caddy:8180 travel.localhost:8180

kill $SAMPLER 2>/dev/null
echo "== 有沒有容器因記憶體不足被砍掉（OOMKilled）"
for c in $(docker ps -a --filter "name=$P-" --format '{{.Names}}'); do
  echo "$c $(docker inspect -f '{{.State.OOMKilled}} 重啟次數={{.RestartCount}}' "$c")"
done
echo "== 記憶體尖峰（MB）"
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD/$OUT:/o" python:3.11-slim python -c "
import csv, re, collections
peak = collections.defaultdict(float); totals = collections.defaultdict(float)
def mb(v):
    n, u = re.match(r'([\d.]+)(\w+)', v).groups(); return float(n) * {'KiB': 1/1024, 'MiB': 1, 'GiB': 1024}.get(u, 1)
for t, name, usage in csv.reader(open('/o/記憶體紀錄.csv')):
    v = mb(usage.split(' / ')[0]); peak[name] = max(peak[name], v)
    if name.startswith('travelprod-'): totals[t] += v
for name, v in sorted(peak.items(), key=lambda x: -x[1]): print(f'{name:32s} {v:7.0f}')
print(f'travelprod 合計尖峰：{max(totals.values()):.0f} MB')"
