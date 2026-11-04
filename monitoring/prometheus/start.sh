#!/bin/sh
# 把 METRICS_TOKEN 寫成檔案給 Prometheus 讀（設定檔本身不放權杖）
mkdir -p /etc/prometheus/token
printf '%s' "$METRICS_TOKEN" > /etc/prometheus/token/metrics_token
exec /bin/prometheus --config.file=/etc/prometheus/prometheus.yml \
  --storage.tsdb.path=/prometheus --storage.tsdb.retention.time=15d --web.enable-lifecycle
