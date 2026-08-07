# LSR Agent Platform — LamsonRetail

Nền tảng agent nội bộ: sau khi deploy, **các phòng ban/cá nhân dùng Claude Code
kết nối vào để tự tạo agent của mình**, tự yêu cầu thêm skill; mỗi người đăng nhập
**Claude Agent SDK riêng**. Nhưng nền tảng **nắm được toàn bộ request**, có cơ chế
**đánh giá / deactivate** agent, cùng **dashboard & báo cáo** đã xây.

> Đây là bản mở rộng từ "Rating Agent". Phần chấm điểm/governance/dashboard cũ giờ
> là **một subsystem** của platform. Chi tiết liên quan:
> [MASTER_DATA.md](MASTER_DATA.md) · [AGENT_INTEGRATION.md](AGENT_INTEGRATION.md).

> ⚠️ **Auth model (đã chốt): agent xác thực bằng Claude Agent SDK đăng nhập
> subscription riêng (OAuth — `claude login` / `setup-token`), KHÔNG dùng
> `ANTHROPIC_API_KEY`.** Hệ quả: bỏ mô hình "LLM gateway virtual-key" làm control
> point. Thay bằng **Claude Code plugin + Telemetry SDK** (nắm request/token) và
> **kill switch qua Lark + dừng process + thu hồi đăng ký**. Xem §2, §5.

---

## 1. Nguyên tắc thiết kế

1. **Self-service, nhưng governed-by-default.** Ai cũng tạo được agent, nhưng mọi
   agent phải đăng ký, định danh, và đi qua control plane.
2. **Nắm hết bằng công cụ bắt buộc + kênh làm việc.** Vì agent dùng subscription
   riêng (không có API key để proxy), việc "nắm hết" dựa vào **Claude Code plugin +
   Telemetry SDK bắt buộc** (ghi mọi request/tool/token về collector) và **mọi
   việc đi qua Lark**. Kill switch = **cắt Lark + dừng process + thu hồi đăng ký**.
3. **Hai nhánh đánh giá giữ nguyên:** Squad (hiệu quả mục tiêu) và Agent
   (skill/usage/kết quả + test). **Mỗi squad ≥ 1 agent; kết quả squad đo qua agent
   của squad.**
4. **Resource Index (chung mọi agent):** file/link được share cho agent phải được
   **lưu metadata + index ra ngoài** (collector/Postgres), truy xuất lại bằng
   **search** — KHÔNG nhồi vào memory/context (tránh long-memory). Đã có:
   `src/rating_agent/resources/` + endpoint collector `/v1/resources`.
5. **Meeting agent "Minh Anh"** (nền tảng): share từ điển thư mục `meeting-notes`
   cho agent mới; khi vào họp thì viết biên bản (transcript → nội dung chính →
   owner confirm → tạo task). Xem [agents/minh-anh/](agents/minh-anh/WORKFLOW.md).
6. **Test & Learn:** bài test (nhiều case, review→active), chọn agent/người làm,
   trượt → training (HR import file → md). Xem [TEST_LEARN.md](TEST_LEARN.md).

---

## 2. Kiến trúc: Control plane / Data plane

```
        NGƯỜI DÙNG (phòng ban / cá nhân)
                 │  dùng Claude Code + template của platform
                 ▼
┌──────────────────────── CONTROL PLANE (platform) ─────────────────────────┐
│  ┌───────────────┐  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐ │
│  │ Onboarding &   │  │  LLM Gateway  │  │Skill Registry │  │ Governance & │ │
│  │ Registry       │  │ (proxy model, │  │ (MCP tự do,   │  │ Evaluation   │ │
│  │ (agents,users, │  │ virtual key,  │  │ khai báo+log, │  │ (scorer,test,│ │
│  │ squads, keys)  │  │ token+budget, │  │ meter usage)  │  │ 6 chỉ số,    │ │
│  │                │  │ KILL SWITCH)  │  │               │  │ dashboards)  │ │
│  └───────┬───────┘  └──────┬───────┘  └──────┬────────┘  └──────┬───────┘ │
│          │ cấp khoá         │ log+chặn        │ log+cấp          │ đọc log  │
└──────────│──────────────────│─────────────────│──────────────────│─────────┘
           │                  │                 │                  │
           ▼                  ▼                 ▼                  ▼
┌──────────────────────── DATA PLANE (agent của user) ──────────────────────┐
│  Agent (build bằng Claude Code / Agent SDK), chạy trên VPS/hạ tầng của team │
│  Auth: đăng nhập SUBSCRIPTION riêng (OAuth) · KHÔNG API key                  │
│  Bắt buộc: plugin+hooks telemetry · skills = MCP tự khai báo                 │
│  → mọi request/tool/token được plugin ghi về collector; việc đi qua Lark    │
└────────────────────────────────────────────────────────────────────────────┘
                 │ trả lời qua Lark (bot)          ▲
                 ▼                                 │ events (usage, kết quả)
              Người dùng cuối  ───────────────────►  Lark
```

