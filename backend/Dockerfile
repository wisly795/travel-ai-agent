FROM python:3.11-slim
WORKDIR /code
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 建置時就下載向量模型，安裝後不用連網也能用 RAG
ENV MODEL_DIR=/models HF_HUB_DISABLE_TELEMETRY=1
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2', cache_dir='/models')"
COPY backend/app /code/app
COPY frontend /code/frontend
COPY data/policies /code/data/policies
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
