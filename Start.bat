@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==== 旅遊 AI 客服與報價系統 ====
docker info >nul 2>&1
if errorlevel 1 (
  echo 請先開啟 Docker Desktop，等它顯示 Engine running 後再執行一次。
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File setup_env.ps1
if errorlevel 1 (
  echo 建立設定檔失敗。
  pause
  exit /b 1
)
echo 建置中，第一次需要下載，約 5 到 10 分鐘，請保持網路連線……
docker compose -p travelai build
if not errorlevel 1 goto run
rem 資料夾路徑有中文時，Docker 新版建置引擎會失敗，改用相容模式逐一建置
echo 一般建置失敗（資料夾路徑含中文時會發生），改用相容模式建置……
set DOCKER_BUILDKIT=0
docker build -t travelai-app -f backend/Dockerfile .
if errorlevel 1 goto buildfail
docker build -t travelai-erp -f erp/Dockerfile .
if errorlevel 1 goto buildfail
docker build -t travelai-mcp -f mcp/Dockerfile .
if errorlevel 1 goto buildfail
docker build -t travelai-website -f website/Dockerfile .
if errorlevel 1 goto buildfail
docker build -t travelai-supplier -f supplier/Dockerfile .
if errorlevel 1 goto buildfail
set DOCKER_BUILDKIT=
:run
echo 啟動中……
docker compose -p travelai up -d
if errorlevel 1 (
  echo 啟動失敗。如果訊息提到 port is already allocated，代表 8100 等埠號被占用，請先關閉其他版本。
  pause
  exit /b 1
)
echo 等待系統就緒……
powershell -NoProfile -Command "for($i=0;$i -lt 90;$i++){try{Invoke-WebRequest -UseBasicParsing http://localhost:8100/api/health -TimeoutSec 3 | Out-Null; exit 0}catch{Start-Sleep 2}}; exit 1"
if errorlevel 1 (
  echo 系統還沒就緒，請稍後再打開 http://localhost:8100
) else (
  echo 完成！登入資訊在「登入資訊.txt」。
  start "" http://localhost:8100
)
pause
exit /b 0
:buildfail
echo 建置失敗，請確認網路連線後再執行一次。
pause
exit /b 1
