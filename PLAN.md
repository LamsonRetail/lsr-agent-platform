# LSR Agent Platform — LamsonRetail

Nền tảng agent nội bộ: sau khi deploy, **các phòng ban/cá nhân dùng Claude Code
kết nối vào để tự tạo agent của mình**, tự yêu cầu thêm skill; mỗi người đăng nhập
**Claude Agent SDK riêng**. Nhưng nền tảng **nắm được toàn bộ request**, có cơ chế
**đánh giá / deactivate** agent, cùng **dashboard & báo cáo** đã xây.

> Đây là bản mở rộng từ "Rating Agent". Phần chấm điểm/governance/dashboard cũ giờ
> là **một subsystem** của platform. Chi tiết liên quan:
> [MASTER_DATA.md](MASTER_DATA.md) · [AGENT_INTEGRATION.md](AGENT_INTEGRATION.md).

> ⚠️ **Auth model (cập nhật 2026-08-11 — kiến trúc v3): subscription ladder.**
> Mỗi agent xác thực theo bậc thang: **① subscription RIÊNG của agent** (OAuth —
> `claude setup-token`) → **② pool subscription chung** (tự chuyển khi hết hạn mức,
> cooldown 5h) → **③ API key qua litellm** (chỉ khi mọi subscription cooldown; chọn
> model theo `model_fallback`, đo chi phí thật). Secrets chỉ nằm trên VM — DB giữ
> tham chiếu. Control point vẫn là **plugin/telemetry + kill switch**; thêm
> **Model Auth Broker** cấp lease. Xem [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 0. Plan hiện hành — Kiến trúc v3 (2026-08-11)

> Kiến trúc đầy đủ: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Phần dưới đây là
> lộ trình 7 phase đang chờ thực thi. Các mục §1–§9 phía sau là nền tảng đã xây
> (giữ làm ngữ cảnh). Trạng thái: ✓ đang chạy · ➕ mới.

Đã kiểm tra 7 use case và vá kiến trúc: (1) FE chat riêng qua Chat API chung,
(2) skill mới có metering, (3) sub riêng từng agent, (4) tự chuyển account khi hết
token, (5) context stateless + fallback API được chọn model, (6) platform agents +
human-in-the-loop, (7) agent-agent qua Directory/A2A.

### P1 — Ingress hợp nhất: Event Gateway + Router + Queue + Chat API *(UC1, nền UC7)*

**Các bước:**
1. Schema: `routing_binding`(app_id, chat_id, channel, agent_id, active) ·
   `jobs`(id, agent_id, channel, payload, status, priority, attempts, run_after, locked_by, locked_at) ·
   `job_events`(job_id, seq, kind, data — cho streaming) · `event_dedupe`(event_id PK, seen_at, TTL).
2. Service `event_gateway` (FastAPI, compose): webhook Lark per-app (verify+decrypt bằng
   key trong secrets VM) → dedupe → tra routing → INSERT jobs → ACK <1s. App chưa có
   webhook: adapter long-connection đẩy vào cùng hàm ingest.
3. Chat API: `POST /v1/chat/{agent_id}/messages` + `GET /v1/chat/{agent_id}/stream` (SSE đọc job_events).
4. Worker API: managed poll nội bộ; tự host dùng `GET /v1/self/jobs?wait=25` (SKIP LOCKED)
   + `POST /v1/self/jobs/{id}/complete|fail`.
5. Retry: attempts+1, run_after = now()+2^attempts×30s, quá 5 → DLQ; console tab Jobs/DLQ + Replay.
6. Di trú `minh_anh_bot` thành consumer đầu tiên.

**Đầu ra:** service event_gateway · 4 bảng · Chat API/SSE · Worker API · tab Routing+Jobs/DLQ · docs INGRESS.md.

**Test case:**
| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 1.1 | Nhắn Lark vào chat đã binding | ACK <1s; agent nhận job ≤2s; trace channel=lark |
| 1.2 | Lark retry cùng event_id ×3 | chỉ 1 job (dedupe) |
| 1.3 | Chat chưa binding | job "unrouted" + alert, không mất |
| 1.4 | 2 chat → 2 agent, đồng thời | đúng agent nhận đúng job |
| 1.5 | Kill container giữa job | lock hết hạn → retry → DLQ sau 5 lần → Replay OK |
| 1.6 | FE riêng gửi Chat API, nhận SSE | reply stream; trace/quota như Lark; không có đường gọi thẳng runtime |
| 1.7 | Agent mới + 1 dòng routing | nhận sự kiện ngay, không sửa gateway |
| 1.8 | Deactive rồi nhắn | job rejected, không consume |

### P2 — Model Auth Broker: sub riêng · pool · fallback API *(UC3·4·5-ladder)*

**Các bước:**
1. Schema: `model_credentials`(id, kind=subscription|api_key, owner_email, secret_ref,
   status=active|cooldown|disabled, cooldown_until, priority, note) + `agents.auth_mode`(own|pool|api),
   `agents.credential_id`.
2. Secrets: mỗi credential = file `/opt/lsr-platform/secrets/model/<id>.env`; DB chỉ giữ ref;
   script `add-model-credential.sh` chạy trên VM.
3. Broker: `POST /v1/self/model-auth/lease` (ladder own→pool→api trả base_url litellm +
   model theo `agent_versions.model_fallback`) · `POST /v1/self/model-auth/report`
   (limit/429 → cooldown tới hết cửa sổ 5h + audit).
4. agent_runner: lease lúc start; wrapper bắt limit → report → re-lease → retry job (job còn trong queue).
5. litellm: model list + spend log; đường API bắt buộc qua litellm.
6. Console tab Model Auth: pool/cooldown/agent-đang-dùng-gì; alert pool cạn.

**Đầu ra:** bảng credentials + ladder API · script VM · runner re-lease tự động · litellm spend · tab Model Auth · docs MODEL_AUTH.md.

**Test case:**
| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 2.1 | auth_mode=own chạy job | lease đúng sub riêng (audit credential_id) |
| 2.2 | Disable credential riêng | tự rơi xuống pool, job vẫn xong |
| 2.3 | Giả lập 429 account A | A cooldown; lease account B; retry OK |
| 2.4 | Mọi sub cooldown | dùng api_key litellm; model=model_fallback; spend ghi nhận |
| 2.5 | Hết cooldown | account về pool, ưu tiên lại sub |
| 2.6 | Pool cạn + không API | fail lỗi rõ + alert Lark ngay |
| 2.7 | Grep secret trong DB/API/log | không lộ token ngoài file VM |
| 2.8 | Đổi account giữa hội thoại | ngữ cảnh giữ nguyên (state ở platform) |

### P3 — Agent Versions + Builder + eval gate *(UC2-skill, kiểm soát hiệu quả)*

**Các bước:**
1. `agent_versions`(agent_id, version, instruction_block, skills, model, model_fallback,
   tool_grants, publication=draft|dev|stg|prod, created_by, created_at) — thay con trỏ prompt_version.
2. Runner đọc version theo môi trường khi nhận job — đổi version không rebuild.
3. Publish → sync `skills` vào brain_skills + Directory.
4. Console Builder: sửa instruction/model/skill → draft → Publish (admin, X-Actor).
5. Eval gate: publish prod phải pass regression golden (harness sẵn có); fail → chặn + diff.
6. Rollback = trỏ lại version trước, có audit.

**Đầu ra:** bảng + API CRUD/publish/rollback · hot-reload version · tab Builder · gate nối regression_runs · migration từ prompt_version.

**Test case:**
| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 3.1 | Sửa instruction | tạo draft; agent chạy không đổi |
| 3.2 | Publish dev | chỉ dev đổi; prod nguyên |
| 3.3 | Publish prod khi golden fail | chặn + hiện case fail + audit |
| 3.4 | Publish prod khi pass | áp dụng ở job kế; audit ai-publish-gì |
| 3.5 | Rollback 1 click | version trước chạy lại ngay |
| 3.6 | Version khai skill mới | hiện ở brain_skills + Directory |

### P4 — Context Compiler + Session Memory + RAG *(UC5-context)*

**Các bước:**
1. `sessions`(session_id, agent_id, channel, user_ref, rolling_summary, last_turns, updated_at)
   + `user_facts`(agent_id, user_ref, fact, source, updated_at); retention nối retention_config.
2. Context Compiler (lib chung + mẫu cho tự host): prompt = instruction(version) + rolling_summary
   + N lượt cuối + user_facts + RAG top-k — mỗi call LLM độc lập.
3. Sau reply: nén summary bằng model rẻ (haiku qua ladder); extract facts có nguồn.
4. RAG: pgvector cho brain_items + `GET /v1/self/brain/search?q=` (kèm source_url).
5. Auto-sync Lark Doc được đánh dấu → brain draft chờ duyệt.

**Đầu ra:** 2 bảng · lib compiler + docs · pgvector + search API · cron sync Doc · purge nối retention.

**Test case:**
| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 4.1 | 2 câu nối nhau 1 session | câu 2 hiểu ngữ cảnh dù 2 call độc lập |
| 4.2 | Restart runner giữa hội thoại | session tiếp tục đúng |
| 4.3 | Hỏi khớp tri thức brain | trả lời kèm source_url |
| 4.4 | Hội thoại 50 lượt | prompt không phình; token/call ổn định |
| 4.5 | Fact ở session cũ, mở session mới | agent vẫn biết (user_facts) |
| 4.6 | TTL ngắn → chờ purge | xoá đúng hạn + audit |

### P5 — Connector Registry + usage metering *(UC2-log·chi phí)*

**Các bước:**
1. `connectors`(id, kind, config_ref, status) + `connector_grants`(agent_id, connector_id, scope,
   granted_by) + `tool_usage`(agent_id, connector, tool, job_id, latency_ms, ok, error, tokens_est, created_at).
2. Chuẩn adapter (mẫu lsr_lark): auth·rate-limit·error-map·audit·metering; kiểm grant tại API —
   thu quyền chặn ngay.
3. Migrate Lark + BigQuery vào registry; skeleton Web/Search, Social, Sapo/Misa.
4. Metering: hooks + runner ghi từng tool call; bq_sink export thêm tool_usage.
5. Console tab Connectors: grant + biểu đồ usage.

**Đầu ra:** registry + grants + tool_usage · CONNECTOR.md · 2 migrate + 3 skeleton · console.

**Test case:**
| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 5.1 | Gọi connector chưa grant | 403 + audit + error-map rõ |
| 5.2 | Cấp grant → gọi lại | chạy ngay, không restart |
| 5.3 | Thu grant giữa chừng | call kế bị chặn ngay |
| 5.4 | Skill/tool mới (UC2) | mỗi call có dòng tool_usage — thấy tần suất/lỗi/chi phí theo skill |
| 5.5 | Thêm connector mock | chỉ đăng ký adapter, không sửa core/agent |
| 5.6 | Connector bị rate-limit ngoài | retry backoff; agent không sập; usage ghi lỗi |

### P6 — Agent Directory + A2A *(UC7)*

**Các bước:**
1. `GET /v1/self/directory`: agent active + skills + domains + status.
2. `a2a_grants`(caller_id, target_id, scope, granted_by) — mặc định deny.
3. `POST /v1/self/a2a/{target}` {task, payload, timeout} → enqueue channel=a2a + reply_to;
   caller poll `GET /v1/self/a2a/{req_id}`.
4. hop_count ≤3, TTL, cấm self-call; caller-pays trong mart.
5. Audit 2 chiều (a2a_call / a2a_serve, khớp req_id).

**Đầu ra:** Directory API · grants + console · A2A qua queue · A2A.md kèm mẫu code tự host.

**Test case:**
| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 6.1 | AG-A đọc directory | thấy AG-B + skill; không thấy agent deactive |
| 6.2 | A gọi B (có grant) | nhận kết quả; trace/audit 2 phía khớp req_id |
| 6.3 | A gọi C (không grant) | 403 + audit denied |
| 6.4 | Vòng A→B→A | hop 3 chặn, không treo queue |
| 6.5 | Target deactive | lỗi "target inactive" ngay, không enqueue |
| 6.6 | Chi phí lượt A2A | tính cho caller trong mart |

### P7 — Platform agents (AG-OPS · AG-EVAL) + HITL + Mart *(UC6)*

**Các bước:**
1. HITL: `pending_actions`(id, proposed_by, action, params, risk=low|high, status, approver,
   expires_at) + card Lark Duyệt/Từ chối (action → gateway → thực thi). Low tự chạy + log;
   high phải duyệt; proposer ≠ approver.
2. AG-OPS: đọc health/cost/DLQ/pool qua admin-tool API — alert kèm chẩn đoán, đề xuất pause
   agent lỗi, xoay credential, replay DLQ, điều phối tải (priority/phân vùng).
3. AG-EVAL: golden định kỳ trên prod + sample chấm chất lượng thật (LLM judge);
   điểm giảm → đề xuất rollback (HITL).
4. Mart: BigQuery scheduled queries — dim(agent, version, kênh, tool, credential, ngày) +
   fact(runs, tokens, cost ước + cost API thật, lỗi, điểm eval) → dashboard KPI + alert ngưỡng.
5. Web chat console (nếu còn thời lượng) chạy trên Chat API P1.

**Đầu ra:** pending_actions + card HITL · AG-OPS/AG-EVAL đăng ký như agent thường · mart + KPI dashboard · runbook.

**Test case:**
| # | Kịch bản | Kỳ vọng |
|---|---|---|
| 7.1 | DLQ vượt ngưỡng | AG-OPS alert ≤5 phút kèm chẩn đoán |
| 7.2 | Đề xuất deactive (high) | card Lark → Duyệt thì thực thi; Từ chối thì thôi; audit đủ |
| 7.3 | Action quá hạn | expire + nhắc 1 lần |
| 7.4 | Điểm prod giảm sau publish | AG-EVAL cảnh báo + đề xuất rollback |
| 7.5 | Đối chiếu mart 1 tuần với dữ liệu thô | lệch ≤1% |
| 7.6 | Platform agent tự duyệt việc mình | bị chặn + audit attempt |
| 7.7 | Pool còn 1 account | cảnh báo sớm trước khi rơi xuống API |

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
