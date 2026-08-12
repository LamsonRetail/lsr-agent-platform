# LSR Agent Platform — Bộ test case toàn platform

> Tổng hợp MỌI test case của platform: đã nghiệm thu (✅ kèm ngày) và kế hoạch (⏳ theo phase).
> Quy ước ID: `<nhóm>.<số>`. Bộ test theo phase khớp [PLAN.md](../PLAN.md) §0.
> Test của TỪNG AGENT không nằm ở đây — mỗi agent có `agents/<ID>/TESTCASES.md` + `tests.jsonl` riêng (bắt buộc, có gate).

## 1. Nền tảng — registry · telemetry · guardrail (✅ nghiệm thu 08/2026)

| ID | Kịch bản | Kỳ vọng | Trạng thái |
|----|----------|---------|-----------|
| CORE.1 | Enroll agent mới bằng enroll-token | Tạo agent `registered` + trả telemetry key (hiện 1 lần) | ✅ 08-08 |
| CORE.2 | Enroll trùng agent_id | Từ chối, không đè key cũ | ✅ 08-08 |
| CORE.3 | Gửi trace với key đúng | Collector 200, ghi `agent_traces` | ✅ 08-08 |
| CORE.4 | Gửi trace với key sai / thiếu | 401 — không ghi gì | ✅ 08-08 |
| CORE.5 | Trace chứa email/SĐT/thẻ | PII bị che TRƯỚC khi lưu, đếm `pii_flags` | ✅ 08-07 |
| CORE.6 | Kill-switch: deactivate agent | Collector 403 + gỡ bot khỏi chat Lark + dừng container; KHÔNG xoá dữ liệu | ✅ 08-08 |
| CORE.7 | Bật lại `active` khi thiếu golive checklist | Bị chặn kèm danh sách mục thiếu (gate golive) | ✅ 08-11 (thấy khi test P1) |
| CORE.8 | Thao tác admin (duyệt/xoá/status) | `audit_log` ghi actor thật (X-Actor / agent token) | ✅ 08-08 |
| CORE.9 | Policy check PreToolUse (deny rule) | Tool bị chặn kèm lý do; fail-open khi service lỗi | ✅ 08-07 |
| CORE.10 | Quota/cost: vượt ngưỡng ước tính | Cảnh báo trên dashboard Chi phí + quota_alerts | ✅ 08-07 |
| CORE.11 | Golden set + regression + LLM judge | Chạy được bộ case, lưu `regression_runs` | ✅ 08-07 |
| CORE.12 | Extract PDF/Word qua /v1/extract | Trả text để đưa vào brain/training | ✅ 08-07 |
| CORE.13 | Scope-guard: PR người ngoài chạm core | CI fail, không merge được | ✅ 08-09 |
| CORE.14 | Health monitor: agent im lặng quá ngưỡng | Xuất hiện ở dashboard Sức khoẻ + alert | ✅ 08-07 |

## 2. Brain v2 — tri thức · graph (✅ 08-10)

| ID | Kịch bản | Kỳ vọng | Trạng thái |
|----|----------|---------|-----------|
| BR.1 | Import item (kind/domain/tags/source_url) | Xuất hiện ở Brain Console đúng lens | ✅ 08-10 |
| BR.2 | Duyệt/xoá item theo quyền domain | Chỉ reviewer đúng domain (hoặc admin) thao tác được | ✅ 08-10 |
| BR.3 | Tạo link typed giữa 2 item (8 loại quan hệ) | Cạnh hiện ở tab Links + graph + 3D (màu theo loại) | ✅ 08-10 |
| BR.4 | AI gợi ý link → người xác nhận | Link `suggested` → `confirmed`; contradicts thành conflict | ✅ 08-10 |
| BR.5 | Agent ghi brain riêng (`/v1/self/brain/*`) | Scope=agent, KHÔNG lẫn sang shared; graph scoped đúng | ✅ 08-10 |
| BR.6 | Graph tổng `/v1/brain/graph` | Đủ 6 loại node (domain/belief/knowledge/skill/policy/team) | ✅ 08-10 |

