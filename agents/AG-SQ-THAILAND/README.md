# Trợ lý Squad Thái Lan (AG-SQ-THAILAND)

Squad agent chính của **SQ-THAILAND**: (1) kho dữ liệu chung có trích dẫn nguồn ·
(2) hỏi đáp cho cả squad qua Lark / Telegram / web chat · (3) tham gia họp, dựng biên
bản, chủ trì chốt rồi mới lưu + đề xuất đầu việc.

| Tài liệu | Nội dung |
|---|---|
| [USECASE.md](USECASE.md) | Bài toán, người dùng, 3 luồng chính, ngoài phạm vi |
| [TESTCASES.md](TESTCASES.md) | Bảng case theo từng luồng + nhãn tool |
| [PLAN.md](PLAN.md) | Mục tiêu, kiến trúc, lộ trình 3 phase, việc cần core |
| [TEAM.md](TEAM.md) | **Hương/Thái đọc trước** — fork + PR, chia file, không đụng core |
| [PLOY.md](PLOY.md) | **Team Ploy đọc trước** — map kế hoạch Ploy → platform, phân công 8 người, 3 mức sửa hành vi |

## Thứ tự làm việc (gate tự nhắc nếu bỏ qua)

1. Điền **USECASE.md** → 2. **TESTCASES.md** (+ tests.jsonl) → 3. Code — ✅ đã đủ.

## Chạy nhanh

```bash
# Chat thử NGAY tại máy — không cần token/platform/admin (model bật nếu đã claude login)
cd agents/AG-SQ-THAILAND && LSR_MODEL_MODE=auto python3 chat_local.py
```

```bash
# đăng ký agent (owner làm 1 lần) — nhận LSR_AGENT_TOKEN, lưu .env.lsr (gitignored)
python3 scripts/lsr_adopt.py --enroll-token <hỏi admin> --id AG-SQ-THAILAND \
  --name "Trợ lý Squad Thái Lan" --owner thint@hapas.vn --squad SQ-THAILAND

# chạy agent (Docker — giống môi trường thật; DRY_RUN=true mặc định)
cd agents/AG-SQ-THAILAND && cp .env.example .env && vi .env && docker compose up

# test tự động theo tests.jsonl (terminal khác)
bash scripts/agent-test.sh AG-SQ-THAILAND

# chat tay 1 câu
bash scripts/agent-chat.sh AG-SQ-THAILAND "bạn làm được gì"
```

## Cấu trúc

```
agents/AG-SQ-THAILAND/
├── USECASE.md · TESTCASES.md · PLAN.md · TEAM.md
├── lsr-agent.yaml          # manifest chuẩn platform (CI kiểm)
├── system_prompt.md        # vai trò + nguyên tắc + format biên bản
├── consumer.py             # khung poll job + định tuyến 3 luồng   (Thi)
├── knowledge.py            # kho dữ liệu chung, có nguồn           (Thái)
├── minutes.py              # biên bản + gate confirm               (Hương)
├── transcribe.py           # client Whisper                        (Hương)
├── thailand_tools.py       # Ploy: 6 nhóm tool thị trường TH       (Data/Tech)
├── configs/                # 13 config key — sửa là đổi hành vi    (mỗi key 1 chủ)
├── skills/                 # skill .md — 1 người 1 file            (xem skills/README.md)
├── tests/agent_tests.yaml  # bộ test có nhãn (6 chỉ số tool)
├── tests.jsonl             # case chạy qua Chat API
└── Dockerfile · docker-compose.yml · .env.example
```

## Console của agent

**https://app.34-126-154-135.sslip.io/agent/AG-SQ-THAILAND** — chat thử, jobs, traces,
chi phí, brain riêng, version. KHÔNG cần Vercel/Supabase: console nằm sẵn trong platform.

## Kênh vào (admin gán 1 dòng ở Console → Ingress)

| Kênh | Cần gì |
|---|---|
| Web chat | có sẵn, không cần gán |
| Lark | channel=lark, chat_id nhóm squad Thái Lan |
| Telegram | channel=telegram, chat_id của chat |
