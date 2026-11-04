#!/usr/bin/env bash
# CI 自動測試：建置全部容器 → 跑全部模擬測試（假 AI，不需金鑰、不花額度）→ 畫面測試
# GitHub Actions 會執行這支；本機也可以用 Git Bash 執行：PROJECT=citest APP_PORT=8200 bash tools/ci_run.sh
set -euo pipefail
cd "$(dirname "$0")/.."
P="${PROJECT:-citest}"
APP_PORT="${APP_PORT:-8100}"

rand() { openssl rand -hex 16; }

# 1. 產生測試用 .env（隨機密碼，沒有 AI 金鑰）。已有 .env 時改用 ci.env，不動原本的設定。
ENV_FILE=.env
if [ -f .env ] && [ -z "${CI:-}" ]; then ENV_FILE=ci.env; fi
if [ "$ENV_FILE" = ci.env ] || [ ! -f .env ]; then
  cat > "$ENV_FILE" <<EOF
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
APP_PORT=${APP_PORT}
ERP_PORT=$((APP_PORT + 1))
MCP_PORT=$((APP_PORT + 2))
WEBSITE_PORT=$((APP_PORT + 3))
N8N_PORT=$((APP_PORT + 10))
MAIL_UI_PORT=$((APP_PORT + 11))
PROMETHEUS_PORT=$((APP_PORT + 12))
ALERTMANAGER_PORT=$((APP_PORT + 13))
GRAFANA_PORT=$((APP_PORT + 14))
EOF
fi
DC=(docker compose -p "$P" --env-file "$ENV_FILE")

# 2. 建置並啟動
"${DC[@]}" up -d --build
echo "等待系統就緒……"
for i in $(seq 1 90); do
  if curl -fsS "http://localhost:${APP_PORT}/api/health" >/dev/null 2>&1; then break; fi
  sleep 2
done
curl -fsS "http://localhost:${APP_PORT}/api/health" >/dev/null
# n8n 啟動時要先匯入並啟用流程，等它真的能收 Webhook 再開始測（剛啟動就測會漏通知）
N8N_PORT=$(grep '^N8N_PORT=' "$ENV_FILE" | cut -d= -f2-); N8N_PORT=${N8N_PORT:-5678}
for i in $(seq 1 90); do
  if docker logs "$P-n8n-1" 2>&1 | grep -q "published workflows"; then break; fi
  sleep 2
done
sleep 5

# 3. 後端測試（在 app 容器裡執行）
docker cp tools/. "$P-app-1:/code/"
FAILED=()
GRAFANA_PASSWORD=$(grep '^GRAFANA_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)
for t in api_test auth_test partner_test agent_test multi_agent_test procurement_test automation_test eval_test rag_eval monitor_test; do
  echo "::group::$t"
  if docker exec -e GRAFANA_PASSWORD="$GRAFANA_PASSWORD" "$P-app-1" python "$t.py"; then echo "✔ $t"; else echo "✘ $t"; FAILED+=("$t"); fi
  echo "::endgroup::"
done

# 4. MCP 測試（在 mcp 容器裡執行）
echo "::group::mcp_test"
docker cp tools/mcp_test.py "$P-mcp-1:/code/"
if docker exec "$P-mcp-1" python mcp_test.py; then echo "✔ mcp_test"; else FAILED+=("mcp_test"); fi
echo "::endgroup::"

# 5. 畫面測試（Chromium 瀏覽器，截圖放 ci-shots/）
echo "::group::ui_test"
docker build -q -t travelquote-uitest tools/uitest >/dev/null
mkdir -p ci-shots
SALES_PASSWORD=$(grep '^SALES_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)
if MSYS_NO_PATHCONV=1 docker run --rm --network "${P}_default" \
    -e APP_URL="http://$P-app-1:8000/" -e SALES_PASSWORD="$SALES_PASSWORD" \
    -v "$PWD/tools:/t" -v "$PWD/ci-shots:/shots" travelquote-uitest python /t/ui_test.py; then
  echo "✔ ui_test"
else FAILED+=("ui_test"); fi
echo "::endgroup::"

# 6. 結果
if [ "${KEEP:-}" != 1 ]; then "${DC[@]}" down -v >/dev/null 2>&1 || true; fi
[ "$ENV_FILE" = ci.env ] && rm -f ci.env
if [ ${#FAILED[@]} -gt 0 ]; then echo "失敗：${FAILED[*]}"; exit 1; fi
echo "全部測試通過"
