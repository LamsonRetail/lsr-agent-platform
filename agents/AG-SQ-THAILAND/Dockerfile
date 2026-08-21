# Agent chạy trong container riêng — chỉ cần stdlib (không cài thêm package pip).
FROM python:3.11-slim

# bq.py ký JWT cho BigQuery bằng CLI `openssl`. Slim image thường đã có sẵn (kèm
# ca-certificates) nhưng khai rõ để bản build không bao giờ thiếu — thiếu là Ploy
# âm thầm trả "chưa có số" thay vì số sống, không báo lỗi.
RUN apt-get update && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /agent
COPY consumer.py knowledge.py minutes.py model.py thailand_tools.py transcribe.py bq.py ./
COPY system_prompt.md ./
COPY skills/ ./skills/
COPY configs/ ./configs/
# memory/ phải có THẬT (không chỉ là thư mục rỗng): vòng "tên chưa biết" ghi vào
# memory/nguoi-chua-biet.md, thiếu thư mục là ghi lỗi im lặng → job quét không học được tên mới.
COPY memory/ ./memory/
CMD ["python", "consumer.py"]
