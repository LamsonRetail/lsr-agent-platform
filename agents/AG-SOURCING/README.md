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

## Liên kết Lark
App dùng: **Nihao Sourcing** (`cli_aaf6ce7c8d38deed`) — khai báo ở `lsr-agent.yaml > lark.bot`.
`app_secret` **chỉ** nằm trong `.env` local (gitignored), không bao giờ vào repo.

Bot đã ở trong 2 nhóm việc (đã điền `chat_ids`):
| chat_id | Nhóm |
|---|---|
| `oc_96886011764769b30cb8fc541944df91` | TEAM S (Supplier & Sampling Development) |
| `oc_d3079f5e1bf44f8605a4f222cce4f86c` | SOURCING MM |

```bash
cd agents/AG-SOURCING
cp .env.example .env && vi .env      # điền LARK_APP_SECRET
python3 lark_link.py                 # verify credential + liệt kê nhóm bot đang ở
python3 lark_link.py --resolve linhntt@hapas.vn      # email -> open_id
DRY_RUN=false python3 lark_link.py --send oc_xxx "ping"   # gửi thử (cân nhắc: gửi thật vào nhóm)
```

Còn việc cần người làm (không tự động được):

**a) Em tự làm — trong Lark Developer Console:** bật Event Subscription `im.message.receive_v1`
+ scope `im:message`, `im:message:send_as_bot`, `im:chat:readonly`, `contact:user.id:readonly`.

**b) Phần core — maintainer (@ntranthi) đã làm xong** (issue #13, commit `9ba8495` + `da1cdf8`):

| # | Việc | Ở đâu | Trạng thái |
|---|---|---|---|
| 1 | `SOURCING_LARK_APP_ID/SECRET` | `/opt/lsr-platform/.env` trên VM | ✅ (nhập bằng `scripts/add-lark-app.sh`) |
| 2 | Ghép app vào `LARK_EXTRA_APPS` của `platform_api` | `infra/lsr-platform/docker-compose.yml:190` | ✅ |
| 3 | Container long-connection `event_gateway_sourcing` | `infra/lsr-platform/docker-compose.yml:81` | ✅ |
| 4 | `routing_binding` app_id + 2 chat_id → `AG-SOURCING` | Console → Ingress | ✅ (nhóm Sharing giữ chưa bật) |

Verify lại bất cứ lúc nào — endpoint này từng trả `503 "Lark chưa cấu hình"` khi chưa có secret:
```bash
curl -s -H "Authorization: Bearer $LSR_AGENT_TOKEN" \
  "$LSR_PLATFORM_URL/v1/lark/chats?app_id=cli_aaf6ce7c8d38deed"   # 200 + 3 nhóm = core OK
```

Nếu secret bị thiếu, platform trả lỗi rõ *"app … chưa có secret trên VM"* và **không** gửi bằng bot
sai (TH.3b) — nên không có rủi ro trả lời lẫn bot.

Lúc chạy thật consumer.py **không cần** app_secret: job Lark vào qua `/v1/self/jobs` (kèm `app_id`
nguồn), trả lời qua `/v1/self/jobs/{id}/reply` → platform tự chọn **đúng bot đã nhận tin** (TH.2b).

## Còn thiếu để golive
`GET /v1/self` → `status: registered`, nhưng `GET /v1/self/context` vẫn trả
`instruction_block: null` và `version: null` → agent **chưa có chính sách nào**, sẽ trả lời cả câu
đáng phải từ chối (TESTCASE 4 — dữ liệu dự án BST).

1. Publish version với nội dung `INSTRUCTION.md` ở Console → Version. Cần role `moderator`
   (token agent trả `403`), nên chủ agent hoặc maintainer làm.
2. Chủ agent dán setup-token của Claude subscription qua `/v1/self/deploy` (`runtime.auth:
   subscription` — không dùng api key).
3. `bash scripts/agent-test.sh AG-SOURCING`.
