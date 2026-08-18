# AG-LEGAL — consumer (chat + kb-sync + news + gate worker) trong cùng image.
#
# ⚠️ Image này KHÔNG có CLI `claude`. Router intent và S2–S5 gọi model qua `claude -p`
# (chuẩn runtime.auth: subscription), nên chạy bằng image này thì chúng degrade: S1 hỏi
# đáp vẫn hoạt động, còn S2–S5 chỉ trả "chưa rà soát được". Consumer in cảnh báo rõ lúc
# khởi động (xem brain.available()).
#
# Cách chạy đầy đủ tính năng: `POST /v1/self/deploy` — platform chạy AGENT_RUNNER_IMAGE
# đã có `claude` + CLAUDE_CODE_OAUTH_TOKEN. Muốn tự host thì thêm Node + Claude Code vào
# image này và mount ~/.claude (hoặc truyền CLAUDE_CODE_OAUTH_TOKEN).
FROM python:3.12-slim
WORKDIR /agent
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY consumer.py sync_worker.py seed_roles.py seed_news.py golden_run.py ./
COPY golden-cases.json ./
COPY legalkb ./legalkb
CMD ["python", "consumer.py"]