**Điểm mấu chốt để "nắm hết request":** người dùng không cầm khoá Anthropic thô.
Platform **cấp virtual key** cho mỗi người/agent; agent trỏ `ANTHROPIC_BASE_URL`
về **LLM Gateway** của platform. Mọi request đi qua gateway → log token, nội dung,
áp budget, và **revoke khoá = deactivate ngay** dù code agent không đổi.

---

## 3. Thành phần platform

| Thành phần | Vai trò | Trạng thái |
|-----------|---------|-----------|
| **Onboarding & Registry** | Đăng ký user/phòng ban/squad/agent; cấp **telemetry key** + cài plugin (không cấp API/virtual key vì dùng subscription) | registry `agents` đã có; cần mở rộng |
| **Claude Code plugin + hooks** | Bắt buộc nhúng khi tạo agent; ghi mọi request/tool/token → collector | **mới** (control point chính) |
| **Collector** | Nhận trace từ plugin/SDK, lưu kho trace | ✅ đã deploy (`/opt/lsr-platform`) |
| **LLM Gateway (LiteLLM)** | *Tuỳ chọn* — chỉ cho agent nào dùng API key; không bắt buộc khi dùng subscription | đã deploy nhưng **hạ xuống optional** |
| **Skill Registry** | Đăng ký + log danh sách MCP mỗi agent (MCP tự do); đo mức dùng qua telemetry | **mới** |
| **Governance & Evaluation** | Ingest log → trace → chấm điểm 2 nhánh, đo 6 chỉ số, auto-deactivate | `evaluation`, `telemetry`, `agent_testing` đã có |
| **Reporting** | 6 dashboard/báo cáo | `reporting` đã có (prototype) |
| **Lark integration** | Bot nhận việc/trả kết quả; Base = master data | khung `lark/` đã có |

---

## 4. Vòng đời onboarding (qua Claude Code)

> **Chi tiết trải nghiệm tạo agent (lệnh, artifact, platform cấp gì):**
> [CREATE_AGENT.md](CREATE_AGENT.md).

1. **Khởi tạo:** user mở Claude Code, dùng plugin `lsr-agent init` → scaffold agent.
2. **Đăng ký + cấp khoá:** `lsr-agent register` → tạo record `agents` + platform cấp
   `TELEMETRY_API_KEY` và **cài Claude Code plugin telemetry**. Agent tự **đăng nhập
   subscription** (`claude login` / `setup-token`) — không cấp API/virtual key.
3. **Kết nối Lark:** `lsr-agent lark connect` → chọn **bot** hoặc **user account** →
   authorize (add bot + event subscription, hoặc OAuth user). Xem CREATE_AGENT §3.5.
4. **Khai báo skill:** `lsr-agent skill add <mcp>` → log danh sách MCP (tự do, không duyệt).
5. **Pre-golive test:** `lsr-agent test` (bộ test có nhãn) → phải pass.
6. **Golive:** `lsr-agent golive` → `status = active`, mở budget, gắn bot Lark.
7. **Vận hành:** platform đo liên tục; fail/vượt chính sách → **auto-deactivate**
   (revoke virtual key + `agents.status=deactivated`).

---

## 5. Cơ chế "nắm hết request" + deactivate

Vì dùng subscription (không API key), control point là **plugin bắt buộc + Lark**:

