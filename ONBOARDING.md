# Onboarding — Tự tạo agent trên LSR Agent Platform

Hướng dẫn cho **thành viên LamsonRetail** tự tạo agent của mình. Có **2 lối**: cài
**plugin** (nhanh, cho agent chạy bằng Claude Code của bạn) hoặc **pull từ git** (đầy đủ
chuẩn + backend riêng). Cả hai đều được platform **ghi telemetry + kiểm soát**.

> Nguyên tắc bắt buộc (mọi agent):
> - **Auth = subscription của chính bạn** (`claude setup-token`), KHÔNG dùng API key, KHÔNG auth chung.
> - **Plugin telemetry bắt buộc** — không gửi trace = không được golive.
> - Agent chỉ chuyển **`active`** khi **admin duyệt + đủ golive checklist**.
> - Xin **enroll token** (`LSR_ENROLL_TOKEN`) từ admin (trong `/opt/lsr-platform/.env`) hoặc hỏi trong nhóm Lark.

Hằng số: `PLATFORM=https://platform.34-126-154-135.sslip.io` ·
`COLLECTOR=https://collector.34-126-154-135.sslip.io`

---

## Lối 1 — Plugin (nhanh)

**1. Cài plugin telemetry** (một lần):
```bash
claude plugin marketplace add LamsonRetail/lsr-agent-platform
claude plugin install lsr-telemetry@lsr
```

**2. Đăng ký agent để lấy telemetry key** (self-service):
```bash
curl -s -X POST "$PLATFORM/v1/agents/enroll" \
  -H "Authorization: Bearer $LSR_ENROLL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"AG-YOURNAME","name":"Tên agent","owner":"ban@hapas.vn","squad":"RETAIL"}'
```
→ Trả về `telemetry_key` (**chỉ hiện 1 lần** — lưu lại) + `db_schema` + `collector`.

**3. Đặt env cho môi trường chạy agent** (đăng nhập subscription trước bằng `claude setup-token`):
```bash
export LSR_COLLECTOR="https://collector.34-126-154-135.sslip.io"
export LSR_AGENT_ID="AG-YOURNAME"
export LSR_TELEMETRY_API_KEY="lsr_tel_...(bước 2)"
```

**4. Chạy agent** bằng Claude Code như bình thường → mọi tool call/token được ghi về
platform; hook `PreToolUse`/`UserPromptSubmit` hỏi Policy API (mặc định cho phép).

**5. Golive:** hoàn tất checklist → nhờ admin chuyển `active`.

---

## Lối 2 — Pull từ git (đầy đủ chuẩn)

**1. Clone repo:**
```bash
git clone https://github.com/LamsonRetail/lsr-agent-platform.git
cd lsr-agent-platform
```

**2. Sinh agent theo chuẩn** (tạo `agents/<id>/lsr-agent.yaml` + system prompt + bộ test):
```bash
node scripts/new-agent.mjs AG-YOURNAME "Tên agent" ban@hapas.vn RETAIL bot
```

**3. (Tuỳ chọn) Backend riêng cho agent** (sub-folder chung repo, auto-deploy cùng platform):
```bash
node scripts/new-agent-backend.mjs AG-YOURNAME
```

**4. Commit + mở Pull Request** → CI tự **kiểm chuẩn** (`tests/test_agent_standards.py`):
cấm API key, bắt buộc `auth: subscription` + `telemetry.enabled: true`, owner là email thật.
Sai chuẩn → CI fail, không merge được. Admin review & merge.

**5. Lấy telemetry key** (enroll như Lối 1 bước 2, hoặc nhờ admin `register`), **cài plugin**
(Lối 1 bước 1), **đặt env** (Lối 1 bước 3).

**6. Golive checklist → nhờ admin `active`.**

---

## Bảng UI (basic-auth `lamson`)
`https://app.34-126-154-135.sslip.io` — Platform · Chi phí · Sức khoẻ · Test & Learn ·
Golden · Duyệt tri thức · Audit.

## Câu hỏi thường gặp
- **Không có enroll token?** Xin admin (nằm ở `/opt/lsr-platform/.env` → `LSR_ENROLL_TOKEN`).
- **`agent_id` đã tồn tại (409)?** Trùng id — đổi id, hoặc nhờ admin cấp lại key.
- **Agent không lên `active`?** Cần đủ golive checklist + admin duyệt (gate 27 mục).
- **Trace không thấy?** Kiểm tra `LSR_COLLECTOR`/`LSR_TELEMETRY_API_KEY`; xem trang **Sức khoẻ**.
