# LSR Agent Platform — LamsonRetail

Nền tảng agent nội bộ: sau khi deploy, **các phòng ban/cá nhân dùng Claude Code
kết nối vào để tự tạo agent của mình**, tự yêu cầu thêm skill; mỗi người đăng nhập
**Claude Agent SDK riêng**. Nhưng nền tảng **nắm được toàn bộ request**, có cơ chế
**đánh giá / deactivate** agent, cùng **dashboard & báo cáo** đã xây.

> Đây là bản mở rộng từ "Rating Agent". Phần chấm điểm/governance/dashboard cũ giờ
> là **một subsystem** của platform. Chi tiết liên quan:
> [MASTER_DATA.md](MASTER_DATA.md) · [AGENT_INTEGRATION.md](AGENT_INTEGRATION.md).
> **PLAN này đang chờ confirm (xem §12) trước khi code tiếp.**

---

## 1. Nguyên tắc thiết kế

1. **Self-service, nhưng governed-by-default.** Ai cũng tạo được agent, nhưng mọi
   agent phải đăng ký, định danh, và đi qua control plane.
2. **Nắm hết bằng đường đi, không bằng niềm tin.** Mọi lời gọi LLM và skill đi qua
   hạ tầng của platform (gateway + skill hub) → platform thấy hết, đo được, và
   **cắt được** (kill switch) mà không cần sửa code của agent.
3. **Hai nhánh đánh giá giữ nguyên:** Squad (hiệu quả mục tiêu) và Agent
   (skill/usage/kết quả + test). **Mỗi squad ≥ 1 agent; kết quả squad đo qua agent
   của squad.**

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
│  Cấu hình: ANTHROPIC_BASE_URL = gateway · skills = MCP tự khai báo           │
│  → mọi model call & skill call đều xuyên qua control plane                   │
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
| **Onboarding & Registry** | Đăng ký user/phòng ban/squad/agent; cấp virtual key + skill token + telemetry key | registry `agents` đã có; cần mở rộng |
| **LLM Gateway** | Proxy trước Anthropic API: log mọi request, đếm token, áp budget/rate-limit, kill switch | **mới** (đề xuất LiteLLM tự host) |
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
   **virtual key** (ANTHROPIC_API_KEY) + `TELEMETRY_API_KEY`. `ANTHROPIC_BASE_URL`
   trỏ về gateway.
3. **Khai báo skill:** `lsr-agent skill add <mcp>` → log danh sách MCP (tự do, không duyệt).
4. **Pre-golive test:** `lsr-agent test` (bộ test có nhãn) → phải pass.
5. **Golive:** `lsr-agent golive` → `status = active`, mở budget, gắn bot Lark.
6. **Vận hành:** platform đo liên tục; fail/vượt chính sách → **auto-deactivate**
   (revoke virtual key + `agents.status=deactivated`).

---

## 5. Cơ chế "nắm hết request" + deactivate

| Loại request | Đi qua | Platform thu được | Cắt bằng |
|--------------|--------|-------------------|----------|
| Lời gọi LLM | LLM Gateway | prompt/response (tuỳ chính sách), token, model, latency | revoke virtual key |
| Lời gọi skill/tool | Telemetry SDK (không proxy) | tên skill, tham số, kết quả, lỗi | deactivate agent (revoke gateway key) |
| Nhận việc / trả kết quả | Lark bot | invocation, kết quả cuối, phản hồi 👍/👎 | gỡ bot khỏi nhóm |

Ba nguồn này ghép thành `AgentRunTrace` (đã có trong `telemetry/`) → tính token,
6 chỉ số hành vi tool, và feed scorer.

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

## 11. Lộ trình

### Giai đoạn 0 — Chốt thiết kế (đang ở đây)
- [ ] Confirm kiến trúc platform (§12).

### Giai đoạn 1 — Control plane tối thiểu
- Platform API + Registry mở rộng; cấp virtual key.
- LLM Gateway (log + budget + kill switch) — dùng được với 1 agent thật.
- Ingest log → trace → token + dashboard.

### Giai đoạn 2 — Self-service
- Template Claude Code (`lsr-agent init`) + luồng đăng ký/ xin skill.
- Skill Registry (khai báo + log MCP mỗi agent).
- Pre-golive test + auto-deactivate end-to-end.

### Giai đoạn 3 — Đánh giá đầy đủ
- Squad qua squad agent; 6 chỉ số + LLM judge; đủ dashboard platform.

### Giai đoạn 4 — Vận hành
- Multi-team, quota, cảnh báo, báo cáo định kỳ.

---

## 12. Quyết định đã chốt & còn mở

**Đã chốt (2026-07):**
1. **Control point = Gateway bắt buộc.** Mọi agent trỏ `ANTHROPIC_BASE_URL` về LLM
   Gateway của platform; virtual key + budget + kill switch. Đây là cách nắm hết
   token/request và deactivate chắc chắn.
2. **Định danh = platform cấp virtual key** cho mỗi người/agent (không ai cầm khoá
   Anthropic thô).
3. **Squad ↔ agent = chỉ là kênh dữ liệu.** Squad agent là đầu mối đo/báo cáo KR;
   điểm squad = hiệu quả mục tiêu như hiện tại, **không** cộng điểm agent. (Vẫn giữ
   ràng buộc squad phải có ≥1 agent để có kênh đo.)
4. **Skill = MCP tự do.** User tự gắn MCP bất kỳ cho agent; platform **đăng ký +
   log danh sách** chứ không bắt duyệt. → bỏ luồng `skill_requests`/duyệt.
5. **Gateway = LiteLLM tự host** trên VPS.

**Hệ quả quan trọng của (4) + (1):**
> Platform proxy **model call** (qua gateway) nhưng **không proxy tool/skill call**
> (MCP chạy trực tiếp giữa agent và server). Vì vậy **token** lấy từ gateway, còn
> **dữ liệu tool để tính 6 chỉ số** (TSR/CTUR/RIR/OFR/UTR) **phải lấy từ telemetry
> SDK bắt buộc nhúng trong agent**. Template `lsr-agent init` phải gắn sẵn SDK này;
> agent không gửi trace → coi như vi phạm, không cho golive.

**Còn mở:**
6. **Provider LLM** chính (mặc định Anthropic/Claude) để chuẩn hoá gateway + đọc token.
7. Kết nối Lark: **bot** (khuyến nghị) hay có ca bắt buộc user account (AGENT_INTEGRATION §2).
