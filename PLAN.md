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
│  │ Onboarding &   │  │  LLM Gateway  │  │  Skill Hub    │  │ Governance & │ │
│  │ Registry       │  │ (proxy model, │  │ (MCP skills,  │  │ Evaluation   │ │
│  │ (agents,users, │  │ virtual key,  │  │ request→cấp,  │  │ (scorer,test,│ │
│  │ squads, keys)  │  │ token+budget, │  │ meter usage)  │  │ 6 chỉ số,    │ │
│  │                │  │ KILL SWITCH)  │  │               │  │ dashboards)  │ │
│  └───────┬───────┘  └──────┬───────┘  └──────┬────────┘  └──────┬───────┘ │
│          │ cấp khoá         │ log+chặn        │ log+cấp          │ đọc log  │
└──────────│──────────────────│─────────────────│──────────────────│─────────┘
           │                  │                 │                  │
           ▼                  ▼                 ▼                  ▼
┌──────────────────────── DATA PLANE (agent của user) ──────────────────────┐
│  Agent (build bằng Claude Code / Agent SDK), chạy trên VPS/hạ tầng của team │
│  Cấu hình: ANTHROPIC_BASE_URL = gateway · skills = MCP của Skill Hub        │
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
| **Skill Hub** | Catalog skill (MCP server/tool); luồng request→duyệt→cấp; đo mức dùng | **mới** |
| **Governance & Evaluation** | Ingest log → trace → chấm điểm 2 nhánh, đo 6 chỉ số, auto-deactivate | `evaluation`, `telemetry`, `agent_testing` đã có |
| **Reporting** | 6 dashboard/báo cáo | `reporting` đã có (prototype) |
| **Lark integration** | Bot nhận việc/trả kết quả; Base = master data | khung `lark/` đã có |

---

## 4. Vòng đời onboarding (qua Claude Code)

1. **Khởi tạo:** user mở Claude Code, dùng template/plugin của platform
   (`lsr-agent init`) → scaffold agent + tạo record `agents` qua Platform API.
2. **Xin skill:** khai báo skill cần → tạo `skill_requests` → Skill Hub duyệt.
3. **Cấp khoá:** platform cấp `GATEWAY_VIRTUAL_KEY` (+ budget), `SKILL_TOKEN`,
   `TELEMETRY_API_KEY`. Agent cấu hình `ANTHROPIC_BASE_URL` = gateway.
4. **Pre-golive test:** chạy bộ test (có nhãn) → phải pass.
5. **Golive:** `status = active`. Từ đây mọi request đi qua control plane.
6. **Vận hành:** platform đo liên tục; fail test/vượt chính sách → **auto-deactivate**
   (revoke virtual key + set `agents.status=deactivated`).

---

## 5. Cơ chế "nắm hết request" + deactivate

| Loại request | Đi qua | Platform thu được | Cắt bằng |
|--------------|--------|-------------------|----------|
| Lời gọi LLM | LLM Gateway | prompt/response (tuỳ chính sách), token, model, latency | revoke virtual key |
| Lời gọi skill/tool | Skill Hub (MCP) | tên skill, tham số, kết quả, lỗi | revoke skill token |
| Nhận việc / trả kết quả | Lark bot | invocation, kết quả cuối, phản hồi 👍/👎 | gỡ bot khỏi nhóm |

Ba nguồn này ghép thành `AgentRunTrace` (đã có trong `telemetry/`) → tính token,
6 chỉ số hành vi tool, và feed scorer.

---

## 6. Skill: catalog → request → duyệt → cấp → đo

- **Catalog** (`agent_skills` mở rộng thành skill của platform): mỗi skill là một
  MCP server/tool platform host, có mô tả, phạm vi dữ liệu, mức rủi ro.
- **Request** (`skill_requests`): user xin skill cho agent → owner/admin duyệt.
- **Cấp**: Skill Hub phát token; agent kết nối MCP skill bằng token đó.
- **Đo**: mọi lời gọi skill được log → vào `skill_score` và các chỉ số tool.

Nhờ skill là MCP do platform host, "tự yêu cầu thêm skill" vẫn nằm trong tầm kiểm soát.

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
- **Bổ sung màn hình platform**: Skill Hub (catalog + request), Gateway/Token
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
| `agent_skills` (→ catalog) | skill của platform = MCP server/tool |
| `skill_requests` | luồng xin skill → duyệt |
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
- Skill Hub (MCP) + duyệt + cấp token.
- Pre-golive test + auto-deactivate end-to-end.

### Giai đoạn 3 — Đánh giá đầy đủ
- Squad qua squad agent; 6 chỉ số + LLM judge; đủ dashboard platform.

### Giai đoạn 4 — Vận hành
- Multi-team, quota, cảnh báo, báo cáo định kỳ.

---

## 12. Cần confirm trước khi làm tiếp

1. **Control point:** đồng ý bắt buộc **mọi agent đi qua LLM Gateway của platform**
   (virtual key, kill switch) — cách duy nhất "nắm hết + deactivate" chắc chắn?
   Hay chấp nhận mô hình telemetry-only (yếu hơn, dựa vào hợp tác)?
2. **Định danh/khoá:** platform **cấp virtual key** cho mỗi người (không cầm khoá
   Anthropic thô) — đúng ý "mỗi người login SDK riêng nhưng platform nắm hết"?
3. **Squad qua agent:** squad agent là **đầu mối đo/báo cáo KR** (đề xuất). Điểm
   agent có ảnh hưởng vào điểm squad không? (a) không, chỉ là kênh dữ liệu;
   (b) có, là một hệ số; (c) squad bị chặn đánh giá nếu squad agent bị deactivate.
4. **Skill:** skill = **MCP server do platform host** + luồng duyệt (đề xuất)?
5. **Hạ tầng gateway:** tự host **LiteLLM** trên VPS (gọn, mã nguồn mở) hay dùng
   dịch vụ khác?
6. **Provider LLM** chính (Anthropic/Claude?) để chuẩn hoá gateway + đọc token.
