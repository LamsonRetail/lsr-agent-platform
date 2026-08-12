# Agent chạy trong container riêng — chỉ cần stdlib (không cài thêm package).
FROM python:3.11-slim
WORKDIR /agent
COPY consumer.py knowledge.py minutes.py thailand_tools.py transcribe.py ./
COPY configs/ ./configs/
CMD ["python", "consumer.py"]
