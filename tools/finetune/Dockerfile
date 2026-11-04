# 微調向量模型用的環境（只在訓練時使用，不進正式系統）
FROM python:3.11-slim
RUN pip install --no-cache-dir --default-timeout=300 \
      torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir --default-timeout=300 \
      sentence-transformers==3.3.1 transformers==4.46.3 datasets==3.1.0 accelerate==1.1.1 \
      "optimum[onnxruntime]==1.23.3" onnxruntime==1.20.1
ENV HF_HUB_DISABLE_TELEMETRY=1
WORKDIR /work
