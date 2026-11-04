# 第一階段：用 Node 建置 React 前端（安裝的電腦不需要裝 Node）
FROM node:20.18-slim AS frontend
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm test && npm run build

# 第二階段：Python 後端，只帶建置好的前端檔案
FROM python:3.11-slim
WORKDIR /code
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 建置時就下載向量模型，安裝後不用連網也能用 RAG
ENV MODEL_DIR=/models HF_HUB_DISABLE_TELEMETRY=1
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='/models')"
COPY backend/app /code/app
COPY --from=frontend /web/dist /code/frontend
COPY data/policies /code/data/policies
# 微調過的向量模型（沒有的話只有 README，系統自動改用原始模型）
COPY models /code/models
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
