# Agent chạy độc lập trong container riêng — chỉ cần stdlib.
FROM python:3.11-slim
WORKDIR /agent
COPY consumer.py .
ENV LSR_PLATFORM_URL=https://platform.34-126-154-135.sslip.io \
    LSR_AGENT_ID=AG-MINH-ANH \
    DRY_RUN=true
CMD ["python", "consumer.py"]
