# LYLY — Trợ lý vận hành sàn MATE MADE (AG-KD-MATE-MADE)

Agent của team **MATE MADE** (túi & quà tặng có túi, B2C trên **Shopee** và **TikTok Shop**)
trên LSR Agent Platform.

**Người dùng là team nội bộ ba nhóm — ADS · AFF · Vận hành sàn.** Không có sale, không ai
chat 1-1 với khách. Hai việc chính:

1. **Hỏi số & hỏi chính sách** — ROAS, ngân sách, tồn kho, tỷ lệ hủy/hoàn, hoa hồng aff,
   chính sách sàn, deadline campaign. Luôn kèm **link nguồn + kỳ dữ liệu**. Không có căn cứ
   → _"Cái này em chưa có, anh/chị hỏi lại quản lý nhé."_
2. **Biên bản họp** — recording → transcript → biên bản nháp (có mục **cam kết
   ai-làm-gì-khi-nào**) → **xin chủ trì chốt** → Lark Docs + task + lưu vào kho tri thức.

> **LYLY tra số để người ta quyết, không quyết thay.** Không tự duyệt ngân sách quảng cáo,
> giá bán, khuyến mãi sàn, booking KOC, hay đền bù ngoài chính sách — kể cả khi kho tri thức
> có sẵn số chứng minh nên làm, kể cả khi bị hối gấp.

**Số không nằm trong prompt.** Toàn bộ số liệu nằm trong kho tri thức đã duyệt, sync hàng
ngày từ **Lark Base** → số đổi là sửa trong Base, không phải sửa code.

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
# 0) đăng nhập platform (1 lần, giống `gh auth login` — KHÔNG cần xin token của ai).
#    Script xin mã, bạn bấm Duyệt trên console, token cá nhân lưu vào ~/.lsr/token.
bash scripts/lsr-login.sh

# 1) đăng ký agent (1 lần) — nhận LSR_AGENT_TOKEN. Từ P11: owner mặc định là người
#    đăng nhập, và người tạo TỰ thành moderator của agent (tự duyệt tri thức được).
python3 scripts/lsr_adopt.py --id AG-KD-MATE-MADE \
  --name "LYLY - Tro ly van hanh san MATE MADE" --squad KINH-DOANH

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
- Dữ liệu từ Lark Base (giá vốn, biên lợi nhuận, chi phí booking) luôn vào `scope=agent` — agent khác
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
