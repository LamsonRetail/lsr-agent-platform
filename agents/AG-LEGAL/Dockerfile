# AG-LEGAL — consumer (chat) + sync worker trong cùng image.
FROM python:3.12-slim
WORKDIR /agent
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY consumer.py sync_worker.py ./
COPY legalkb ./legalkb
CMD ["python", "consumer.py"]
