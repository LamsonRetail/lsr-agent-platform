# AG-SOURCING — runbook golive

Trạng thái lúc viết (đã kiểm live, không suy đoán):

| Thứ | Trạng thái |
|---|---|
| Agent enroll | ✅ `GET /v1/self` → `status: registered` |
| Core Lark đa-app | ✅ `/v1/lark/chats?app_id=cli_aaf6ce7c8d38deed` → 200 + 3 nhóm |
| Brain riêng | ✅ 12 item `approved` từ 2 Lark Doc (`brain_seed.py --list`) |
| Golden set | ✅ 4 case active trong `golden-cases.json` (chưa upload lên platform) |
| **Instruction** | ❌ `GET /v1/self/context` → `instruction_block: null`, `version: null` |

→ Bot đang online trong TEAM S + SOURCING MM mà **không có refusal policy nào**.

## Vì sao token agent không tự chạy được chuỗi này

Có **hai cửa độc lập**, không phải một:

1. **Cửa mạng (Caddy).** `infra/lsr-platform/caddy/Caddyfile:38` chỉ mở không cần gateway token cho
   `/v1/agents/enroll`, `/bootstrap/*`, `/v1/self`, `/v1/self/*`, `/v1/lark/*`, `/v1/chat/*`.
   `/v1/agents/{id}/versions` **không** thuộc danh sách này → thiếu header `X-Gateway-Token` là
   Caddy trả `403 "forbidden"` (chuỗi trần, không phải JSON `{"detail":…}` của FastAPI — đây là
   cách nhận biết mình bị chặn ở cửa nào).
2. **Cửa quyền (app).** `_require_role` (`app.py:227`) đòi `p["kind"] in ("session","admin_token")`.
   Token agent **không thuộc loại nào cả** → dù có gateway token vẫn không qua. Nghĩa là không phải
   "agent chưa đủ cấp moderator" mà là **agent vĩnh viễn không đủ tư cách**; việc này phải do
   **người** làm bằng phiên đăng nhập Console, hoặc bằng admin token.

Đường tự phục vụ còn lại cũng đóng: `POST /v1/self/actions/propose` (`app.py:4215`) đòi
`is_platform=true` (chỉ AG-OPS/AG-EVAL) → AG-SOURCING nhận 403.

Kết luận: **bước 1 và bước 5 buộc phải có người.** Không có mẹo nào lách, và không nên lách.

## Chuỗi golive — ai làm gì

### Bước 0 — Kiểm regex trước khi làm phiền người khác (em làm được, offline)
```bash
cd agents/AG-SOURCING && python3 golden_selfcheck.py    # không token, không model, không gọi API
```
Chấm 4 regex active bằng **đúng** hàm platform dùng (`_assert_answer`, `app.py:5038` →
`re.search`, không IGNORECASE) trên hai bộ câu: câu mà `INSTRUCTION.md` **bắt** agent nói (phải
khớp) và câu trả lời **sai** kiểu điển hình — đã xoá NCC, đọc dữ liệu BST, nêu nguồn rỗng (phải
KHÔNG khớp). Đã chạy: 4/4 case qua cả hai chiều.

Lý do có bước này: `--run` ở bước 4 cần **admin token** nên phải nhờ ntranthi. Regex viết sai thì
lần chạy đó fail vì lỗi mình, tốn một lượt nhờ người và để lại một dòng fail trong
`regression_runs`. Nhưng nó **không** thay được bước 4: ở đây câu trả lời do em viết theo
instruction, chạy thật là model viết.

### Bước 1 — Tạo version (chủ agent, cần `moderator`) — Console
`https://app.34-126-154-135.sslip.io/agent/AG-SOURCING` → **Version** → New version →
dán **toàn bộ** nội dung `INSTRUCTION.md` vào `instruction_block` → Save (version ở `draft`).

Ghi lại số version N. Kiểm: `GET /v1/self/version` phải thấy nó.

### Bước 2 — Publish `dev` (chủ agent, `moderator` là đủ)
Console → Version → Publish → env `dev`. `dev`/`stg` **không** qua eval gate
(`app.py:3272` chỉ gate khi `env == "prod"`), nên bước này chạy được ngay.

