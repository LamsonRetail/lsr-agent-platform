# Platform agents (AG-OPS, AG-EVAL) — chỉ stdlib, chọn agent bằng biến AGENT_SCRIPT.
FROM python:3.11-slim
WORKDIR /app
COPY ops.py eval_agent.py ./
ENV AGENT_SCRIPT=ops.py
CMD ["sh", "-c", "python ${AGENT_SCRIPT}"]