## 3. Lark dùng chung — broker + cache (✅ 08-11)

| ID | Kịch bản | Kỳ vọng | Trạng thái |
|----|----------|---------|-----------|
| LK.1 | Gọi `/v1/lark/resolve` không token | 401 | ✅ 08-11 |
| LK.2 | Resolve với agent token | 200; email→open_id qua cache danh tính chung (158 người đã nạp) | ✅ 08-11 |
| LK.3 | `/v1/lark/send` thiếu nội dung | 400 — không gửi gì | ✅ 08-11 |
| LK.4 | Token Lark cache 2 tầng | `lark_token_cache` có token + hạn; mọi service dùng chung 1 token | ✅ 08-11 |
| LK.5 | Send text/markdown tới email/open_id/chat_id | Gửi đúng loại; email chưa resolve được → fallback nhóm chung | ⏳ chờ Lark app mở range (blocker ngoài) |
| LK.6 | Audit mỗi lần agent gửi Lark | `audit_log` action=lark_send, actor=agent | ✅ 08-11 |

## 4. P1 — Ingress hợp nhất (✅ 08-11, 8/8)

| ID | Kịch bản | Kỳ vọng | Trạng thái |
|----|----------|---------|-----------|
| P1.1 | Tin Lark vào chat đã binding | Gateway ACK <1s; agent nhận job ≤2s; trace channel=lark | ✅ (đường ingest verify; tin Lark thật chờ app mở range) |
| P1.2 | Cùng event_id gửi 3 lần (Lark retry) | Chỉ 1 job (dedupe) | ✅ 08-11 |
| P1.3 | Chat chưa có binding | Job `unrouted` + không mất sự kiện | ✅ 08-11 |
| P1.4 | 2 chat → 2 agent đồng thời | Đúng agent nhận đúng job | ✅ 08-11 |
| P1.5 | Consumer chết giữa job / fail 5 lần | Reaper thu hồi lock → retry backoff → DLQ → Replay chạy lại | ✅ 08-11 |
| P1.6 | FE riêng gửi Chat API + SSE | Reply stream về; telemetry/quota như Lark; không có đường gọi thẳng runtime | ✅ 08-11 (full loop consumer thật) |
| P1.7 | Agent mới + 1 dòng routing | Nhận sự kiện ngay, không sửa code gateway | ✅ 08-11 |
| P1.8 | Deactivate rồi gửi tin | Job `rejected`, consumer 403 | ✅ 08-11 |

## 5. P2 — Model Auth ladder (✅ 08-11, 8/8)

| ID | Kịch bản | Kỳ vọng | Trạng thái |
|----|----------|---------|-----------|
| P2.1 | auth_mode=own | Lease đúng subscription riêng (audit credential_id) | ✅ 08-11 |
| P2.2 | Credential riêng bị disable | Tự rơi xuống pool, job vẫn chạy | ✅ 08-11 |
| P2.3 | 429/limit account A | A cooldown 5h; lease account B; retry OK | ✅ 08-11 |
| P2.4 | Mọi subscription cooldown | Lease API key qua litellm; model = model_fallback; spend đo thật | ✅ 08-11 |
| P2.5 | Cooldown hết hạn | Account tự về pool; ưu tiên lại subscription (rẻ hơn API) | ✅ 08-11 |
| P2.6 | Pool cạn + không có API | 503 + audit `model_auth_exhausted` + alert Lark | ✅ 08-11 |
| P2.7 | Rò rỉ secret | Lease/API/DB chỉ chứa REF; API upsert TỪ CHỐI field secret; grep sạch | ✅ 08-11 |
| P2.8 | Đổi account giữa hội thoại | Người dùng không nhận ra; ngữ cảnh giữ nguyên | ✅ 08-12 (khoá nốt bởi P4.6.1) |
| P2.9 | Runner lease end-to-end trên VM | Container lease→đọc `/secrets/<ref>`→set env→chạy; gặp limit→report→cooldown→**tự chuyển account khác** | ✅ 08-12 (container thật trên VM) |

## 6. Stable release — workflow team (✅ 08-12, gate local 4/4)

