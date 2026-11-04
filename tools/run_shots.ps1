# 執行截圖腳本：密碼從 .env 讀進環境變數，docker 只傳變數名稱，命令列和錯誤訊息不會出現密碼
# 用法：powershell -File tools\run_shots.ps1 ui_i234_shots.py
param([Parameter(Mandatory)][string]$Script, [string[]]$ScriptArgs = @(), [string]$Out = "")
$proj = Split-Path $PSScriptRoot -Parent
$names = 'SALES_PASSWORD', 'MANAGER_PASSWORD', 'ADMIN_PASSWORD', 'GRAFANA_PASSWORD'
foreach ($line in Get-Content "$proj\.env" -Encoding utf8) {
    $pair = $line.Split('=', 2)
    if ($names -contains $pair[0]) { Set-Item "env:$($pair[0])" $pair[1] }
}
$envArgs = foreach ($n in $names) { '-e'; $n }
# 截圖放到 docs/過程截圖/<Out>/（不指定就用腳本自己的預設位置）
if ($Out) { New-Item -ItemType Directory -Force "$proj\docs\過程截圖\$Out" | Out-Null; $envArgs += @('-e', "OUT=/shots/$Out") }
docker run --rm --network travelquote_default @envArgs `
    -v "$proj\tools:/t" -v "$proj\docs\過程截圖:/shots" travelquote-uitest python "/t/$Script" @ScriptArgs
