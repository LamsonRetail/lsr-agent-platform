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

**b) Phần core** — app Lark này dùng chung với `AG-SOURCING`, nên (1)–(3) **đã xong** rồi
(maintainer @ntranthi, commit `9ba8495` + `da1cdf8`):

| # | Việc | Ở đâu | Trạng thái |
|---|---|---|---|
| 1 | `SOURCING_LARK_APP_ID/SECRET` | `/opt/lsr-platform/.env` trên VM | ✅ dùng chung |
| 2 | Ghép app vào `LARK_EXTRA_APPS` của `platform_api` | `infra/lsr-platform/docker-compose.yml:190` | ✅ dùng chung |
| 3 | Container long-connection `event_gateway_sourcing` | `infra/lsr-platform/docker-compose.yml:81` | ✅ dùng chung |
| 4 | `routing_binding` app_id + chat_id nhóm → `AG-MOTHERS-DAY` | Console → Ingress | ❌ **chờ có nhóm** |

Bước (4) chưa làm được vì nhóm Lark "Mother's Day" **chưa tồn tại** — phải tạo nhóm + add bot
trước (mục a), rồi mới bind được. Verify phần core dùng chung:
```bash
curl -s -H "Authorization: Bearer $LSR_AGENT_TOKEN" \
  "$LSR_PLATFORM_URL/v1/lark/chats?app_id=cli_aaf6ce7c8d38deed"   # 200 = core OK
```

⚠️ Routing theo **chat_id**, không theo app. Cùng một bot Nihao Sourcing sẽ phục vụ 2 agent:
nhóm TEAM S / SOURCING MM → `AG-SOURCING`, nhóm Mother's Day → `AG-MOTHERS-DAY`. Đừng bind nhóm
Mother's Day cho AG-SOURCING, vì mỗi agent có brain riêng — bind sai là trộn dữ liệu 2 dự án.

Thiếu (1)/(2) thì platform trả lỗi rõ *"app … chưa có secret trên VM"* và **không** gửi bằng bot
sai (TH.3b). Lúc chạy thật consumer.py **không cần** app_secret: job Lark vào qua `/v1/self/jobs`
(kèm `app_id` nguồn), trả lời qua `/v1/self/jobs/{id}/reply` → platform tự chọn **đúng bot đã
nhận tin** (TH.2b).

## Còn thiếu để golive
Khác với `AG-SOURCING` (đã `status: registered`), agent này **chưa được enroll** — chưa có
`LSR_AGENT_TOKEN` nên `.env` còn trống phần platform và mọi lệnh gọi `/v1/self/*` sẽ `401`.

1. Xin thêm 1 enroll token cho `AG-MOTHERS-DAY` (issue #10) → chạy `scripts/lsr_adopt.py`.
2. Tạo nhóm Lark "Mother's Day" + add bot → điền `chat_ids` → nhờ bind ingress (bước b4).
3. Publish version với nội dung `INSTRUCTION.md` (Console → Version, cần role `moderator`).
4. Chủ agent dán setup-token Claude subscription qua `/v1/self/deploy`.
5. `bash scripts/agent-test.sh AG-MOTHERS-DAY`.