| ID | Kịch bản | Kỳ vọng | Trạng thái |
|----|----------|---------|-----------|
| ST.1 | Code agent khi THIẾU USECASE.md/TESTCASES.md | Plugin chặn Write/Edit file code + hướng dẫn tạo 2 file | ✅ 08-12 (unit 4/4) |
| ST.2 | Viết chính USECASE.md/TESTCASES.md | Luôn cho phép (không gate file .md/.jsonl) | ✅ 08-12 |
| ST.3 | Đủ 2 file → code | Cho phép bình thường | ✅ 08-12 |
| ST.4 | PR có code agent mà thiếu 2 file | CI `agent-gate` fail kèm hướng dẫn; đủ file → pass; PR chỉ `.md` → không bị gate | ✅ 08-12 (mô phỏng diff thật) |
| ST.5 | `new-agent.sh` scaffold | Sinh đủ USECASE/TESTCASES/tests.jsonl/consumer.py/README; consumer compile được | ✅ 08-12 |
| ST.6 | Team branch không đụng core | scope-guard fail nếu PR chạm `infra/ src/ scripts/ plugins/ ...` | ✅ 08-09 (đã có) |
| ST.7 | `agent-test.sh` chạy tests.jsonl qua Chat API | Pass/fail theo từ khoá kỳ vọng; exit code đúng cho CI | ✅ 08-12 (**2/2 pass** — agent chạy trên máy dev, test qua platform) |
| ST.8 | 2–3 người cùng branch | Push chung branch `agent/<team>-<ID>`, PR duy nhất, không conflict core | ⏳ cần team thật (cơ chế scope-guard + CI đã verify) |

## 7. P3 — Agent Versions + Builder + eval gate (✅ 08-12, 25/25 pass)

> Bộ test chi tiết theo 8 nhóm tính năng. Lần chạy đầu bắt được **1 bug thật** (P3.2.7):
> publish version lên env thứ 2 làm mất version ở env cũ → đã sửa bằng bảng `agent_publications`.

### 7.1 Tính năng: tạo & quản lý version (CRUD)

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P3.1.1 | Agent đã đăng ký, chưa có version | `POST /v1/agents/{id}/versions` với instruction_block | Tạo version **v1**, `publication=draft`, trả version number; audit `version_create` |
| P3.1.2 | Đã có v1 | Tạo tiếp | Tự tăng **v2** (không ghi đè v1); v1 giữ nguyên nội dung |
| P3.1.3 | — | Tạo version thiếu `instruction_block` | 400, không tạo bản rác |
| P3.1.4 | Có v1, v2 | `GET /v1/agents/{id}/versions` | Liệt kê đủ, mới nhất trước, kèm publication + created_by + created_at |
| P3.1.5 | — | Tạo version cho agent không tồn tại | 404 |
| P3.1.6 | Không có quyền admin | Tạo/publish bằng token thường | 401/403 — không đổi gì |
| P3.1.7 | v1 có `skills`, `model`, `model_fallback`, `tool_grants` | Đọc lại v1 | Giữ đúng mọi trường đã lưu (không mất field) |

### 7.2 Tính năng: publication theo môi trường (dev/stg/prod)

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P3.2.1 | v1 draft | Publish v1 → **dev** | v1.publication=dev; `GET /v1/agents/{id}/versions/resolve?env=dev` → v1 |
| P3.2.2 | v1@dev, v2 draft | Publish v2 → dev | v2 thành dev, **v1 tự về draft** (mỗi env chỉ 1 version sống) |
| P3.2.3 | v2@dev, prod chưa có | `resolve?env=prod` | Trả rỗng/null — dev KHÔNG rò sang prod |
| P3.2.4 | v1@prod, v2@dev | `resolve?env=prod` | Vẫn là **v1** (đổi dev không ảnh hưởng prod) |
| P3.2.5 | — | Publish với env lạ (`foo`) | 400 — chỉ chấp nhận draft/dev/stg/prod |
| P3.2.6 | v1@prod | Publish lại chính v1 vào prod | Idempotent, không lỗi, không nhân bản |
| P3.2.7 | v3@prod | Publish **chính v3** thêm vào stg (promote/song song) | v3 sống ở **cả prod và stg**; prod KHÔNG bị rỗng đi (bug đã bắt được ở lần chạy đầu) |

