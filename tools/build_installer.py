"""打包安裝包 zip：只放系統執行需要的檔案，絕對不放 .env、登入資訊和截圖。

用法（在專案資料夾）：docker run --rm -v <專案>:/p python:3.11-slim python /p/tools/build_installer.py
"""
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dist" / f"旅遊AI客服系統_安裝包_{date.today():%Y%m%d}.zip"
# 微調模型（models/finetuned，約 113 MB）一起放進去，安裝後不用重新訓練；個人求職資料（成品規劃等）不放
INCLUDE = ["backend", "frontend", "db", "data", "erp", "mcp", "website", "supplier", "automation", "monitoring", "models", "tools",
           "docker-compose.yml", "docker-compose.prod.yml", ".env.example", "Start.bat", "Stop.bat", "setup_env.ps1",
           "README.md", ".gitignore", ".gitattributes",
           "docs/交接文件.md", "docs/MCP接入說明.md", "docs/系統規格.md", "docs/從零重建指南.md"]
NEVER = {".env", "登入資訊.txt", "ci.env"}
SKIP_DIRS = {"__pycache__", "node_modules", "dist"}

OUT.parent.mkdir(exist_ok=True)
files = []
for item in INCLUDE:
    path = ROOT / item
    files += [p for p in path.rglob("*") if p.is_file()] if path.is_dir() else [path]
files = [p for p in files if p.name not in NEVER and not SKIP_DIRS & set(p.parts) and p.suffix != ".pyc"]

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(files):
        archive.write(path, "旅遊AI客服系統/" + path.relative_to(ROOT).as_posix())

names = zipfile.ZipFile(OUT).namelist()
assert not any(Path(n).name in NEVER for n in names), "安裝包裡不能有 .env 或登入資訊"
# docker-compose.yml 裡每個要建置的 Dockerfile 都要在安裝包裡（J4-1：漏了 supplier 才發現要檢查）
import re
compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
for dockerfile in re.findall(r"dockerfile:\s*(\S+)", compose):
    assert f"旅遊AI客服系統/{dockerfile}" in names, f"安裝包少了 {dockerfile}"
print(f"{OUT.name}：{len(names)} 個檔案，{OUT.stat().st_size / 1024:.0f} KB")
