# AG-LEGAL — consumer (chat + kb-sync + news + gate worker) trong cùng image.
#
# Image có CLI `claude` (Node + Claude Code): router intent và S2–S5 gọi model qua
# `claude -p` theo chuẩn `runtime.auth: subscription`. Thiếu CLI thì router rơi về mặc
# định và S2–S5 chỉ trả "chưa rà soát được" — consumer in cảnh báo rõ lúc khởi động.
#
# Token KHÔNG nằm trong image và KHÔNG nằm trong .env của agent: lúc khởi động agent xin
# `POST /v1/self/model-auth/lease`, platform trả **tham chiếu** tới file secret trên VM
# (`/secrets/model/<id>.env`, mount read-only). Xem `brain.lease_model_auth()`.
# Không dùng `POST /v1/self/deploy` cho agent này: handler đó chỉ truyền một bộ env cố
# định nên mất `.env` (Lark, NotebookLM, token folder Drive) — xem SETUP.md §6.
FROM python:3.12-slim
WORKDIR /agent
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @anthropic-ai/claude-code \
 && npm cache clean --force && apt-get purge -y curl && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY consumer.py sync_worker.py seed_roles.py seed_news.py golden_run.py ./
COPY golden-cases.json ./
COPY legalkb ./legalkb
CMD ["python", "consumer.py"]