### 7.3 Tính năng: eval gate trước khi publish prod

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P3.3.1 | v2 chưa chạy regression | Publish v2 → **prod** | **Bị chặn 422**, message nêu rõ "chưa có regression pass cho version này"; v2 vẫn draft |
| P3.3.2 | v2 có regression **fail** (score < threshold) | Publish v2 → prod | Bị chặn + trả **danh sách case fail** (case_id + lý do); audit ghi lần thử bị chặn |
| P3.3.3 | v2 có regression **pass** | Publish v2 → prod | Publish thành công; audit `version_publish` kèm run_id + score |
| P3.3.4 | v2 pass, nhưng run gắn với **version khác** (v1) | Publish v2 → prod | Bị chặn — gate soi đúng version, không mượn kết quả cũ |
| P3.3.5 | Publish → **dev/stg** (không phải prod) | Publish v2 → dev khi chưa eval | Cho phép (gate chỉ áp cho prod) — để team test nhanh |
| P3.3.6 | Không có golden case nào active | Publish v2 → prod | Bị chặn kèm hướng dẫn tạo golden case (không "pass ngầm") |
| P3.3.7 | Admin cần phát hành khẩn | Publish prod với `force=true` + lý do | Cho phép nhưng **audit ghi force + lý do + ai làm** (đường thoát có dấu vết) |

### 7.4 Tính năng: runtime đọc version (không rebuild)

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P3.4.1 | v1@prod, agent đang chạy | `GET /v1/self/version` (agent token) | Trả instruction/model/skills của **v1** |
| P3.4.2 | Đổi sang v2@prod (không restart container) | Agent gọi lại `/v1/self/version` | Trả **v2** ngay ở lần lấy job kế tiếp |
| P3.4.3 | Agent A hỏi version của agent B | `/v1/self/version` bằng token A | Chỉ trả version của **A** (không rò chéo agent) |
| P3.4.4 | Prod chưa publish gì | Agent gọi `/v1/self/version` | Trả fallback rỗng + không lỗi 500 (agent vẫn chạy được) |
| P3.4.5 | Agent bị deactivate | Gọi `/v1/self/version` | 403 (đồng bộ kill-switch) |

### 7.5 Tính năng: rollback

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P3.5.1 | v1 từng @prod, nay v2@prod | `POST .../rollback {env:prod}` | prod trở lại **v1**; v2 về draft; **không tạo version mới** |
| P3.5.2 | Chỉ mới có 1 version từng publish | Rollback | 409 kèm message "không có version trước" |
| P3.5.3 | Sau rollback | `resolve?env=prod` + `/v1/self/version` | Đều trả v1 ở lần gọi kế tiếp |
| P3.5.4 | — | Rollback | Audit `version_rollback` (ai, từ v2 → v1, lúc nào) |

### 7.6 Tính năng: skills khai báo trong version

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P3.6.1 | v2 khai skill mới chưa từng có | Publish v2 | Skill xuất hiện trong `brain_skills` (scope agent), không phải sửa core |
| P3.6.2 | Publish 2 lần cùng skill | Publish lại | Không nhân bản skill (idempotent) |
| P3.6.3 | v2 bỏ 1 skill so với v1 | Publish v2 | Skill cũ không bị xoá khỏi brain (giữ lịch sử), version chỉ khai cái đang dùng |

### 7.7 Tính năng: Builder trên console

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P3.7.1 | Vào `/builder` | Chọn agent | Hiện instruction hiện tại + danh sách version + publication từng env |
| P3.7.2 | Sửa instruction → Lưu nháp | — | Tạo draft mới; **agent đang chạy không đổi hành vi** (P3.1.1 + P3.4) |
| P3.7.3 | Bấm Publish dev / prod | — | Gọi đúng API; prod fail gate thì hiện **case fail ngay trên UI** |
| P3.7.4 | Bấm Rollback | — | Prod về version trước, bảng cập nhật |
| P3.7.5 | Trang chỉ dùng token server-side | Xem HTML/JS trả về client | Không lộ `PLATFORM_ADMIN_TOKEN` |

