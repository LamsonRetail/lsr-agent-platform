# Đóng góp & tạo Agent — LSR Agent Platform

Hướng dẫn cho **thành viên team** pull repo về và tạo thêm agent trong platform này.
Mọi agent mới **phải theo chuẩn** (CI kiểm tự động) và **dùng auth của owner**, không
dùng auth chung của platform.

## ⚠️ Phạm vi được phép sửa (bắt buộc)
Khi pull repo về, bạn **CHỈ được thêm/sửa agent của mình**:
- `agents/<AGENT_ID>/**` — manifest, system prompt, test của agent
- `apps/agents/<AGENT_ID>/**` — backend riêng của agent

**KHÔNG được đụng CORE** (để không ảnh hưởng platform / shared brain / rules chung):
`infra/`, `src/`, `scripts/`, `plugins/`, `installers/`, `apps/platform-web/`, `.github/`,
`tests/`, `docs/`, agent nền tảng (`agents/AG-LSR-BRAIN`, `agents/minh-anh`), và các file
rules ở gốc (PLAN.md, MASTER_DATA.md, GOLIVE_CHECKLIST.md, CONTRIBUTING.md, STATUS.md).

Cơ chế chặn (3 lớp):
1. **CI scope-guard** (`.github/workflows/scope-guard.yml`) — PR chạm core của người không
   phải maintainer sẽ **fail, không merge được**.
2. **CODEOWNERS** — thay đổi core bắt buộc review của maintainer.
3. **pre-commit hook local** (tùy chọn, chặn sớm): `bash scripts/install-git-hooks.sh`
   → commit chạm core bị chặn ngay. Kiểm thủ công: `bash scripts/check-scope.sh`.

Cần sửa core? Mở issue hoặc nhờ maintainer (xem `.github/CODEOWNERS`). Maintainer khai báo
trong `.github/maintainers.txt`.

## 0. Workflow theo TEAM (bản stable)

Mọi team làm **chung repo này** nhưng trên **branch riêng** — main luôn là bản stable.

```bash
git clone https://github.com/LamsonRetail/lsr-agent-platform.git
cd lsr-agent-platform
git checkout -b agent/<team>-<AGENT-ID>     # vd: agent/bi-AG-KHO-HN
```

Quy ước:
- **1 agent = 1 branch** `agent/<team>-<AGENT-ID>`; team 2–3 người cùng push lên branch đó
  (chia file: người viết USECASE/TESTCASES, người code consumer, người lo backend/routing).
- **Không commit thẳng main.** Xong thì mở PR → CI (scope-guard + agent-gate) chạy →
  maintainer review → merge. Pull bản stable mới nhất: `git pull origin main` (hoặc tag `v1.x`).
- Secrets (`.env.lsr`, token) **không bao giờ commit** — đã gitignore, CI cũng quét.

### Quy trình BẮT BUỘC: use case → test case → code

Mỗi agent mới phải có `agents/<ID>/USECASE.md` + `TESTCASES.md` **trước khi viết code**.
Quên thì hệ thống tự nhắc ở 2 lớp:
1. **Ngay khi đang code** — plugin lsr-telemetry chặn Write/Edit file code trong
   `agents/<ID>/` kèm hướng dẫn (viết 2 file .md xong là code tiếp được).
2. **Khi mở PR** — CI `agent-gate` fail nếu có code mà thiếu 2 file trên.

### Console của agent nằm ở đâu?

**Trong chính platform** — `https://app.34-126-154-135.sslip.io/agent/<AGENT_ID>`:
chat thử, jobs/DLQ, traces, chi phí, brain riêng, version. Agent mới đăng ký là **tự có**,
**KHÔNG cần tài khoản Vercel/Supabase, không phải deploy web riêng, không đăng nhập thêm gì**.

Kênh vào của agent do admin gán 1 dòng ở Console → **Ingress**:

| Kênh | Cần gì |
|---|---|
| Web chat (Chat thử) | có sẵn |
| Telegram | routing: channel `telegram` + chat_id |
| Lark | routing: channel `lark` + chat_id nhóm |

Agent **không cần biết tin đến từ kênh nào**: trả lời bằng
`POST /v1/self/jobs/{id}/reply`, platform tự gửi đúng chỗ.

Muốn xem một agent đã nối đủ mọi thứ: **[agents/AG-MINH-ANH](agents/AG-MINH-ANH/README.md)**
là agent demo tham chiếu (Lark + Telegram + web chat + brain + memory + Docker riêng).

### Tạo + chạy + test agent trong 5 phút

```bash
bash scripts/new-agent.sh AG-KHO-HN "Trợ lý kho HN"   # scaffold đủ template
# 1) điền agents/AG-KHO-HN/USECASE.md + TESTCASES.md (+ tests.jsonl case tự động)
# 2) đăng ký với platform (nhận token, hỏi admin enroll-token):
python3 scripts/lsr_adopt.py --enroll-token <token> --id AG-KHO-HN \
  --name "Trợ lý kho HN" --owner <email của bạn>
# 3) code answer() trong agents/AG-KHO-HN/consumer.py rồi chạy (Docker, giống thật):
cd agents/AG-KHO-HN && cp .env.example .env && vi .env && docker compose up
#    (hoặc chạy thẳng: LSR_AGENT_TOKEN=<token> python3 consumer.py)
# 4) terminal khác — test tự động theo tests.jsonl:
bash scripts/agent-test.sh AG-KHO-HN
# hoặc chat tay: bash scripts/agent-chat.sh AG-KHO-HN "câu hỏi thử"
```

Chat test đi qua **Chat API của platform** (cùng đường với Lark) nên chạy được ngay
không cần Lark app, và mọi lần chạy đều có telemetry/quota/audit như thật.