| Loại request | Đi qua | Platform thu được | Cắt bằng |
|--------------|--------|-------------------|----------|
| Lời gọi LLM | Claude Code plugin / Telemetry SDK | token (usage), model, prompt/response (tuỳ chính sách), latency | dừng process + thu hồi đăng ký |
| Lời gọi skill/tool | Hooks + Telemetry SDK | tên skill, tham số, kết quả, lỗi | dừng process + thu hồi đăng ký |
| Nhận việc / trả kết quả | Lark bot | invocation, kết quả cuối, phản hồi 👍/👎 | **gỡ bot khỏi nhóm / thu hồi Lark auth** |

Ba nguồn này ghép thành `AgentRunTrace` (đã có trong `telemetry/`) → tính token,
6 chỉ số hành vi tool, và feed scorer.

**Kill switch (deactivate) — vì không có virtual key để revoke:**
1. **Cắt Lark** (mạnh nhất): gỡ bot khỏi nhóm / thu hồi Lark auth → agent không
   nhận & không trả việc được, bất kể LLM auth của nó.
2. **Dừng process** agent (nếu platform quản lý host / systemd unit).
3. **Thu hồi đăng ký + telemetry key**: collector từ chối trace → agent coi như
   ngoài governance → cảnh báo + chặn golive lại.

> Token là **soft-enforce** (đo qua telemetry + `TokenBudget` trong SDK dừng agent
> khi vượt), KHÔNG phải hard-cap theo billing như virtual key (subscription không
> cho cắt token ở tầng Anthropic).

---

## 6. Skill: MCP tự do (khai báo → log → đo)

Theo quyết định đã chốt (§12), skill = **MCP tự do**:
- **Khai báo**: user tự gắn MCP bất kỳ cho agent (`lsr-agent skill add`).
- **Log/đăng ký**: platform ghi danh sách MCP của mỗi agent (`agent_mcp_skills`) —
  **không bắt duyệt**.
- **Đo**: vì gateway KHÔNG proxy tool, lời gọi skill được đo qua **Telemetry SDK**
  (bắt buộc nhúng) → vào `skill_score` và 6 chỉ số hành vi tool.

> Đánh đổi: linh hoạt cao, nhưng governance ở tầng tool dựa vào SDK. Agent không
> gửi trace = không cho golive (đây là ràng buộc thay cho "duyệt skill").

---

## 7. Squad ↔ Agent & đánh giá squad qua agent

- **Ràng buộc:** mỗi squad phải có **≥ 1 agent** (một agent được đánh dấu là
  *squad agent* chính). Không có agent → squad không đủ điều kiện đánh giá.
- **Đo squad qua squad agent:** kết quả/tiến độ mục tiêu của squad được **thu qua
  squad agent** — squad agent là đầu mối truy vấn dữ liệu (BigQuery/Lark), tổng hợp
  và báo cáo KR. `squad_objectives.actual` lấy từ output của squad agent thay vì
  query trực tiếp.
- **Liên đới sức khỏe:** squad agent bị deactivate → squad mất kênh đo → cảnh báo.
  (Mức độ ảnh hưởng của điểm agent lên điểm squad: **cần confirm** — xem §12.)

---

## 8. Đánh giá & Dashboard (giữ nguyên, mở rộng)

- **Squad scorer / Agent scorer**: giữ như hiện tại.
- **Bổ sung Agent Detail**: token/kỳ, 6 chỉ số hành vi tool, mức dùng skill.
- **Bổ sung màn hình platform**: Skill Registry (danh sách MCP mỗi agent), Gateway/Token
  usage, Onboarding queue. (Nâng từ 6 → ~8 màn hình.)

---

## 9. Bảo mật & tách biệt

- Mỗi user/agent có **định danh + khoá riêng**; không ai cầm khoá Anthropic thô.
- Phân quyền theo phòng ban/squad; skill nhạy cảm cần duyệt.
- Log request có thể chứa dữ liệu nhạy cảm → chính sách lưu/ẩn (PII), phạm vi
  người xem log. Cần thống nhất với nội bộ.

---

## 10. Master data thay đổi (tóm tắt — chi tiết hoá sau confirm)

Thêm/mở rộng trên Lark Base (hoặc DB của platform):

