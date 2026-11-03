FROM python:3.11-slim
WORKDIR /code
RUN pip install --no-cache-dir mcp==1.30.0
COPY mcp/server.py /code/server.py
EXPOSE 8000
CMD ["python", "server.py", "http"]