## 1. Lấy repo về (chi tiết)
```bash
git clone https://github.com/LamsonRetail/lsr-agent-platform.git
cd lsr-agent-platform
```
Yêu cầu: `git`, `python3` (test), `node` ≥ 20 (backend web), Docker (nếu chạy infra),
và **subscription Claude riêng** của bạn (để agent bạn tạo dùng auth của bạn).

Chạy test/validator ở máy:
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pydantic PyYAML pytest requests
pytest        # gồm cả kiểm chuẩn agent (tests/test_agent_standards.py)
```

## 2. Tạo một agent mới (theo chuẩn)
```bash
node scripts/new-agent.mjs <AGENT_ID> "Tên agent" <owner-email> [squad] [bot|user]
# ví dụ:
node scripts/new-agent.mjs AG-SALES-COACH "Sales Coach" an.nguyen@lamsonretail.vn SQ-SALES bot
```
Sinh `agents/<id>/`: `lsr-agent.yaml` (manifest chuẩn), `system_prompt.md`,
`tests/agent_tests.yaml`. Manifest đã set sẵn: `auth: subscription`, `telemetry.enabled: true`.

Kiểm chuẩn ngay:
```bash
pytest tests/test_agent_standards.py
```

## 3. Auth của OWNER (KHÔNG dùng auth chung platform)
Mỗi agent chạy bằng **subscription Claude của owner**, không phải khoá chung:
```bash
claude setup-token        # owner đăng nhập subscription RIÊNG → token lưu ở máy/VPS chạy agent
```
- Platform **không** cấp khoá LLM. Chỉ cấp `TELEMETRY_API_KEY` (riêng agent) khi register.
- CI **chặn** manifest có `api_key`/auth chung; `runtime.auth` phải là `subscription`.

## 4. Đăng ký + golive
```bash
# đăng ký (nhận telemetry key + tạo schema DB riêng trên Postgres platform)
curl -s $PLATFORM/v1/agents/register -H "Authorization: Bearer $ADMIN" \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"AG-...","name":"...","owner":"...@lamsonretail.vn","squad":"SQ-..."}'
```
Rồi: kết nối Lark (bot/user) → bật telemetry → **pass bộ test** → golive. Xem chi tiết
[CREATE_AGENT.md](CREATE_AGENT.md).

## 5. Console của agent — CÓ SẴN, không phải làm gì

`https://app.34-126-154-135.sslip.io/agent/<AGENT_ID>` — chat thử, jobs/DLQ, traces,
chi phí, brain riêng, version. **Không cần Vercel/Supabase, không deploy web riêng.**

> *(Nâng cao — hiếm khi cần)* Nếu agent cần **giao diện riêng cho người dùng cuối**
> (không phải console vận hành), có thể sinh app Next.js riêng:
> `node scripts/new-agent-backend.mjs <AGENT_ID> "Tên"` rồi deploy bằng tài khoản Vercel
> của **owner platform**. Mặc định **không dùng** — console trong platform là đủ.

## 6. Quy trình đóng góp
1. Tạo nhánh: `git checkout -b agent/<id>`.
2. Chạy `pytest` (phải xanh — gồm kiểm chuẩn agent).
3. Mở PR vào `main`. **CI** (`.github/workflows/ci.yml`) chạy test + validator; không
   đạt chuẩn → không merge.
4. Merge → auto-deploy: platform trên VM (CI `deploy.yml`). Agent của bạn chạy bằng
   `docker compose up` ở nơi bạn muốn; console đã có sẵn trong platform.

## Tiêu chuẩn agent (CI enforce)
- `agent.owner` = email owner thật · `connect_mode` ∈ {bot,user}.
- `runtime.auth = subscription` (auth của owner) · **không** api key/auth chung.
- `telemetry.enabled = true` (control point) · có bộ test.
- Bộ nhớ/DB nằm trên **Postgres của platform (VM GCP)**, mỗi agent **schema riêng** (tự tạo khi register); dữ liệu phân tích đẩy sang **BigQuery AI_DB**.

## 7. Agent CÓ SẴN ở dự án khác (adopt vào platform)

Agent đang chạy ở repo/hạ tầng khác vẫn đăng ký được, **giữ nguyên cấu hình và nơi chạy**:

```bash
# chạy TRONG repo của agent đó
python3 /đường/dẫn/lsr-agent-platform/scripts/lsr_adopt.py \
  --id AG-YOURBOT --name "Your Bot" --owner you@lamsonretail.vn --squad SQ-SALES \
  --platform https://platform.34-126-154-135.sslip.io \
  --collector https://collector.34-126-154-135.sslip.io \
  --admin-token "$PLATFORM_ADMIN_TOKEN" \
  --trace-script /đường/dẫn/lsr-agent-platform/plugins/lsr-telemetry/scripts/lsr_trace.py
```
Script sẽ: dò `git remote` + MCP đang dùng → sinh `lsr-agent.yaml` (`deployment: external`)
→ **thêm hook telemetry** vào `.claude/settings.json` (**không phá cấu hình cũ**) →
đăng ký, ghi `.env.lsr` (đã gitignore). Thêm `--dry-run` để xem trước.

Sau đó: owner chạy `claude setup-token` (subscription **của owner**) và nạp `.env.lsr`
khi khởi động agent → trace chảy về, agent lên dashboard như agent managed.

**Cắt agent external thế nào?** Platform không kill process của team, nhưng khi
`status=deactivated` thì **collector trả 403** (không nhận trace) + cắt Lark →
agent ra khỏi governance và dashboard thấy ngay.
