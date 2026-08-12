# Agent gọi model qua Claude Agent SDK (claude_agent_sdk) — SDK này cần Node.js
# + CLI @anthropic-ai/claude-code cài sẵn, và dùng auth subscription của OWNER
# (mount ~/.claude từ máy đã `claude login`/`claude setup-token` — xem README).
FROM node:20-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code
WORKDIR /agent
COPY consumer.py .
RUN pip3 install --no-cache-dir --break-system-packages claude-agent-sdk requests
ENV LSR_PLATFORM_URL=https://platform.34-126-154-135.sslip.io \
    LSR_AGENT_ID=AG-HARRY \
    DRY_RUN=true
CMD ["python3", "consumer.py"]