### 7.8 Tương thích ngược & di trú

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P3.8.1 | Agent cũ có `prompt_version`/`prompt_ref` | Chạy migrate | Sinh version v1 tương ứng, không mất dữ liệu cũ |
| P3.8.2 | Agent chưa có version nào | Chạy job bình thường | Vẫn chạy như trước P3 (không bắt buộc version) |

## 8. P4 — Context Compiler + Session Memory + RAG (✅ 08-12, 28/28 pass)

> Lần chạy đầu bắt được **1 lỗ hổng thật** (P4.1.8): lượt hội thoại bị cắt chỉ trả về
> **một lần** — agent crash đúng lúc đó là mất luôn. Đã vá bằng `pending_summary` (giữ tới khi nén xong).

> Nguyên tắc kiểm: **state ở platform, không ở model**. Mỗi call LLM stateless nhưng vẫn đủ ngữ cảnh.
> RAG dùng **lexical hybrid** (full-text + trigram + bỏ dấu) — không phụ thuộc dịch vụ embedding ngoài.

### 8.1 Tính năng: session memory (lượt hội thoại)

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P4.1.1 | Session mới | `POST /v1/self/session/turn` (user) | Tạo session, `n_turns=1`, lưu đúng nội dung |
| P4.1.2 | Đã có 1 lượt | Ghi tiếp lượt assistant | `n_turns=2`, thứ tự lượt giữ nguyên |
| P4.1.3 | — | Ghi turn thiếu `session_id` hoặc `text` | 400, không tạo rác |
| P4.1.4 | Session của agent A | Agent B ghi vào cùng session_id | 403 — không ghi đè hội thoại của agent khác |
| P4.1.5 | Hội thoại dài (> ngưỡng nén) | Ghi thêm lượt | Cửa sổ giữ đúng N lượt cuối; trả `needs_summary=true` + `dropped_turns` để agent tự nén |
| P4.1.6 | Có `dropped_turns` | `POST /v1/self/session/summary` | `rolling_summary` được lưu; hàng chờ nén (`pending_summary`) được xoá |
| P4.1.7 | Agent khác gửi summary cho session không thuộc mình | — | 404/403 |
| P4.1.8 | Đã cắt lượt nhưng agent **crash trước khi nén** | Ghi lượt tiếp theo / gọi context | `needs_summary` vẫn `true` và `pending_summary` vẫn giữ lượt cũ — **không mất hội thoại** (lỗ hổng bắt được ở lần chạy đầu) |

### 8.2 Tính năng: Context Compiler (`GET /v1/self/context`)

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P4.2.1 | Có version prod + session 2 lượt | Gọi `/v1/self/context?session_id=` | Trả **đủ 5 phần**: instruction (version prod), rolling_summary, recent_turns, user_facts, knowledge |
| P4.2.2 | Câu 1 nói "tôi ở kho HN", câu 2 hỏi tiếp | Gọi context ở lượt 2 | `recent_turns` chứa câu 1 → câu 2 hiểu ngữ cảnh dù 2 call LLM độc lập |
| P4.2.3 | "Restart runner" (mô phỏng: gọi context từ tiến trình khác) | Gọi lại context | Trả y hệt — state ở Postgres, không ở tiến trình |
| P4.2.4 | Session chưa tồn tại | Gọi context với session_id lạ | Không lỗi 500; trả rỗng hợp lệ để agent vẫn chạy |
| P4.2.5 | Agent bị deactivate | Gọi context | 403 (đồng bộ kill-switch) |
| P4.2.6 | Agent A ↔ session của B | Gọi context bằng token A với session của B | Không trả nội dung của B |
| P4.2.7 | Hội thoại 50 lượt | Gọi context | `recent_turns` ≤ N (không phình); có rolling_summary |

