# Sourcing (AG-SOURCING)

Thứ tự làm việc (gate tự nhắc nếu bỏ qua):
1. Điền **USECASE.md** → 2. Điền **TESTCASES.md** (+ tests.jsonl) → 3. Code (consumer.py / Claude Code)

Chạy nhanh:
```bash
# đăng ký agent (1 lần) — nhận LSR_AGENT_TOKEN, lưu vào .env.lsr (gitignored)
python3 scripts/lsr_adopt.py --enroll-token <hỏi admin> --id AG-SOURCING --name "Sourcing" --owner linhntt@hapas.vn

# chạy agent (Docker — giống môi trường thật)
cd agents/AG-SOURCING && cp .env.example .env && vi .env && docker compose up
# hoặc chạy trực tiếp: LSR_AGENT_TOKEN=... python3 consumer.py

# test tự động theo tests.jsonl (terminal khác)
bash scripts/agent-test.sh AG-SOURCING

# chat tay 1 câu
bash scripts/agent-chat.sh AG-SOURCING "câu hỏi thử"
```

## Console của agent
**https://app.34-126-154-135.sslip.io/agent/AG-SOURCING** — chat thử, jobs, traces, chi phí,
brain riêng, version. KHÔNG cần tài khoản Vercel/Supabase: console nằm sẵn trong platform.

## Kênh vào (admin gán 1 dòng ở Console → Ingress)
| Kênh | Cần gì |
|---|---|
| Web chat | có sẵn, không cần gán |
| Telegram | channel=telegram, chat_id của chat |
| Lark | channel=lark, chat_id nhóm |
