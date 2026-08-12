# Data Support (AG-DATA-SUPPORT)

Agent của **team Data**: tổng hợp dữ liệu chung (BigQuery + Lark Base) vào một kho
tri thức ai cũng hỏi được qua chat, và tự dựng biên bản họp từ Lark Meeting.

> Thư mục này là **toàn bộ phạm vi được phép sửa** cho agent này (theo
> [CONTRIBUTING.md](../../CONTRIBUTING.md) của platform) — không đụng gì khác trong repo.

Thứ tự làm việc (gate của platform tự nhắc nếu bỏ qua):
1. Đã điền **USECASE.md** → 2. Đã điền **TESTCASES.md** (+ `tests.jsonl`) → 3. Code (`consumer.py`, `ingest/`)

## Chạy nhanh

> Các lệnh `scripts/...` dưới đây chạy từ **gốc repo** (`lsr-agent-platform/`); lệnh
> `docker compose` chạy sau khi đã `cd agents/AG-DATA-SUPPORT`.

```bash
# đăng ký agent (1 lần, từ gốc repo) — nhận LSR_AGENT_TOKEN, lưu vào .env.lsr (gitignored)
python3 scripts/lsr_adopt.py --enroll-token <hỏi admin> --id AG-DATA-SUPPORT \
  --name "Data Support" --owner anhnt1@hapas.vn --squad SQ-DATA

# chạy agent (Docker — giống môi trường thật)
cd agents/AG-DATA-SUPPORT && cp .env.example .env && vi .env && docker compose up
# hoặc chạy trực tiếp: LSR_AGENT_TOKEN=... python3 consumer.py

# test tự động theo tests.jsonl (terminal khác, từ gốc repo)
bash scripts/agent-test.sh AG-DATA-SUPPORT

# chat tay 1 câu (từ gốc repo)
bash scripts/agent-chat.sh AG-DATA-SUPPORT "câu hỏi thử"
```

## Đồng bộ dữ liệu (Data Hub)

Trước khi có dữ liệu thật để trả lời, Data lead cần điền danh sách bảng vào:
- `ingest/bigquery_sync.py` → biến `SOURCES` (bảng + query tóm tắt).
- `ingest/lark_base_sync.py` → biến `SOURCES` (app_token + table_id).

Chạy tay để test: `LSR_AGENT_TOKEN=... python3 ingest/bigquery_sync.py`. Khi golive,
2 job này chạy theo `schedule:` đã khai trong `lsr-agent.yaml`.

## Biên bản họp (Lark Meeting)

1. Add bot **Data Support** vào nhóm họp Lark của team Data.
2. Recording/transcript vào nhóm → agent trả lời bản nháp biên bản.
3. Chủ trì gõ **"chốt"** → agent tạo task Lark cho từng action item + lưu biên bản vào
   kho tri thức chung (tra lại được bằng chat sau này).

`DRY_RUN=true` mặc định: chỉ log, chưa tạo task Lark thật. Đổi `DRY_RUN=false` khi golive.

## Console của agent

**https://app.34-126-154-135.sslip.io/agent/AG-DATA-SUPPORT** — chat thử, jobs, traces,
chi phí, brain riêng, version. KHÔNG cần tài khoản Vercel/Supabase: console nằm sẵn
trong platform, không phải deploy web riêng.

## Kênh vào (admin gán 1 dòng ở Console → Ingress)

| Kênh | Cần gì |
|---|---|
| Web chat | có sẵn, không cần gán — ai trong công ty cũng vào chat thử được |
| Lark | channel=lark, chat_id nhóm Data squad |

## Golive checklist (rút gọn — chi tiết xem [GOLIVE_CHECKLIST.md](../../GOLIVE_CHECKLIST.md))

1. Owner đăng nhập subscription RIÊNG: `claude setup-token`.
2. Data lead xác nhận danh sách bảng BigQuery/Lark Base cho `ingest/`.
3. Add bot vào nhóm Lark Data squad, bật Event Subscription.
4. Pass `bash scripts/agent-test.sh AG-DATA-SUPPORT` (từ `tests.jsonl`).
5. Nhờ admin chuyển `status=active`.
