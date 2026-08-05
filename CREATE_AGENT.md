# Tạo một agent mới trên LSR Agent Platform

Tài liệu này mô tả **cách một người bất kỳ (phòng ban/cá nhân) tạo agent của mình**
bằng Claude Code — và platform vẫn nắm hết, đánh giá, deactivate được.

Áp dụng các quyết định đã chốt (PLAN §12): **Gateway bắt buộc · virtual key do
platform cấp · MCP skill tự do · LiteLLM tự host · squad agent là kênh dữ liệu**.

---

## 0. Ý tưởng một dòng

> Người dùng viết agent bằng **Claude Agent SDK của riêng mình**, nhưng agent được
> **cấu hình sẵn để trỏ mọi lời gọi model qua Gateway của platform** (bằng
> *virtual key* platform cấp) và **nhúng sẵn Telemetry SDK**. Nhờ vậy "login riêng"
> nhưng "platform nắm hết" — và **revoke key = tắt agent**.

---

## 1. Điều kiện trước khi bắt đầu

| Cần có | Ai cấp |
|--------|--------|
| Tài khoản platform (định danh cá nhân, thuộc phòng ban/squad) | Admin/IT |
| Claude Code đã cài + plugin `lsr-agent` | Cá nhân tự cài |
| Thuộc ít nhất 1 squad | Quản lý squad |

> Người dùng **không** cần và **không** được cầm khoá Anthropic thô — platform cấp
> virtual key thay thế.

---

## 2. Sơ đồ tuần tự

```
 Người tạo        Claude Code (plugin lsr-agent)     Platform API            Gateway/Lark
    │                     │                              │                        │
    │ lsr login           │──── OAuth/SSO ──────────────►│                        │
    │                     │◄──── personal token ─────────│                        │
    │ lsr-agent init      │  hỏi tên/squad/skill...       │                        │
    │                     │  scaffold project cục bộ      │                        │
    │ lsr-agent register  │──── tạo record agents ───────►│  (status=registered)   │
    │                     │◄── virtual key + telemetry key│  + cấp budget mặc định │
    │ lsr-agent lark connect│─ chọn bot/user + authorize ──►│  map agent↔chat / OAuth│──► Lark
    │  ... code agent ...  │  (model call qua gateway)     │                        │
    │ lsr-agent skill add  │──── khai báo MCP (log) ──────►│                        │
    │ lsr-agent test       │── chạy bộ test → traces ─────►│  chấm pass/fail + 6 CS │
    │ lsr-agent golive     │──── yêu cầu golive ──────────►│  active + mở full key  │──► gắn bot Lark
    │                     │                              │  ingest log liên tục   │──► auto-deactivate nếu fail
```

---

## 3. Các bước chi tiết

### Bước 1 — Đăng nhập platform
```bash
lsr login
```
Mở SSO nội bộ → lưu **personal token** cục bộ. Token này định danh *người tạo*
(để gắn `owner_user` cho agent), khác với virtual key của agent.

### Bước 2 — Khởi tạo agent (scaffold)
```bash
lsr-agent init
```
Hỏi tương tác: tên agent, **squad**, mô tả/mục đích, `connect_mode` (bot/user),
model mặc định, skill (MCP) muốn dùng. Sinh ra project cục bộ (xem §4) đã **pre-wire**
gateway + telemetry.

### Bước 3 — Đăng ký + nhận khoá
```bash
lsr-agent register
```
Gọi Platform API → tạo record trong `agents` (`status=registered`), gắn
`owner_user`, `squad`. Platform trả (hiện **một lần**, lưu vào `.env` đã gitignore):
- `ANTHROPIC_API_KEY` = **virtual key** `lsr_vk_...` (KHÔNG phải khoá Anthropic thô)
- `LSR_TELEMETRY_API_KEY` = `lsr_tel_...`
- `LSR_AGENT_ID`

> Nếu squad chưa có agent nào → agent này được đề nghị làm **squad agent chính**
> (`is_squad_agent=true`). Squad phải có ≥1 agent mới đủ điều kiện đánh giá.

### Bước 3.5 — Kết nối Lark (chọn kênh + authorize)
Vì mọi giao tiếp đi qua Lark, agent phải gắn một kênh Lark trước khi golive.
```bash
lsr-agent lark connect
```
Chọn `connect_mode`:

**A. Bot (Custom App)** — khuyến nghị:
1. Chọn dùng **bot dùng chung của platform** (nhanh, đã cài sẵn) hay **app riêng**
   của agent (cách ly hơn, tự tạo trên Lark Developer Console).
2. **Authorize:** admin cài app vào tenant + cấp scopes (`im:message`, `im:chat`,
   `im:message.receive_v1`...) — làm **một lần** cho platform bot.
3. Bật **Event Subscription** trỏ về webhook collector (platform điền sẵn).
4. **Add bot vào (các) nhóm chat** mục tiêu → platform map agent ↔ `chat_id`.
→ Agent nhận việc qua event, trả kết quả trong nhóm; platform đếm invocation + đọc kết quả.

**B. User account** — chỉ khi bắt buộc:
1. `lsr-agent lark connect --mode user` mở **URL OAuth** của Lark.
2. Người dùng **đăng nhập & đồng ý scopes** ngay trên giao diện Lark.
3. Callback về platform → đổi `authorization code` lấy `user_access_token` +
   `refresh_token`, **lưu mã hoá ở platform** (không nằm trong repo). Token tự refresh.
→ Agent hành động dưới danh nghĩa user đó. Cần review ToS/chính sách nội bộ trước.

> Việc authorize (cài app, cấp scope, đồng ý OAuth) do **người dùng/admin thực
> hiện trên giao diện Lark** — platform không nhập hộ mật khẩu/khoá.

