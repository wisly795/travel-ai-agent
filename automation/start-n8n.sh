#!/bin/sh
# n8n 啟動前先匯入並啟用流程，安裝後不用手動設定。流程編號固定，重複匯入會覆蓋成最新版本。
set -e
n8n import:workflow --separate --input=/automation/workflows
for id in tqNewQuote000001 tqDailyReport001 tqPoReminder0001 tqErpRetry000001; do
  n8n publish:workflow --id="$id"
done
exec n8n start
