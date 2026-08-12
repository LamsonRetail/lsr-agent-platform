# Mother's Day (AG-MOTHERS-DAY)

Thứ tự làm việc (gate tự nhắc nếu bỏ qua):
1. Điền **USECASE.md** → 2. Điền **TESTCASES.md** (+ tests.jsonl) → 3. Code (consumer.py / Claude Code)

Chạy nhanh:
```bash
# đăng ký agent (1 lần) — nhận LSR_AGENT_TOKEN, lưu vào .env.lsr (gitignored)
python3 scripts/lsr_adopt.py --enroll-token <hỏi admin> --id AG-MOTHERS-DAY --name "Mother's Day" --owner linhntt@hapas.vn

# chạy agent (Docker — giống môi trường thật)
cd agents/AG-MOTHERS-DAY && cp .env.example .env && vi .env && docker compose up
# hoặc chạy trực tiếp: LSR_AGENT_TOKEN=... python3 consumer.py

# test tự động theo tests.jsonl (terminal khác)
bash scripts/agent-test.sh AG-MOTHERS-DAY

# chat tay 1 câu
bash scripts/agent-chat.sh AG-MOTHERS-DAY "câu hỏi thử"
```

## Console của agent
**https://app.34-126-154-135.sslip.io/agent/AG-MOTHERS-DAY** — chat thử, jobs, traces, chi phí,
brain riêng, version. KHÔNG cần tài khoản Vercel/Supabase: console nằm sẵn trong platform.

## Kênh vào (admin gán 1 dòng ở Console → Ingress)
| Kênh | Cần gì |
|---|---|
| Web chat | có sẵn, không cần gán |
| Telegram | channel=telegram, chat_id của chat |
| Lark | channel=lark, chat_id nhóm |

## Liên kết Lark
App dùng: **Nihao Sourcing** (`cli_aaf6ce7c8d38deed`) — khai báo ở `lsr-agent.yaml > lark.bot`.
`app_secret` **chỉ** nằm trong `.env` local (gitignored), không bao giờ vào repo.

```bash
cd agents/AG-MOTHERS-DAY
cp .env.example .env && vi .env      # điền LARK_APP_SECRET
python3 lark_link.py                 # verify credential + liệt kê nhóm bot đang ở
python3 lark_link.py --resolve linhntt@hapas.vn      # email -> open_id
DRY_RUN=false python3 lark_link.py --send oc_xxx "ping"   # gửi thử (cân nhắc: gửi thật vào nhóm)
```

Còn việc cần người làm (không tự động được):

**a) Em tự làm:**
1. **Add bot vào nhóm Lark "Mother's Day"** → chạy lại `lark_link.py` để lấy `chat_id`,
   điền vào `lsr-agent.yaml > lark.bot.chat_ids` (hiện rỗng vì chưa có nhóm).
2. **Bật Event Subscription** `im.message.receive_v1` trong Lark Developer Console
   + scope `im:message`, `im:message:send_as_bot`, `im:chat:readonly`, `contact:user.id:readonly`.

**b) Cần maintainer (core, ngoài phạm vi PR agent)** — theo cơ chế đa-app Lark ở
`docs/TESTCASES.md §14`, app phụ muốn nhận/trả tin cần 4 thứ:

| # | Việc | Ở đâu |
|---|---|---|
| 1 | `NIHAO_LARK_APP_ID=cli_aaf6ce7c8d38deed` + `NIHAO_LARK_APP_SECRET=...` | `/opt/lsr-platform/.env` trên VM |
| 2 | Ghép app vào `LARK_EXTRA_APPS` (JSON app_id→secret) của `platform_api` | `infra/lsr-platform/docker-compose.yml` |
| 3 | Container long-connection cho app này (mẫu: `gateway_sawadee`) | `infra/lsr-platform/docker-compose.yml` |
| 4 | `routing_binding` với `app_id=cli_aaf6ce7c8d38deed` + chat_id nhóm → `AG-MOTHERS-DAY` | Console → Ingress |

(1)–(3) **dùng chung** với `AG-SOURCING` vì cùng một app Lark — nếu AG-SOURCING đã cấu hình rồi
thì campaign này chỉ cần thêm `routing_binding` ở bước (4).

Thiếu (1)/(2) thì platform trả lỗi rõ *"app … chưa có secret trên VM"* và **không** gửi bằng bot
sai (TH.3b). Lúc chạy thật consumer.py **không cần** app_secret: job Lark vào qua `/v1/self/jobs`
(kèm `app_id` nguồn), trả lời qua `/v1/self/jobs/{id}/reply` → platform tự chọn **đúng bot đã
nhận tin** (TH.2b).
