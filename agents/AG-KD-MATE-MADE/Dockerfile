# Agent chạy trong container riêng.
FROM python:3.11-slim
WORKDIR /agent
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY consumer.py kd_sync.py meeting_note.py lark_docs.py transcribe.py ./
CMD ["python3", "consumer.py"]
