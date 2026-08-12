# Agent chạy độc lập trong container riêng.
# Base Python (logic agent) + Node (Claude Agent SDK gọi qua CLI `claude` bên dưới —
# xem ask_model() trong consumer.py). Không có Node/CLI/subscription vẫn chạy được,
# answer() tự fallback về luật đơn giản.
FROM python:3.11-slim
WORKDIR /agent

RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm \
    && npm install -g @anthropic-ai/claude-code \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY consumer.py system_prompt.md ./
ENV LSR_PLATFORM_URL=https://platform.34-126-154-135.sslip.io \
    LSR_AGENT_ID=AG-CUNG-UNG \
    LSR_MODEL=claude-sonnet-5 \
    DRY_RUN=true
CMD ["python", "consumer.py"]