| Bảng | Ghi chú |
|------|---------|
| `users` / `departments` | người tạo agent, phòng ban, quyền |
| `agents` (mở rộng) | + `owner_user`, `connect_mode` (bot/user), `gateway_key_id`, `is_squad_agent` |
| `squads` (mở rộng) | + `primary_agent_id` (ràng buộc ≥1 agent) |
| `agent_mcp_skills` | danh sách MCP mỗi agent khai báo (tự do, chỉ log) |
| `gateway_keys` | virtual key, budget, trạng thái (active/revoked) |
| `agent_traces` / `agent_task_labels` / `agent_behavior_metrics` | như AGENT_INTEGRATION §6 |

---

## 10b. Hạ tầng (GCP)

Backend platform triển khai trên **GCP Compute Engine**: project `ganesha-381907`,
zone `asia-southeast1-b`, instance `digital-transformation-hosting`. Các service
(LiteLLM Gateway, Collector, Platform API, Scorer/Dashboard) chạy trên VM này sau
reverse proxy + TLS. SSH & bố trí service: [infra/DEPLOY.md](infra/DEPLOY.md).

---

## 10c. Bổ sung phạm vi (mới — chờ triển khai)

### (1) Đăng ký agent CÓ SẴN từ dự án khác (external agents)
Agent đã chạy ở repo/hạ tầng khác (không trên VM/Vercel của platform) vẫn **đăng ký
được**, **giữ nguyên cấu hình**, platform chỉ **quan sát + điều phối**.

- **Chế độ triển khai** thêm trường `deployment`: `managed` (platform host) |
  **`external`** (team tự host). External thì platform **không** đụng vào runtime.
- **Adopt bằng 1 lệnh** trong repo sẵn có: `lsr-agent adopt` →
  (a) sinh `lsr-agent.yaml` từ cấu hình đang có (không sửa code), (b) cài **plugin
  telemetry** cho Claude Code, (c) gọi `/v1/agents/register` với `deployment=external`
  → nhận `TELEMETRY_API_KEY`; owner vẫn dùng **subscription của mình**.
- **Nắm được để lên dashboard**: agent gửi trace (token, tool, output) về collector;
  platform hiển thị usage/kết quả/test như agent managed.
- **Giới hạn cần nói rõ**: với external, platform **không kill process được** — cơ chế
  cắt là: thu hồi telemetry key + **cắt kết nối Lark** (xem (2)) + đánh dấu
  `deactivated` trên dashboard (bot không nhận/không trả việc được nữa).
- **Vẫn code thêm bằng Claude Code**: repo của team giữ nguyên; chỉ thêm plugin +
  manifest, CI chuẩn chạy được nếu họ copy `tests/test_agent_standards.py`.

### (2) Platform kết nối Lark bằng tài khoản admin (activate/deactivate đồng bộ)
Khi platform bật/tắt agent → **bot/account Lark tương ứng cũng bật/tắt**.
**Nguyên tắc tuyệt đối: KHÔNG xoá bất kỳ dữ liệu nào** (chỉ thay đổi trạng thái/quyền).

- **App admin riêng** của platform (khác app của từng agent) với scope quản trị
  (contact/user admin, chat member admin).
- **Deactivate agent** → theo `connect_mode`:
  - `bot`: **gỡ bot khỏi các chat** đang phục vụ (giữ nguyên lịch sử tin nhắn) +
    ghi lại danh sách `chat_id` để khôi phục.
  - `user`: **thu hồi quyền/đình chỉ đăng nhập** tài khoản đó (không xoá user, không
    xoá dữ liệu, không "resign").
- **Activate lại** → add bot trở lại đúng các chat đã lưu / khôi phục quyền.
- **Audit**: mọi thao tác ghi `lark_admin_actions` (ai, khi nào, agent nào, trước/sau).
- ⚠️ **Cần xác nhận khả thi**: Lark Open Platform **không có API public để bật/tắt một
  Custom App**; việc disable app phải làm trong Admin Console. Vì vậy cơ chế khả thi
  là **gỡ/khôi phục bot khỏi chat + thu hồi token**, và với user account là **đình chỉ
  đăng nhập**. Sẽ xác minh scope thực tế khi có app admin.

### (3) Second brain của team (bảng chung, không rải rác)
Agent phục vụ squad/chapter/team cần biết **ai trong team, làm gì, phối hợp thế nào**.
Dùng **bảng chung của platform** (không mỗi agent một nơi):

