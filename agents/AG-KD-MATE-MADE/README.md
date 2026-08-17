# LYLY — Trợ lý Kinh doanh MATE MADE (AG-KD-MATE-MADE)

Agent của team Kinh doanh MATE MADE trên LSR Agent Platform. **Người dùng là nhân viên
sale nội bộ, không phải khách hàng cuối.** Ba việc chính:

1. **Tra giá & chính sách** — giá lẻ/sỉ, chiết khấu, phí ship, bảo hành. Luôn kèm **link
   nguồn + kỳ dữ liệu** để sale đối chiếu trước khi báo khách. Không có căn cứ →
   _"Cái này em chưa có, anh/chị hỏi lại quản lý nhé."_
2. **Soạn tin & xử lý khách khó** — đoạn tin copy-gửi-luôn; playbook khách chê đắt / lưỡng
   lự / so sánh đối thủ, kèm câu nói mẫu.
3. **Biên bản họp** — recording → transcript → biên bản nháp (có mục **cam kết
   ai-làm-gì-khi-nào**) → **xin chủ trì chốt** → Lark Docs + task + lưu vào kho tri thức.

> **LYLY không tự duyệt** chiết khấu vượt khung, công nợ, hay thời gian giao ngoài chính
> sách — mọi ngoại lệ đẩy về quản lý kinh doanh, kể cả khi sale nói gấp.

**Giá không nằm trong prompt.** Toàn bộ số liệu nằm trong kho tri thức đã duyệt, sync hàng
ngày từ Lark → đổi giá là sửa file gốc, không phải sửa code.

Đọc trước khi sửa: [USECASE.md](USECASE.md) · [TESTCASES.md](TESTCASES.md) ·
[DATA_CHECKLIST.md](DATA_CHECKLIST.md) ← **cần nạp dữ liệu trước khi LYLY dùng được**

## Thành phần

**Hai tiến trình** (`docker compose`), không phải ba:

| File | Việc | Chạy thế nào |
|---|---|---|
| `consumer.py` | Poll job từ mọi kênh, xử lý **cả** hỏi đáp **lẫn** biên bản họp | service `agent` |
| `meeting_note.py` | Logic biên bản họp | **module**, do `consumer.py` gọi |
| `kd_sync.py` | Đồng bộ Lark Base + Drive → hàng chờ tri thức, hàng ngày 6h VN | service `kd_sync` |
| `lark_docs.py` | Client **chỉ-đọc** Lark Wiki/Docx/Base/Drive | module |
| `transcribe.py` | Client Whisper transcription server | module |

> `meeting_note.py` **không** chạy thành service riêng: chỉ được có **một** tiến trình poll
> `/v1/self/jobs`. Hai process cùng poll sẽ giành job của nhau và tin nhắn rơi ngẫu nhiên
> vào process không biết xử lý.

## Chạy nhanh

```bash
# 1) đăng ký agent (1 lần) — nhận LSR_AGENT_TOKEN
python3 scripts/lsr_adopt.py --enroll-token <hỏi admin> --id AG-KD-MATE-MADE \
  --name "Trợ lý Kinh Doanh Mate Made" --owner <email của bạn> --squad KINH-DOANH

# 2) cấu hình
cd agents/AG-KD-MATE-MADE && cp .env.example .env && vi .env

# 3) chạy (Docker — giống môi trường thật). DRY_RUN=true: chỉ log, KHÔNG gửi tin ra Lark
docker compose up

# 4) test tự động (terminal khác, chạy từ gốc repo)
bash scripts/agent-test.sh AG-KD-MATE-MADE

# 5) chat tay 1 câu
bash scripts/agent-chat.sh AG-KD-MATE-MADE "target doanh số quý này của Mate Made?"

# 6) thử đồng bộ dữ liệu, KHÔNG ghi gì lên platform
python3 kd_sync.py --dry-run
```

## Console

**https://app.34-126-154-135.sslip.io/agent/AG-KD-MATE-MADE** — chat thử, jobs/DLQ, traces,
chi phí, brain riêng, version, **duyệt tri thức**. Không cần Vercel/Supabase, không deploy
web riêng.

## Kênh vào

Admin gán ở Console → Ingress. Agent không cần biết tin đến từ kênh nào — trả lời bằng
`POST /v1/self/jobs/{id}/reply`, platform tự gửi đúng chỗ.

| Kênh | Cần gì |
|---|---|
| Web chat (Chat thử) | có sẵn |
| Lark | channel `lark` + chat_id nhóm KD |
| Telegram | channel `telegram` + chat_id |

## Ranh giới phải giữ

- **Không add AG-MINH-ANH vào nhóm KD** và ngược lại — hai bot cùng nhóm sẽ ra hai biên bản
  khác nhau cho cùng cuộc họp. Chốt với admin trước golive.
- Dữ liệu từ Lark Base (giá vốn, chiết khấu, khách hàng) luôn vào `scope=agent` — agent khác
  trong công ty **không** tra được. Đừng đổi thành `shared`.
- Mọi tri thức vào hàng chờ `pending`, người của team KD duyệt trên console rồi agent mới
  dùng được. Agent không tự duyệt tri thức của chính nó.

## Trạng thái

- [x] USECASE + TESTCASES + manifest + bộ test
- [x] `consumer.py` — hỏi đáp có trích dẫn, chặn dữ liệu hạn chế ở tầng code
- [x] `kd_sync.py` — sync Lark Base + Drive → hàng chờ tri thức
- [x] `meeting_note.py` — biên bản nháp → chốt → publish
- [ ] Nối model thật (hiện `answer()` chạy bằng luật để test được ngay — xem ghi chú trong file)
- [ ] BigQuery `AI_DB` (phase 2 — cần GCP admin cấp dataset + SA riêng)
