@echo off
chcp 65001 >nul
cd /d "%~dp0"
docker compose -p travelai down
echo 已停止。資料會保留，下次執行 Start.bat 會接著使用。
pause
