# Agent chạy trong container riêng — chỉ cần stdlib (+ client BigQuery/Lark khi bật ingest thật).
FROM python:3.11-slim
WORKDIR /agent
COPY consumer.py .
COPY ingest/ ingest/
CMD ["python", "consumer.py"]