| Bảng | Nội dung |
|------|----------|
| `teams` | team_id, loại (squad/chapter/team), tên, mục tiêu, lead, kênh Lark |
| `team_members` | team_id, họ tên, `lark_user_id`, vai trò, chuyên môn, backup, giờ làm việc |
| `team_kpis` | team_id, tên KPI, đơn vị, **công thức**, nguồn dữ liệu, target, kỳ, trọng số |
| `team_context` | "second brain": ghi chú, quy ước, quyết định, cách phối hợp (dạng md + tags) |

- Agent **đọc qua Platform API** (`GET /v1/teams/{id}/brain`) — không nhồi vào memory,
  tra cứu khi cần (đúng nguyên tắc chống long-memory).
- Nguồn nạp: **checklist golive** (mục B, C) + cập nhật dần từ Minh Anh (biên bản họp)
  và quản lý team.

### (4) Checklist golive bắt buộc
Xem đầy đủ: **[GOLIVE_CHECKLIST.md](GOLIVE_CHECKLIST.md)** — 8 nhóm (định danh/sở hữu,
con người & phối hợp, KPI & cách tính, phạm vi dữ liệu, kết nối & auth, chất lượng &
an toàn, vận hành sau golive, tuân thủ). Platform **chặn golive** nếu thiếu mục bắt
buộc; dữ liệu nộp vào chảy thẳng vào **second brain** (3) và bảng KPI.

---

## 11. Lộ trình

### Giai đoạn 0 — Chốt thiết kế (đang ở đây)
- [ ] Confirm kiến trúc platform (§12).

### Giai đoạn 1 — Control plane tối thiểu
- [x] Collector nhận trace (đã deploy) + LiteLLM gateway optional (đã deploy).
- Platform API + Registry mở rộng; cấp `TELEMETRY_API_KEY`.
- Claude Code plugin + hooks telemetry (control point chính).
- Ingest trace → token + 6 chỉ số → dashboard.

### Giai đoạn 2 — Self-service
- [x] **Platform API** (register agent, cấp telemetry key, active/deactivate) — đã deploy.
- [x] Hook `on_agent_registered` → **Minh Anh share từ điển meeting-notes** (live).
- [x] Resource Index + Meeting agent Minh Anh + client transcript Whisper.
- Template Claude Code (`lsr-agent init`) gọi Platform API.
- Pre-golive test + auto-deactivate end-to-end.

### Giai đoạn 3 — Đánh giá đầy đủ
- Squad qua squad agent; 6 chỉ số + LLM judge; đủ dashboard platform.

### Giai đoạn 4 — Vận hành
- Multi-team, quota, cảnh báo, báo cáo định kỳ.

### Giai đoạn 5 — Phạm vi mới (§10c) + tính năng đã chọn (§11b)
Thứ tự đã chốt: **Second brain + checklist golive trước**, rồi external agents, rồi Lark admin.
- [x] **Second brain + checklist golive**: bảng chung `teams`/`team_members`/`team_kpis`/
      `team_context` + `agent_golive_checklist`; API `/v1/teams/*`, `/v1/teams/{id}/brain`,
      `/v1/agents/{id}/golive-checklist`; **gate chặn golive** khi thiếu mục bắt buộc.
- [ ] Đăng ký **agent external** (`deployment=external`, `lsr-agent adopt`).
- [ ] **Lark admin** đồng bộ de/activate (cần app admin + scope).

**Tính năng đã chọn (cả 4 nhóm) — thứ tự đề xuất:**
1. *Vận hành & tin cậy*: cost/quota theo agent → health monitor + cảnh báo Lark →
   versioning/rollback prompt → staging/canary.
2. *Chất lượng & học hỏi*: human feedback 👍/👎 có lý do → golden set + regression test →
   LLM judge (RIR/OFR/CTRL-Acc) → marketplace prompt/skill.
3. *Kiến thức & phối hợp*: semantic search resource index → second brain toàn công ty →
   agent-to-agent handoff.
4. *Quản trị & tuân thủ*: audit log toàn platform → RBAC theo phòng ban → PII guard →
   data retention.

---

## 11b. Đề xuất tính năng agent platform (ứng viên — chọn rồi mới đưa vào lộ trình)

Nhóm theo giá trị; ✅ = đã có, còn lại là đề xuất.

