# 執行截圖腳本：密碼從 .env 讀進環境變數，docker 只傳變數名稱，命令列和錯誤訊息不會出現密碼
# 用法：powershell -File tools\run_shots.ps1 ui_i234_shots.py
param([Parameter(Mandatory)][string]$Script, [string[]]$ScriptArgs = @())
$proj = Split-Path $PSScriptRoot -Parent
$names = 'SALES_PASSWORD', 'MANAGER_PASSWORD', 'ADMIN_PASSWORD', 'GRAFANA_PASSWORD'
foreach ($line in Get-Content "$proj\.env" -Encoding utf8) {
    $pair = $line.Split('=', 2)
    if ($names -contains $pair[0]) { Set-Item "env:$($pair[0])" $pair[1] }
}
$envArgs = foreach ($n in $names) { '-e'; $n }
docker run --rm --network travelquote_default @envArgs `
    -v "$proj\tools:/t" -v "$proj\docs\過程截圖:/shots" travelquote-uitest python "/t/$Script" @ScriptArgs
