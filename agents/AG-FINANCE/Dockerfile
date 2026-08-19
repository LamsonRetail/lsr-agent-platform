# Agent chạy độc lập trong container riêng.
FROM python:3.11-slim
WORKDIR /agent
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY consumer.py .
COPY data_hub/ ./data_hub/
COPY meeting/ ./meeting/
COPY shared/ ./shared/
ENV LSR_PLATFORM_URL=https://platform.34-126-154-135.sslip.io \
    LSR_AGENT_ID=AG-FINANCE \
    DRY_RUN=true
CMD ["python", "consumer.py"]