**Vận hành & tin cậy**
1. **Cost & quota theo agent/squad** — trần token/chi phí ngày–tháng, cảnh báo khi vọt.
2. **Health monitor + cảnh báo Lark** — agent lỗi/không phản hồi/usage tụt → báo owner.
3. **Kill switch tức thời + lịch sử** — tắt agent 1 nút, có audit ai tắt/khi nào (đã có nền).
4. **Versioning & rollback prompt/config** — mỗi lần sửa system prompt/skill là 1 version,
   quay lại được bản trước.
5. **Staging/canary** — thử agent với nhóm nhỏ trước khi mở toàn team.

**Chất lượng & học hỏi**
6. **Human feedback loop** — 👍/👎 + lý do trên từng câu trả lời trong Lark → vào điểm chất lượng.
7. **Golden set & regression test** — bộ câu hỏi chuẩn, chạy lại mỗi lần đổi prompt để
   phát hiện tụt chất lượng.
8. **LLM judge cho RIR/OFR/CTRL-Acc** — chấm ngữ nghĩa tự động (đang để nhãn tay).
9. **Prompt/skill marketplace nội bộ** — chia sẻ prompt/MCP tốt giữa các team.

**Kiến thức & phối hợp**
10. **Second brain toàn công ty** (ngoài team) — thuật ngữ, quy trình, quyết định chung.
11. **Agent-to-agent handoff** — agent chuyển việc cho agent khác (vd Minh Anh → agent squad).
12. **Semantic search trên resource index** — tìm theo ngữ nghĩa thay vì từ khoá.

**Quản trị & tuân thủ**
13. **RBAC & phân quyền theo phòng ban** — ai xem/sửa/tắt agent nào.
14. **Audit log toàn platform** — mọi thao tác admin, xem được, không xoá.
15. **PII guard** — tự phát hiện/che dữ liệu nhạy cảm trong trace & log.
16. **Data retention policy** — tự dọn trace cũ theo chính sách.

**Trải nghiệm**
17. **Agent catalog cho nhân viên** — "cửa hàng" agent nội bộ: agent nào làm được gì, dùng thế nào.
18. **Onboarding wizard** — hướng dẫn tạo agent từng bước trên UI (thay vì CLI).
19. **Báo cáo định kỳ tự động** — tuần/tháng gửi Lark: hiệu quả squad, top agent, agent cần xử lý.
20. **Chat trực tiếp với agent trên dashboard** — thử nhanh không cần vào Lark.

---

## 12. Quyết định đã chốt & còn mở

**Đã chốt:**
1. **Auth = Claude Agent SDK subscription riêng (OAuth), KHÔNG API key.**
   → *thay thế* quyết định "Gateway bắt buộc/virtual key" trước đây.
2. **Control point = Claude Code plugin + Telemetry SDK bắt buộc** (nắm request/
   tool/token) + **Lark là kênh việc**. Kill switch = cắt Lark + dừng process +
   thu hồi đăng ký (không revoke virtual key nữa).
3. **Squad ↔ agent = chỉ là kênh dữ liệu.** Squad agent là đầu mối đo/báo cáo KR;
   điểm squad = hiệu quả mục tiêu, **không** cộng điểm agent. (Vẫn ràng buộc ≥1 agent.)
4. **Skill = MCP tự do.** User tự gắn MCP bất kỳ; platform **đăng ký + log** chứ
   không bắt duyệt.
5. **LiteLLM Gateway = optional**, đã deploy — chỉ dùng cho agent nào chọn API key;
   không bắt buộc khi dùng subscription.

**Hệ quả quan trọng:**
> Không proxy được model call (subscription OAuth). Vì vậy **cả token lẫn dữ liệu
> tool cho 6 chỉ số đều lấy từ Telemetry SDK / plugin bắt buộc**. Template
> `lsr-agent init` phải gắn sẵn plugin+SDK; agent không gửi trace → không cho golive.
> Token là **soft-enforce** (đo + `TokenBudget` dừng agent), không hard-cap billing.

**Còn mở:**
6. Cơ chế headless auth subscription cho agent chạy trên VPS: `claude setup-token`
   của từng người (mỗi người 1 subscription) — cần confirm cách quản lý/luân chuyển.
7. Số phận LiteLLM gateway đã deploy: **giữ chạy (optional)** hay tắt để tiết kiệm?
8. Kết nối Lark: **bot** (khuyến nghị) hay có ca bắt buộc user account.