### Bước 3 — Hỏi agent bằng instruction MỚI (em làm được)
```bash
cd agents/AG-SOURCING
LSR_ENV=dev DRY_RUN=true python3 consumer.py     # terminal 1
LSR_AGENT_TOKEN=... python3 golden_run.py --ask  # terminal 2
```
`LSR_ENV=dev` là bắt buộc: `/v1/self/context` mặc định `env=prod` (`app.py:3448`), bỏ nó là đang
chấm instruction **cũ** rồi gắn kết quả cho version **mới** — gate xanh mà chưa kiểm gì.

⚠️ **Cảnh báo tác dụng phụ, phải quyết trước khi chạy:** `consumer.py` poll `/v1/self/jobs` —
**một queue dùng chung mọi kênh**. Nó không phân biệt job của `golden_run.py` với tin nhắn thật
trong TEAM S / SOURCING MM, và `/reply` gửi thẳng vào nhóm. Nên bật consumer = agent bắt đầu trả
lời người thật. `DRY_RUN=true` **không** chặn việc này (chỉ chặn ghi brain). Hai lựa chọn:
- (an toàn hơn) nhờ ntranthi tạm `pause_routing` 2 chat_id, chạy `--ask`, rồi bật lại;
- (nhanh hơn) chấp nhận: sau bước 2 agent đã có policy nên trả lời có kiểm soát.

Sau đó **đọc `answers.json` bằng mắt** — regex chỉ chứng minh agent CÓ NÓI câu đúng, không chứng
minh nó không bịa thêm số liệu ở câu sau. (`answers.json` bị gitignore: chứa tri thức nội bộ.)

### Bước 4 — Nạp golden case + chấm (ntranthi, cần `admin`)
```bash
cd agents/AG-SOURCING
LSR_ADMIN_TOKEN=... python3 golden_run.py --upload            # POST /v1/golden-cases  (admin)
LSR_ADMIN_TOKEN=... python3 golden_run.py --run --version N   # POST /v1/regression/run (admin)
```
Cả hai endpoint đều `_require_admin` (`app.py:5738`, `app.py:5783`) **và** nằm ngoài allowlist của
Caddy → người chạy cần cả `X-Gateway-Token`. Script chỉ dùng stdlib, luôn truyền
`skill: "AG-SOURCING"`, không ghi gì ngoài phạm vi agent.

`--run` phải đúng `--version N` của bước 1: gate tìm `regression_runs WHERE target_id=AG-SOURCING
AND agent_version=N AND passed=true` (`app.py:3218`).

### Bước 5 — Publish `prod`
Chủ agent bấm publish `prod` → vì chưa phải admin nên vào `pending_actions` chờ duyệt
(`app.py:3243`), ntranthi duyệt. Hoặc ntranthi publish thẳng.

Gate sẽ kiểm: ≥1 golden case `active` (đếm **toàn cục**) + regression run PASS gắn đúng version N.

### Bước 6 — Xác nhận thật
```bash
LSR_AGENT_TOKEN=... curl -s -H "Authorization: Bearer $LSR_AGENT_TOKEN" \
  "$LSR_PLATFORM_URL/v1/self/context?session_id=probe&q=test" | python3 -m json.tool | head
# instruction_block PHẢI khác null, version PHẢI = N
bash scripts/agent-test.sh AG-SOURCING
```

## Biết trước hai chỗ sẽ vênh

- **Golden case #1 giờ có cơ sở để pass**: brain đã có tri thức, hỏi "Quy trình duyệt báo giá NCC
  hiện tại ra sao?" thì RAG trả về Bước 6 kèm `source_url` (kiểm bằng `brain_seed.py --check`).
  Trước khi nạp brain thì case này chắc chắn fail.
- **`llm_judge` âm thầm hạ cấp thành `contains`** khi `JUDGE_URL` chưa cấu hình (`app.py:5708`) —
  nên golden set này dùng `regex` toàn bộ, không dùng `llm_judge`.