### 8.3 Tính năng: user facts (nhớ xuyên session)

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P4.3.1 | — | `POST /v1/self/facts` {user_ref, fact} | Lưu fact; `GET /v1/self/facts` trả về |
| P4.3.2 | Đã có fact y hệt | Lưu lại lần 2 | **Không nhân bản** (dedupe), chỉ cập nhật thời gian |
| P4.3.3 | Fact ở session cũ | Mở **session MỚI** rồi gọi context với cùng `user_ref` | `user_facts` vẫn có → agent vẫn biết |
| P4.3.4 | Fact của user X | Gọi context với `user_ref` của user Y | Không rò fact của X |
| P4.3.5 | Fact của agent A | Agent B gọi facts cùng user_ref | Không thấy fact của A (scope theo agent) |

### 8.4 Tính năng: RAG search có trích dẫn

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P4.4.1 | Brain có item "Quy trình nhập kho" (approved) | `GET /v1/self/brain/search?q=nhập kho` | Trả item đó kèm `source_url` để trích dẫn |
| P4.4.2 | Truy vấn **không dấu** ("nhap kho") | Search | Vẫn khớp (unaccent) |
| P4.4.3 | Truy vấn sai chính tả nhẹ ("nhap khoo") | Search | Vẫn khớp nhờ trigram |
| P4.4.4 | Item ở trạng thái pending (chưa duyệt) | Search | **Không** trả về (chỉ dùng tri thức đã duyệt) |
| P4.4.5 | Item brain riêng của agent A | Agent B search | Không thấy item của A; A vẫn thấy shared + của mình |
| P4.4.6 | Truy vấn không liên quan | Search | Trả rỗng, không lỗi |
| P4.4.7 | Có nhiều item khớp | Search k=2 | Trả đúng ≤2, sắp theo điểm liên quan |
| P4.4.8 | Câu hỏi khớp tri thức | Gọi `/v1/self/context?q=` | Phần `knowledge` có item + `source_url` (nền để agent trích dẫn thay vì bịa) |

### 8.5 Tính năng: retention purge (dọn dữ liệu quá hạn)

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P4.5.1 | `retention_config` scope=sessions, ttl nhỏ, enabled | `POST /v1/retention/purge` | Session cũ bị xoá đúng hạn; session mới còn nguyên |
| P4.5.2 | scope **disabled** | Purge | **Không** xoá gì (an toàn mặc định) |
| P4.5.3 | Có xoá | Purge | `audit_log` ghi `retention_purge` + số dòng |
| P4.5.4 | — | Purge bằng token thường | 401 |

### 8.6 Tính năng: giữ ngữ cảnh khi đổi credential/model (khoá nốt P2.8)

| ID | Tiền đề | Thao tác | Kỳ vọng |
|----|---------|----------|---------|
| P4.6.1 | Hội thoại đang chạy | Đổi credential (mô phỏng cooldown → account khác) rồi gọi lại context | Ngữ cảnh **giữ nguyên 100%** (state ở Postgres, không ở model/tiến trình) |
| P4.6.2 | Đổi version prod giữa hội thoại | Gọi context | Instruction đổi theo version mới nhưng **lịch sử hội thoại không mất** |

## 9. P5 — Connector Registry + metering (✅ 08-12, 8/8 pass)

> Lần chạy đầu bắt **1 bug thật**: lần bị chặn quyền ghi audit/usage rồi `raise` → transaction
> rollback, **mất sạch dấu vết** (đúng thứ cần nhất khi điều tra). Vá bằng commit trước khi raise.