### Bước 4 — Phát triển bằng Claude Code
Người dùng viết logic agent bằng **Claude Agent SDK** như bình thường. Vì
`ANTHROPIC_BASE_URL` đã trỏ về gateway và key là virtual key, **mọi lời gọi model
tự động đi qua platform** (log token, áp budget) — không phải làm gì thêm.

### Bước 5 — Thêm skill (MCP tự do)
```bash
lsr-agent skill add bigquery      # hoặc bất kỳ MCP server nào
```
Cập nhật manifest + **đăng ký/log** skill vào danh sách của agent trên platform.
Không cần duyệt (theo quyết định "MCP tự do"), nhưng danh sách được ghi lại để
đánh giá & kiểm toán. Lời gọi tool được đo qua **Telemetry SDK** (vì gateway không
proxy tool).

### Bước 6 — Test trước golive
```bash
lsr-agent test
```
Chạy **bộ test có nhãn** (`needs_tool`, `expected_tool`) → Telemetry SDK sinh trace
→ platform tính pass/fail + 6 chỉ số hành vi tool. **Phải pass** mới được golive.

### Bước 7 — Golive
```bash
lsr-agent golive
```
Platform kiểm: đủ thông tin đăng ký + test pass → `status=active`, mở virtual key
ở full budget, gắn bot vào nhóm Lark. Agent bắt đầu nhận việc.

### Bước 8 — Vận hành & governance (tự động)
Platform liên tục ingest: **gateway log** (token) + **telemetry trace** (hành vi
tool) + **Lark events** (usage, kết quả, 👍/👎). Test định kỳ; fail theo chính sách
→ **auto-deactivate** = revoke virtual key + `status=deactivated` + báo owner.

---

## 4. Template scaffold ra gì

```
my-agent/
├── lsr-agent.yaml          # manifest agent (khai báo cho platform)
├── .env                    # khoá platform cấp (gitignored)
├── src/agent.py            # logic agent (Claude Agent SDK) — đã pre-wire
├── skills/                 # cấu hình MCP skills
└── tests/agent_tests.yaml  # bộ test có nhãn needs_tool/expected_tool
```

**`lsr-agent.yaml` (ví dụ):**
```yaml
apiVersion: lsr/v1
agent:
  id: ""                    # điền khi register
  name: Order Lookup Bot
  version: 0.1.0
  owner: thint@hapas.vn
  squad: SQ-SALES
  is_squad_agent: false
  connect_mode: bot         # bot | user
  description: Tra cứu đơn hàng cho sales
lark:                       # kết nối Lark (Bước 3.5)
  connect_mode: bot         # bot | user
  bot:                      # khi connect_mode=bot
    app: platform-shared    # platform-shared | custom
    chat_ids: []            # nhóm agent phục vụ (điền khi add bot)
    event_webhook: https://collector.lsr.internal/lark/events
  user:                     # khi connect_mode=user (token lưu ở platform, không ở repo)
    oauth_scopes: [im:message, im:chat]
runtime:
  sdk: claude-agent-sdk
  model: claude-sonnet-5
  gateway_base_url: https://gateway.lsr.internal   # -> ANTHROPIC_BASE_URL
skills:                     # MCP tự do — chỉ khai báo + log
  - {name: bigquery,  type: mcp}
  - {name: lark-task, type: mcp}
telemetry:
  enabled: true             # bắt buộc, không tắt được khi golive
  collector: https://collector.lsr.internal
tests:
  suite: tests/agent_tests.yaml
```

**`.env` (platform cấp khi register):**
```
ANTHROPIC_BASE_URL=https://gateway.lsr.internal
ANTHROPIC_API_KEY=lsr_vk_xxxxxxxx        # virtual key
LSR_TELEMETRY_API_KEY=lsr_tel_xxxxxxxx
LSR_AGENT_ID=AG-ORDER-BOT
```

**`src/agent.py` (điểm pre-wire tối thiểu):**
```python
# base_url + key lấy từ .env -> mọi model call đi qua gateway
# TraceRecorder (telemetry SDK) bọc quanh 1 lượt chạy để ghi token/tool/output
from rating_agent.telemetry import TraceRecorder, TelemetryClient

rec = TraceRecorder(agent_id=os.environ["LSR_AGENT_ID"], task_id=task_id)
# ... gọi Claude Agent SDK (ANTHROPIC_BASE_URL đã trỏ gateway) ...
rec.record_llm(model, usage.input_tokens, usage.output_tokens)
rec.record_tool("bigquery", args, ok=True, has_result=True)
rec.set_output(answer)
TelemetryClient(collector, os.environ["LSR_TELEMETRY_API_KEY"]).report(rec.build())
```

---

## 5. Ai chịu trách nhiệm gì

| Vai trò | Việc |
|---------|------|
| **Người tạo agent** | init/register/code/test/golive; viết bộ test có nhãn |
| **Quản lý squad** | đảm bảo squad có ≥1 agent; chỉ định squad agent |
| **Platform (tự động)** | cấp/revoke key, log gateway, ingest trace, chấm điểm, auto-deactivate, dashboard |
| **Admin** | tạo tài khoản, quota budget, chính sách log/PII |

---

## 6. Cần confirm

1. **Giao diện tạo agent:** plugin Claude Code cung cấp lệnh `lsr-agent ...`
   (khuyến nghị) — hay muốn thêm CLI độc lập / UI web?
2. **Cấp tài khoản & budget mặc định:** ai duyệt (admin/quản lý squad?), budget
   token mặc định cho agent mới là bao nhiêu?
3. **Bộ test pre-golive:** người tạo tự viết test có nhãn, hay platform cấp bộ
   test mẫu theo loại skill?
4. Địa chỉ nội bộ thật cho `gateway.lsr.internal` / `collector.lsr.internal`.
