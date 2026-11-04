# 第一次安裝時建立 .env：密碼與權杖全部隨機產生，並把登入資訊存成文字檔
$ErrorActionPreference = 'Stop'
if (Test-Path .env) { exit 0 }
function New-Secret([int]$n) { -join ((48..57) + (97..122) | Get-Random -Count $n | ForEach-Object { [char]$_ }) }
# 帳號密碼：英文字母加數字，符合系統的密碼規則
function New-Password { (-join ((97..122) | Get-Random -Count 8 | ForEach-Object { [char]$_ })) + (Get-Random -Minimum 1000 -Maximum 9999) }
$admin = New-Password
$managerPw = New-Password
$sales = New-Password
$text = (Get-Content .env.example -Raw -Encoding UTF8)
$text = $text -replace '(?m)^DB_PASSWORD=.*$', ('DB_PASSWORD=' + (New-Secret 24))
$text = $text -replace '(?m)^ADMIN_PASSWORD=.*$', ('ADMIN_PASSWORD=' + $admin)
$text = $text -replace '(?m)^MANAGER_PASSWORD=.*$', ('MANAGER_PASSWORD=' + $managerPw)
$text = $text -replace '(?m)^SALES_PASSWORD=.*$', ('SALES_PASSWORD=' + $sales)
$text = $text -replace '(?m)^STAFF_TOKEN=.*$', ('STAFF_TOKEN=' + (New-Secret 20))
$text = $text -replace '(?m)^MANAGER_TOKEN=.*$', ('MANAGER_TOKEN=' + (New-Secret 20))
$text = $text -replace '(?m)^ERP_API_KEY=.*$', ('ERP_API_KEY=' + (New-Secret 32))
$text = $text -replace '(?m)^AUTOMATION_TOKEN=.*$', ('AUTOMATION_TOKEN=' + (New-Secret 32))
$text = $text -replace '(?m)^PARTNER_DEMO_KEY=.*$', ('PARTNER_DEMO_KEY=pk_' + (New-Secret 32))
$text = $text -replace '(?m)^METRICS_TOKEN=.*$', ('METRICS_TOKEN=' + (New-Secret 32))
$grafana = New-Password
$text = $text -replace '(?m)^GRAFANA_PASSWORD=.*$', ('GRAFANA_PASSWORD=' + $grafana)
[IO.File]::WriteAllText((Join-Path (Get-Location) '.env'), $text, (New-Object Text.UTF8Encoding $false))
$info = @"
旅遊 AI 客服與報價系統：登入資訊（只存在這台電腦，請勿外流）

網站：http://localhost:8100 → 業務後台
  業務帳號：sales      密碼：$sales
  主管帳號：manager    密碼：$managerPw（可核准大額採購單）
  管理員帳號：admin    密碼：$admin（可管理帳號與合作夥伴）

監控儀表板：http://localhost:3000（Grafana）
  帳號：admin    密碼：$grafana

第一次登入後，建議由管理員在後台「系統管理」修改密碼。

AI 客服需要 Claude API 金鑰：用記事本打開 .env，貼在 ANTHROPIC_API_KEY= 後面，存檔後再執行一次 Start.bat。
"@
[IO.File]::WriteAllText((Join-Path (Get-Location) '登入資訊.txt'), $info, (New-Object Text.UTF8Encoding $true))
Write-Host '已建立 .env 與 登入資訊.txt'