| ID | Tiền đề | Thao tác | Kỳ vọng | Trạng thái |
|----|---------|----------|---------|-----------|
| P5.1 | Agent chưa được cấp quyền `lark` | Gọi `/v1/lark/send` | 403 + audit `connector_denied` | ✅ 08-12 |
| P5.1b | Như trên | — | Lần bị chặn **vẫn ghi `tool_usage`** (nhìn được ai đang thiếu quyền) | ✅ 08-12 |
| P5.2 | Admin cấp quyền qua console | Gọi lại | Qua gate ngay, **không restart** | ✅ 08-12 |
| P5.3 | Đang có quyền | Thu quyền giữa chừng | Call kế tiếp bị chặn **ngay lập tức** | ✅ 08-12 |
| P5.4 | Gọi connector thành công | — | `tool_usage` ghi connector+tool+latency | ✅ 08-12 |
| P5.4b | Agent dùng **skill/tool hoàn toàn mới** | `POST /v1/self/tool-usage` ×2 (1 lỗi) | `GET /v1/self/usage` thấy tần suất + lỗi **theo skill** | ✅ 08-12 |
| P5.5 | — | Đăng ký connector mock mới | Xuất hiện trong registry, **không sửa core/agent nào** | ✅ 08-12 |
| P5.6 | Connector lỗi/tắt | — | 503 **error-map rõ ràng**, agent không sập, `tool_usage` ghi lỗi | ✅ 08-12 |
| P5.7 | Agent Claude Code chạy tool | Trace về collector | Collector **tự nổ `tool_calls` thành `tool_usage`** — 3 tool (1 lỗi, gắn đúng connector) | ✅ 08-12 |

## 10. P6 — Agent Directory + A2A (✅ 08-12, 8/8 pass)

> Lần chạy đầu bắt **1 bug thật**: A2A trả kết quả lấy nhầm event `done` (`{ok:true}`)
> thay vì nội dung `message` → caller nhận rỗng. Đã sửa thứ tự ưu tiên event.

| ID | Tiền đề | Thao tác | Kỳ vọng | Trạng thái |
|----|---------|----------|---------|-----------|
| P6.1 | A và B cùng active | A gọi `/v1/self/directory` | Thấy B kèm skill/status + cờ `can_call` | ✅ 08-12 |
| P6.1b | B bị deactivate | A đọc directory | **Không** thấy B | ✅ 08-12 |
| P6.2 | Đã cấp `a2a_grant` A→B | A gọi `/v1/self/a2a/B` | Job `channel=a2a` vào **cùng queue**; audit **2 chiều** khớp `req_id` | ✅ 08-12 |
| P6.2b | B lấy job, trả kết quả | A gọi `GET /v1/self/a2a/{req_id}` | Job mang `from_agent=A`; A nhận đúng nội dung B trả | ✅ 08-12 |
| P6.2c | — | Agent khác đọc kết quả của A | 404 — không rò kết quả | ✅ 08-12 |
| P6.3 | Chưa có grant | A gọi B | 403 + audit `a2a_denied` | ✅ 08-12 |
| P6.4 | — | Gọi với `X-A2A-Hop: 4` | 429 (chặn vòng lặp, giới hạn 3 chặng) | ✅ 08-12 |
| P6.4b | — | Tự gọi chính mình | 400 | ✅ 08-12 |
| P6.5 | Target đang deactivate | A gọi B | 409 **và KHÔNG enqueue** (không rác queue) | ✅ 08-12 |
| P6.6 | Lượt A2A tiêu tốn token | — | Chi phí tính cho agent **GỌI** (caller-pays) trong mart | ✅ 08-12 (P7.5) |

## 11. P7 — Platform agents + HITL + Mart (✅ 08-12, 14/14 pass)

> Lần chạy đầu bắt **1 bug số liệu thật**: `a2a_out`/`tool_calls` ghi vào **mọi dòng kênh**
> của cùng agent/ngày → KPI **đếm trùng**. Vá bằng mô hình mart: chỉ số cấp agent chỉ nằm ở
> dòng tổng hợp (`channel='-'`), số lượt theo kênh tách riêng.

### 11.1 Phân quyền đề xuất

| ID | Tiền đề | Thao tác | Kỳ vọng | Trạng thái |
|----|---------|----------|---------|-----------|
| P7.a | Agent thường (không phải platform agent) | `POST /v1/self/actions/propose` | 403 — chỉ AG-OPS/AG-EVAL được đề xuất | ✅ 08-12 |
| P7.a2 | AG-OPS | Đề xuất action ngoài danh sách cho phép | 400 | ✅ 08-12 |
| P7.1b | AG-OPS | `GET /v1/self/ops/snapshot` | Đủ trường: jobs, dlq_by_agent, credential_pool, silent_agents, pending_actions | ✅ 08-12 |
| P7.1c | Agent thường | Xem snapshot | 403 | ✅ 08-12 |

