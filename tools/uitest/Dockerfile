# 瀏覽器自動測試用的映像檔：裝好 Chromium、中文字型與 Playwright，測試時不用每次重新下載
FROM python:3.11-slim
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends chromium fonts-noto-cjk && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --default-timeout=120 playwright==1.47.0
ENV CHROME=/usr/bin/chromium
