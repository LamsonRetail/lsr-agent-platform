# Agent chạy trong container riêng — chỉ cần stdlib (không cài thêm package).
FROM python:3.11-slim
WORKDIR /agent
COPY consumer.py knowledge.py minutes.py transcribe.py ./
CMD ["python", "consumer.py"]
