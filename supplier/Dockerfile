FROM python:3.11-slim
WORKDIR /code
RUN pip install --no-cache-dir fastapi==0.111.0 uvicorn==0.29.0
COPY supplier/app.py /code/app.py
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