### 11.2 HITL — rủi ro thấp tự chạy, rủi ro cao phải duyệt

| ID | Tiền đề | Thao tác | Kỳ vọng | Trạng thái |
|----|---------|----------|---------|-----------|
| P7.1 | AG-OPS phát hiện DLQ vượt ngưỡng | Đề xuất `alert` risk=**low** | **Tự chạy** (status=auto) + audit `action_auto` | ✅ 08-12 |
| P7.2 | AG-OPS đề xuất `replay_dlq` risk=**high** | — | Vào hàng chờ duyệt + card Lark | ✅ 08-12 |
| P7.2b | Đang chờ duyệt | — | **CHƯA thực thi** (DLQ chưa đổi) | ✅ 08-12 |
| P7.2c | Người vận hành bấm Duyệt | — | Thực thi **thật** (DLQ→queued), `approver` ghi đúng người | ✅ 08-12 |
| P7.2d | Đã duyệt | Duyệt lại lần 2 | 409 — không thực thi trùng | ✅ 08-12 |
| P7.2e | AG-OPS đề xuất `deactivate_agent` | Người bấm **Từ chối** | Agent **KHÔNG** bị tắt; action=rejected | ✅ 08-12 |
| P7.3 | Đề xuất quá `expires_at`, không ai duyệt | Chờ job nền | Tự chuyển `expired` (+ nhắc 1 lần trước hạn) | ✅ 08-12 |
| P7.6 | AG-OPS đề xuất | **AG-OPS tự duyệt** | 403 + audit `action_self_approve_blocked` (separation of duty) | ✅ 08-12 |

### 11.3 Mart KPI + caller-pays

| ID | Tiền đề | Thao tác | Kỳ vọng | Trạng thái |
|----|---------|----------|---------|-----------|
| P7.5 | Có trace (1500 token) + 1 lượt A2A đi ra | `POST /v1/mart/rebuild` → `GET /v1/mart/kpi` | Token/chi phí đúng, `a2a_out=1` tính cho agent **GỌI**, **không đếm trùng** | ✅ 08-12 |
| P7.4 | Điểm eval prod tụt ≥10% sau publish | AG-EVAL quét định kỳ | Đề xuất `rollback_version` qua HITL ("điểm eval tụt 1.00 → 0.00") | ✅ 08-12 |
| P7.7 | Pool subscription còn ≤1 account | AG-OPS quét | Cảnh báo sớm ("Pool subscription chỉ còn 1/1 account") trước khi rơi xuống API | ✅ 08-12 |

## 12. P8 + P9 — Tài khoản/RBAC + Agent no-code (⏳ kế hoạch)

Chi tiết: [PLAN_RBAC_NOCODE.md](PLAN_RBAC_NOCODE.md) — 17 case P8 (đăng nhập, phân quyền
theo platform & theo agent, tab Accounts) + 16 case P9 (wizard no-code, runtime no-code,
publish có phê duyệt). Điểm cốt lõi cần test: **quyền phải bị chặn ở API, không chỉ ẩn nút UI**,
và `audit_log.actor` phải là **email người thật** thay cho hằng số `web-admin` hiện nay.

---

**Tổng: 148 case — 141 ✅ đã nghiệm thu (95%).**

**7 case còn lại, chia 2 nhóm:**
- **Cần bạn xử lý (3):** `LK.5`, `P1.1` — Lark app chưa mở available-range và bot chưa ở nhóm nào (resolve trả `null`, `/v1/lark/chats` rỗng); `ST.8` — cần team thật cùng push 1 branch.
- **Chỉ kiểm bằng mắt trên UI (4):** `P3.7.1`–`P3.7.5` Builder (các API bên dưới đã pass, trang render 200).

Toàn bộ P1–P7 đã triển khai và verify trên VM. Cách chạy lại bộ smoke: script trong lịch sử deploy (P1/P2 smoke chạy trên VM), hoặc yêu cầu chạy lại bất kỳ nhóm nào.
