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
| CORE.7 | Bật `active` khi thiếu golive checklist | Chặn (409) + **nhắc OWNER** đúng mục còn thiếu; đủ checklist → hệ thống tự trình admin duyệt (xem §19) | ✅ 08-18 |
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
| LK.5 | Send text/markdown tới email/open_id/chat_id | Gửi đúng loại; email→open_id resolve qua danh bạ | ✅ 08-14 — Admin App mở range + sửa bug open_department_id: resolve OK cả 5 admin/owner |
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

## 12. P8 — Tài khoản console + RBAC (✅ 08-12, 17/17 pass)

> Bắt 1 bug thật: người ĐÃ đăng nhập nhưng thiếu quyền trên agent bị trả **401** thay vì 403
> → middleware sẽ đá họ ra trang login. Đã tách bạch 401 (chưa đăng nhập) / 403 (không đủ quyền).

| ID | Kịch bản | Kỳ vọng | TT |
|---|---|---|---|
| P8.1.1/1.5 | Đăng nhập tài khoản mới | Có phiên + **bắt đổi mật khẩu tạm** | ✅ |
| P8.1.2 | Sai mật khẩu 5 lần | Khoá 15' — mật khẩu đúng cũng bị chặn (429) | ✅ |
| P8.1.3 | Tài khoản bị khoá | Không đăng nhập được | ✅ |
| P8.1.4 | Đăng xuất | Phiên hết hiệu lực ngay | ✅ |
| P8.2.1 | **user gọi thẳng API sửa** | **403 TỪ API** (không chỉ ẩn nút) | ✅ |
| P8.2.2 | user xem config/dashboard | 200 | ✅ |
| P8.2.3 | moderator sửa agent trong phạm vi | Tạo draft OK | ✅ |
| P8.2.4 | moderator sửa agent ngoài phạm vi | 403 (không phải 401) | ✅ |
| P8.2.5 | moderator publish dev | Chạy ngay | ✅ |
| P8.2.6 | moderator publish **prod** | Tạo việc chờ duyệt, **prod chưa đổi** | ✅ |
| P8.2.7 | Admin duyệt | Prod đổi; audit có **cả người đề xuất và người duyệt** | ✅ |
| P8.2.9 | user toàn platform + moderator 1 agent | Sửa được đúng agent đó, agent khác 403 | ✅ |
| P8.3.1 | Thao tác bất kỳ | `audit.actor` = **email người thật** (hết `web-admin`) | ✅ |
| P8.3.2 | Thu quyền giữa chừng | Request kế tiếp 403 ngay, không cần đăng xuất | ✅ |
| P8.4.3 | moderator gọi API accounts | 403 | ✅ |
| P8.4.4 | Khoá tài khoản đang có phiên | Phiên vô hiệu **ngay** + không đăng nhập lại được | ✅ |
| P8.4.x | Admin reset mật khẩu | Sinh mật khẩu tạm mới, thu hồi phiên cũ | ✅ |
| P8.web | Trình duyệt chưa đăng nhập | Mọi trang **307 về /login**; cookie httpOnly+Secure | ✅ |

## 13. P9 — Agent no-code trên console (✅ 08-12, 14/14 pass)

| ID | Kịch bản | Kỳ vọng | TT |
|---|---|---|---|
| P9.1.1 | Tạo agent qua wizard (đủ điều kiện) | Agent runtime=nocode + version v1 draft; người tạo tự thành moderator của agent | ✅ |
| P9.1.2 | Thiếu use case / chỉ 1 test case | **422 — không tạo** (gate như đường code) | ✅ |
| P9.1.3 | agent_id trùng | 409, không đè agent cũ | ✅ |
| P9.1.4 | `user` tạo agent | 403 | ✅ |
| P9.2.1 | Nhắn cho agent vừa tạo | **Runtime tự trả lời — không cần viết code, không cần Docker** | ✅ |
| P9.2.3 | Câu hỏi khớp tri thức | Trả lời **kèm trích dẫn nguồn**, không bịa | ✅ |
| P9.2.4 | Hội thoại | Có ghi session (lượt sau nhớ ngữ cảnh) | ✅ |
| P9.3.1 | Moderator publish prod | Tạo việc chờ duyệt; prod chưa đổi | ✅ |
| P9.3.3 | Admin duyệt khi golden **chưa** pass | **Vẫn bị eval gate chặn** | ✅ |
| P9.3.2 | Golden pass + admin duyệt | Prod = version mới | ✅ |
| P9.4.4 | Deactivate agent no-code | Job `rejected`, runtime bỏ qua (kill-switch vẫn hiệu lực) | ✅ |
| P9.4.2 | Xuất repo (USECASE/TESTCASES ra file) | — | ⏳ chưa làm (spec đã lưu DB, API sẵn) |

## 14. TH — Đa app Lark theo squad + C1 tải file (✅ 08-12, 13/13 pass)

> Nền cho AG-SQ-THAILAND (app Sawadee HAPAS `cli_aaf6d2b3a5b8ded3`): mỗi routing_binding
> có thể gắn app Lark riêng, trả lời job bằng **đúng bot đã nhận tin**.

| ID | Kịch bản | Kỳ vọng | TT |
|---|---|---|---|
| TH.1 | Token agent AG-SQ-THAILAND (enroll) | `/v1/self` trả đúng agent | ✅ |
| TH.2a | Ingest sự kiện từ app Sawadee | Route → AG-SQ-THAILAND theo `routing_binding.app_id` | ✅ |
| TH.2b | reply_to của job | Tự mang `app_id` nguồn (chọn bot khi trả lời) | ✅ |
| TH.3a | Agent lease job | Nhận được job vừa ingest | ✅ |
| TH.3b | Reply khi app chưa có secret trên VM | Lỗi **RÕ** "chưa có secret" — KHÔNG gửi bằng bot sai | ✅ |
| TH.3c | Reply lỗi kênh Lark | Message vẫn ghi `job_events` (web/SSE không mất) | ✅ |
| TH.4 | Regression app mặc định | `/v1/lark/chats` = 200 (Minh Anh/notify còn nguyên) | ✅ |
| TH.5 | `chats?app_id=` app thiếu secret | 503 kèm hướng dẫn thêm vào `.env` VM | ✅ |
| TH.6 | C1: tin nhắn file qua gateway | Payload có `file_key`+`file_name`+`sender_open_id`+`app_id` | ✅ |
| TH.7a | Tải resource app thiếu secret | 503 secret missing | ✅ |
| TH.7b | Tải resource app mặc định (id giả) | Tới Lark, Lark từ chối → 502 minh bạch | ✅ |
| TH.7c | Tải resource không token | 401 | ✅ |
| TH.8 | Container gateway_sawadee chưa có secret | Idle an toàn + log cảnh báo rõ | ✅ |

## 15. P10 — Đăng nhập Lark OAuth + quyền mặc định + xin quyền per-agent (✅ 08-14, 21/21 pass)

> Mọi tài khoản đăng nhập (mật khẩu hoặc Lark) mặc định có quyền **user trên tất cả agent**;
> quyền moderator/admin cấp theo **từng agent** — một người giữ nhiều vai trò cùng lúc.
> Đăng nhập Lark: kiểm tra ĐÚNG ORG (tenant_key + domain email) rồi mới tự mở tài khoản.

| ID | Kịch bản | Kỳ vọng | TT |
|---|---|---|---|
| P10.1a | Account A (user platform + admin AG-MINH-ANH + moderator AG-SOURCING) login | Có phiên | ✅ |
| P10.1b | `/v1/auth/me` của A | Trả **cả 3 vai trò cùng lúc** — đa agent/account | ✅ |
| P10.1c | A sửa routing AG-SOURCING (vai moderator) | 200 | ✅ |
| P10.1d | A sửa routing AG-MINH-ANH (vai admin) | 200 | ✅ |
| P10.1e | A sửa routing AG-BI (chỉ user mặc định) | 403 | ✅ |
| P10.1f | A gọi API quản lý tài khoản | 403 (không phải admin platform) | ✅ |
| P10.2a | Account B không có binding nào | DB xác nhận 0 binding | ✅ |
| P10.2b | Catalog của B | effective_role = **user trên TẤT CẢ agent** (mặc định) | ✅ |
| P10.2c | B sửa config | 403 — mặc định chỉ xem | ✅ |
| P10.3a | `/v1/auth/lark/start` | URL authorize Lark (app_id + redirect console + state ký HMAC) | ✅ |
| P10.3b | Callback với state giả | 400 (chống CSRF, TTL 10') | ✅ |
| P10.3c | Callback state đúng + code giả | 401 — Lark từ chối, không tạo phiên | ✅ |
| P10.4 | Đăng nhập Lark thật + kiểm org (tenant/domain) + auto tạo tài khoản + trang xin quyền | ✅ 08-14 — thint@hapas.vn login OK (audit #396); fix redirect dùng hostname container → publicBase(); siết LARK_TENANT_KEY | ✅ |
| P10.5a | B xin moderator AG-SOURCING | Tạo yêu cầu + notify admin (Telegram/Lark) | ✅ |
| P10.5b | Xin trùng khi đang pending | 409 | ✅ |
| P10.5c | Xin quyền 'user' | 400 — user là mặc định, không cần xin | ✅ |
| P10.5d | B tự duyệt yêu cầu của mình | 403 | ✅ |
| P10.5e | Admin xem danh sách chờ | Thấy yêu cầu (Console → Tài khoản) | ✅ |
| P10.5f | Admin duyệt | Ghi role_binding + báo người xin | ✅ |
| P10.5g | Sau duyệt B sửa AG-SOURCING | 200 — quyền hiệu lực ngay | ✅ |
| P10.5h | Duyệt lại yêu cầu đã chốt | 409 | ✅ |
| P10.6 | Admin TỪ CHỐI yêu cầu lên admin | Quyền giữ nguyên moderator | ✅ |

## 16. A2A — 5 tình huống agent gọi nhau (✅ 08-14, 14/14 pass — agent + token THẬT trên VM)

> Master data năng lực (`agents.capabilities` + `usage_guide`) là nguồn để agent khác
> biết AI-làm-được-GÌ và GỌI-THẾ-NÀO trước khi A2A. Agent mới: token cấp TỰ ĐỘNG ở
> mọi kênh đăng ký (enroll/no-code) nhưng phải được admin ACTIVATE mới chạy kênh thực + A2A.

| ID | Tình huống | Kỳ vọng | TT |
|---|---|---|---|
| A2A.1 | MAI đọc `/v1/self/directory` | Thấy capabilities + usage_guide (10 agent có master data), `can_call` đúng theo grant | ✅ |
| A2A.2 | **Happy path** MAI → AG-SOURCING hỏi trạng thái duyệt báo giá | Grant → gọi → target trả lời → caller nhận đúng nội dung (round-trip đo được) | ✅ |
| A2A.3 | **Grant gate** AG-SQ-THAILAND → AG-DATA-SUPPORT | Chưa grant: 403 + audit `a2a_denied`; sau grant: nhận số liệu kèm nguồn | ✅ |
| A2A.4 | **Approve gate**: agent mới enroll (AG-A2ATEST) | Token TỰ SINH + admin được notify; gọi TỚI nó 409, nó gọi RA 403, Lark ingest `rejected`; admin activate → chạy ngay | ✅ |
| A2A.5 | **Chống vòng lặp + caller-pays** | hop 4 > 3 → 429; mart `a2a_out` tính cho BÊN GỌI (MAI=2, TH=1) | ✅ |

⚠️ Bài học vận hành (sự cố 08-14, đã khắc phục trong harness): consumer mô phỏng khi test
**chỉ được đụng job `channel='a2a'` khớp req_id của test** — job kênh thật lease nhầm phải
`fail` để trả về queue, tuyệt đối không reply. (Một tin thật của nhóm SOURCING MM từng bị
harness trả lời nhầm — xem báo cáo 08-14.)

## 17. P11 — Device-login CLI + token cá nhân + enroll tự duyệt (✅ 08-14, 25/25 pass)

> Bỏ rào "đi xin enroll token": CLI/Claude Code tự đăng nhập như `gh auth login`.
> Token cá nhân mang ĐÚNG quyền người dùng; **admin enroll → agent ACTIVE luôn**.

| ID | Kịch bản | Kỳ vọng | TT |
|---|---|---|---|
| P11.1a | `POST /v1/auth/device/start` | Trả user_code + link duyệt, không cần auth | ✅ |
| P11.1b | Poll khi chưa duyệt | `pending` — không cấp token sớm | ✅ |
| P11.1c | Duyệt khi chưa đăng nhập console | 401 | ✅ |
| P11.1d | Người dùng duyệt trên console | `approved` | ✅ |
| P11.1e | CLI poll sau duyệt | Nhận token cá nhân của ĐÚNG người duyệt | ✅ |
| P11.1f | Poll lần 2 | Token chỉ trả MỘT LẦN rồi xoá | ✅ |
| P11.1g | Mã sai | 404 | ✅ |
| P11.2a | Gọi `/v1/auth/me` bằng PAT | Nhận diện đúng người | ✅ |
| P11.2b | PAT moderator gọi API admin | **403** (không phải 401 — không đá về login) | ✅ |
| P11.2c | Liệt kê token của mình | Thấy nhãn thiết bị | ✅ |
| P11.3a | Enroll bằng PAT, KHÔNG enroll-token | Tạo agent thành công | ✅ |
| P11.3b | — | Token agent cấp TỰ ĐỘNG trong response | ✅ |
| P11.3c | Không truyền owner | Tự lấy = email người tạo | ✅ |
| P11.3d | Người tạo là moderator | `auto_approved=false` — chờ admin | ✅ |
| P11.3e | — | Người tạo tự thành moderator của agent đó | ✅ |
| P11.4a | **Admin** enroll | Agent `active` NGAY (tự duyệt) | ✅ |
| P11.4b | — | Response ghi `auto_approved=true` | ✅ |
| P11.4c | — | `golive_at` được ghi | ✅ |
| P11.4d | Tin Lark tới agent admin vừa tạo | `queued` — chạy kênh thực ngay | ✅ |
| P11.4e | Tin Lark tới agent của moderator | `rejected` — vẫn chờ duyệt | ✅ |
| P11.5a | Enroll bằng enroll-token cũ | Vẫn chạy (không phá script cũ) | ✅ |
| P11.5b | Enroll không auth | Lỗi CHỈ ĐƯỜNG: chạy `lsr-login.sh` | ✅ |
| P11.5c | Thu hồi token cá nhân | Chết ngay (401) | ✅ |
| P11.6a | Ops snapshot | Có dung lượng đĩa VM | ✅ |
| P11.6b | AG-OPS khi đĩa ≥85% | Cảnh báo kèm lệnh dọn Docker (sự cố 08-14) | ✅ |

---

## 18. Golive không ma sát + cảnh báo routing bắt tất (✅ 08-18, 6/6 pass)

| ID | Kịch bản | Kỳ vọng | TT |
|---|---|---|---|
| A2.x | ~~Approve bỏ qua checklist~~ | **Đã thay bằng §19** (18/08): checklist là gate, owner bổ sung rồi mới tới admin | ↩︎ |
| B.1 | Ops snapshot | Phát hiện binding "bắt tất" (app_id + chat_id đều rỗng) | ✅ |
| B.2 | AG-OPS | Sinh cảnh báo cho TỪNG binding, nêu agent + người tạo + cách xử lý | ✅ |
| A1 | Caddy carve-out | `/login` `/device` `/api/auth/*` mở (200/307); `/accounts` `/` vẫn 401 basic-auth | ✅ |

---

## 19. Golive 2 chặng: owner đủ checklist → admin duyệt (✅ 08-18, 22/22 pass)

> Quy trình chốt: agent KHÔNG tự lên sóng. Thiếu checklist → platform **nhắc owner**
> đúng mục thiếu. Đủ 28 mục → hệ thống **tự trình admin duyệt** (HITL, risk=high,
> owner không tự duyệt việc mình đề xuất). Admin bấm Duyệt → agent chạy kênh thật.

| ID | Kịch bản | Kỳ vọng | TT |
|---|---|---|---|
| GL.1a | Active khi thiếu checklist | 409, không bật | ✅ |
| GL.1b | Nội dung lỗi | Nói rõ đã nhắc owner + cách bổ sung | ✅ |
| GL.1c | Danh sách thiếu | Liệt kê đủ 28 mục để owner biết làm gì | ✅ |
| GL.1d | Audit | Ghi `golive_blocked` + owner đã nhắc | ✅ |
| GL.1e | Trạng thái agent | Vẫn `registered` — không lọt kênh thật | ✅ |
| GL.2a | Nộp checklist còn thiếu | `complete=false` + danh sách thiếu | ✅ |
| GL.2b | Hướng dẫn | Chỉ bước tiếp theo cho owner | ✅ |
| GL.2c | Trình admin | CHƯA trình khi còn thiếu | ✅ |
| GL.3a–c | Nộp đủ checklist | `complete=true`, tự tạo đề xuất duyệt, owner biết đang chờ admin | ✅ |
| GL.3d | Mức rủi ro | `risk=high` → bắt buộc người duyệt | ✅ |
| GL.3e | Sau khi nộp đủ | KHÔNG tự bật agent (owner không tự golive) | ✅ |
| GL.3f | Nộp lại nhiều lần | Không tạo đề xuất trùng | ✅ |
| GL.4a–d | Admin duyệt | Thực thi `activate_agent` → `active` + `golive_at` + kênh Lark `queued` | ✅ |
| GL.5a–b | **Chống lách**: xoá checklist rồi mới duyệt | Chặn tại lúc thực thi + nhắc owner; agent không bị bật | ✅ |
| GL.6a–b | Admin `force` (ngoại lệ) | Vẫn bật được nhưng audit ghi rõ thiếu mục gì | ✅ |

---

### 19.1 Owner tự nộp bằng token cá nhân (✅ 08-18, 10/10 pass)

> Bắt **1 bug thật**: `_require_role` (guard trung tâm) chưa nhận token cá nhân PAT →
> MỌI endpoint cấp moderator đều 401 khi gọi từ CLI. Cùng họ bug session-vs-PAT đã sửa
> ở `/auth/me` và `_require_admin`; nay sửa tận guard chung + `_actor_of` (audit ghi
> đúng người thay vì "service").

| ID | Kịch bản | Kỳ vọng | TT |
|---|---|---|---|
| S.1 | Owner (moderator agent) chạy `lsr-login.sh` | Lấy được token cá nhân | ✅ |
| S.2a | Nộp checklist bằng PAT | Nộp được, KHÔNG cần admin platform | ✅ |
| S.2b | Nộp 3/28 mục | Trả đúng 25 mục còn thiếu | ✅ |
| S.2c | — | Chưa trình admin | ✅ |
| S.3a | Nộp đủ 28 mục | Tự tạo đề xuất duyệt | ✅ |
| S.3b | `proposed_by` | Ghi đúng email người nộp (không phải "service") | ✅ |
| S.3c | — | Owner không tự bật agent | ✅ |
| S.4 | Owner tự duyệt đề xuất của mình | 403 — tách vai | ✅ |
| S.5a–b | Admin duyệt | AG-HARRY golive **đúng luồng, không force** | ✅ |

---

### 19.2 Owner nộp TỪ MÁY DEV qua Caddy (✅ 08-18, 8/8 pass — Linh báo lỗi)

> Bắt **2 bug thật** + **1 lỗ bảo mật**. Bài học lặp lần 3: test chạy trên VM
> (`localhost:8090`) **bỏ qua Caddy**, nên mọi carve-out thiếu đều không lộ ra. Test của
> tính năng owner-facing PHẢI đi từ máy dev qua domain thật.

| ID | Kịch bản | Kỳ vọng | TT |
|---|---|---|---|
| C.1 | `/v1/agents/*/golive-checklist|spec|profile` từ máy dev | Không còn 403 của Caddy (401 = đã tới app) | ✅ |
| C.2 | `/v1/auth/tokens`, `/v1/roles/catalog` | Mở cho CLI | ✅ |
| C.3 | `/v1/accounts`, `/v1/model-auth/*`, `/v1/routing` | **Vẫn 403** — ranh giới admin không bị nới | ✅ |
| E.1–3 | Device-login từ máy dev qua Caddy | Lấy được token cá nhân | ✅ |
| E.4 | POST checklist rỗng qua Caddy | App trả đúng 28 mục thiếu | ✅ |
| E.5–6 | `scripts/submit-golive.sh` chạy từ máy dev | Nộp được + in mã đề xuất đã trình admin | ✅ |
| E.7 | GET checklist bằng token cá nhân | Đọc được payload của agent mình | ✅ |
| E.8 | GET checklist KHÔNG token | **401** — trước đây endpoint này không kiểm quyền, mở qua Caddy là hở email/KPI/nguồn dữ liệu ra internet | ✅ |

Bug đã sửa: (1) Caddy `@selfserve` thiếu route golive-checklist → owner 403; dùng
`path_regexp` vì `path` matcher không khớp wildcard giữa đường dẫn. (2) `submit-golive.sh`
pipe response vào `python3 - <<EOF` → heredoc chiếm stdin, script luôn crash khi nộp.
(3) `GET /golive-checklist` chưa kiểm quyền → thêm `_require_role(user, agent_id)`.

---

**Tổng: 285 case — 279 ✅ đã nghiệm thu (98%).**

**7 case còn lại, chia 2 nhóm:**
- **Cần bạn xử lý (2):** `P1.1` — bot Admin App chưa được add vào nhóm nào (`/v1/lark/chats` rỗng — add bot vào 1 nhóm là xong); `ST.8` — cần team thật cùng push 1 branch.
- **Chỉ kiểm bằng mắt trên UI (4):** `P3.7.1`–`P3.7.5` Builder (các API bên dưới đã pass, trang render 200).

Toàn bộ P1–P7 đã triển khai và verify trên VM. Cách chạy lại bộ smoke: script trong lịch sử deploy (P1/P2 smoke chạy trên VM), hoặc yêu cầu chạy lại bất kỳ nhóm nào.

## §20 — Đĩa VM: cảnh báo xin duyệt + tự dọn (AG-OPS + prune_docker)

Ngưỡng mặc định: `OPS_DISK_WARN_PCT=80` (xin duyệt), `OPS_DISK_AUTO_PCT=90` (tự dọn),
`OPS_PRUNE_AGE_HOURS=168` (không đụng image mới hơn 7 ngày).

| # | Case | Kỳ vọng | KQ |
|---|---|---|---|
| 20.1 | `diagnose` với đĩa 79% | không đề xuất gì | ✅ |
| 20.2 | đĩa 84% | 1 đề xuất `prune_docker` risk=**high** (chờ duyệt) | ✅ |
| 20.3 | đĩa 92% | 1 đề xuất `prune_docker` risk=**low** (tự chạy) | ✅ |
| 20.4 | đĩa 96% | thêm alert "dọn image có thể không đủ" | ✅ |
| 20.5 | `prune_docker` scope lạ (`"tat ca"`) | trả lỗi, KHÔNG gọi Docker | ✅ |
| 20.6 | `prune_docker` scope=dangling trên VM thật | xoá 40 lớp mồ côi, trả disk before/after | ✅ |
| 20.7 | freed_gb = 0 | KHÔNG nhắn admin (chống spam mỗi giờ) | ✅ |
| 20.8 | propose high 2 lần cùng params | lần 2 trả đúng id cũ + `duplicate:true`, không đẻ phiếu mới | ✅ |
| 20.9 | `pending_actions.params` là jsonb | so sánh `params = %s::jsonb` chạy được (không lỗi `json =`) | ✅ |

Ghi chú đo thật trên VM 19/08: image dangling chỉ ~0.4GB, còn scope `unused/168h`
mới gom được ~2.8GB (9 image). Tức là dọn image chỉ cứu được ~6% đĩa — case 20.4
tồn tại chính vì lý do đó, đừng coi auto-prune là bảo hiểm.

## §21 — Gateway Lark không kết nối (agent active nhưng câm)

| # | Case | Kỳ vọng | KQ |
|---|---|---|---|
| 21.1 | agent active + app riêng, platform chưa có secret | vào `lark_gateway_gaps` | ✅ |
| 21.2 | app có secret và Lark chấp nhận (Sawadee/Sourcing/Data) | KHÔNG báo | ✅ |
| 21.3 | agent `registered` (AG-HARRY) | KHÔNG báo — chưa được phép nhận tin | ✅ |
| 21.4 | tiền tố env lấy từ `LARK_APP_PREFIXES` | lệnh in ra đúng `LYLY` + `event_gateway_lyly` | ✅ |
| 21.5 | thiếu `LARK_APP_PREFIXES` | fallback quét os.environ, không vỡ | ✅ |
| 21.6 | AG-OPS chạy thật | tạo `pending_actions #419` đúng nội dung | ✅ |
| 21.7 | `add-lark-app.sh LEGAL <app của Minh Anh>` | CHẶN, không ghi .env (2 listener/1 app = Lark chia event, mất tin) | ✅ |
| 21.8 | `add-lark-app.sh LEGAL <app_id mới>` | đi tiếp bình thường tới bước nhập secret | ✅ |
| 21.9 | `add-lark-app.sh LYLY <app_id của chính LYLY>` | KHÔNG coi là trùng (cập nhật lại secret cũ) | ✅ |
| 21.10 | `LEGAL_LARK_APP_ID` rỗng | `LARK_EXTRA_APPS`/`LARK_APP_PREFIXES` vẫn parse được, không mất app phụ nào | ✅ |

## §22 — C8 User Identity Broker cho Lark (36/36)

Chạy in-process trong container `platform_api` bằng agent NHÁP `AG-C8TEST` + identity
giả (`c8test@hapas.vn`) — không chạm agent thật, không gọi Lark thật. Dọn sạch cuối bài.

| Nhóm | Case | KQ |
|---|---|---|
| A. Mã hoá | ciphertext khác nhau mỗi lần (nonce), giải mã đúng, plaintext không nằm trong ciphertext | 3/3 ✅ |
| B. authorize/start | subject không phải email→422; domain ngoài org→403; domain nghiệp vụ lạ→422; app không có secret→503; trả url+state; scope có `offline_access`; url không chứa secret; không phải admin→401 | 8/8 ✅ |
| C. Phân quyền | chưa grant→403; tạo grant; `path_prefix` không phải `/open-apis/`→422; grant cho identity chưa có→404; path ngoài allowlist→403; method ngoài allowlist→403; path có `..`→422; path không phải `/open-apis/`→422 | 8/8 ✅ |
| D. status | connected=True khi có grant; response KHÔNG chứa token; subject lạ→connected=False kèm lý do | 3/3 ✅ |
| E. Tự refresh | trả token MỚI; DB lưu token mới (vẫn mã hoá); expiry gia hạn; audit có `lark_user_refresh` | 4/4 ✅ |
| F. Refresh hết hạn | →401 nói rõ phải authorize lại | 1/1 ✅ |
| G. Kill switch | deactivate agent→tắt grant; gọi sau đó→403; revoke→xoá identity; gọi sau revoke→403 | 4/4 ✅ |
| H. Audit | mọi sự kiện C8 của subject cùng `target_id`; agent_id là actor; audit KHÔNG chứa token dạng rõ; dọn sạch identity + agent nháp | 5/5 ✅ |

### §22.1 — Định tuyến qua Caddy (từ máy dev, không phải localhost:8090)

| Path | Không gateway token | Kỳ vọng | KQ |
|---|---|---|---|
| `POST /v1/lark/user/authorize/start` | 403 | chặn ở edge | ✅ |
| `POST /v1/lark/user/grants` | 403 | chặn ở edge | ✅ |
| `GET /v1/lark/user/identities` | 403 | chặn ở edge | ✅ |
| `POST /v1/lark/user/identities/{s}/revoke` | 403 | chặn ở edge | ✅ |
| `POST /v1/lark/user/call` | 401 `agent token required` | **tới được app** (agent gọi được) | ✅ |
| `GET /v1/lark/user/status` | 401 `agent token required` | tới được app | ✅ |
| `GET /v1/lark/user/identities` + gateway + admin token | 200 `[]` | admin dùng được | ✅ |
| `POST /v1/lark/user/authorize/start` + gateway, thiếu admin | 401 `admin token required` | 2 lớp độc lập | ✅ |

**Chưa nghiệm thu được (cần người bấm đồng ý trên Lark):** lời gọi Approval thật bằng
user token của một account thật. Toàn bộ đường đi đã test bằng token giả + refresh giả;
ca cuối chỉ chạy được sau khi chốt chính sách §5 và có identity đầu tiên.

### §22.2 — Link authorize hết hạn + tên bot trên console

| # | Case | Kỳ vọng | KQ |
|---|---|---|---|
| 22.9 | callback với state không tồn tại | 400 nói rõ "state không tồn tại — xin link mới" | ✅ |
| 22.10 | callback với state đã hết hạn | 400 nói rõ **đã hết hạn + giờ tạo + subject**, đánh dấu session `expired` | ✅ |
| 22.11 | callback dùng lại link đã done | 400 "mỗi link chỉ dùng một lần" | ✅ |
| 22.12 | TTL link authorize | 24h (bước có người, link gửi qua chat) | ✅ |
| 22.13 | `POST /v1/lark/bots/sync` | lấy `app_name` thật từ `bot/v3/info`, sửa `lark_bot_name` lệch, ghi audit | ✅ 3 agent |
| 22.14 | agent thiếu app_secret khi sync | báo trong `van_de`, không ghi tên rỗng lên DB | ✅ AG-HARRY |

Sự cố 20/08 sinh ra §22.9-22.12: link 30 phút hết hạn trước khi người bấm, callback trả
400 với thông báo mờ ("không hợp lệ hoặc đã hết hạn") nên không ai biết phải làm gì.

### §22.3 — Nghiệm thu tiêu chí 1: AG-LEGAL gọi Approval thật (20/08)

Identity `ann_legal@hapas.vn` (Ann Nguyen, `ou_28c573f0…`) authorize bằng chính account
đó; grant `/open-apis/approval/v4/` + GET,POST. Gọi qua domain thật (Caddy), token tạm
20 phút của AG-LEGAL, **đã xoá sau khi test** (gọi lại → 401).

| # | Case | Kỳ vọng | KQ |
|---|---|---|---|
| 22.15 | `GET approval/v4/tasks?topic=1` bằng user token của Ann | Lark `code: 0` | ✅ |
| 22.16 | agent có thấy token không | không — chỉ nhận `{http_status, data}` | ✅ |
| 22.17 | `GET /open-apis/im/v1/messages` (ngoài allowlist) | 403 kèm danh sách path được cấp | ✅ |
| 22.18 | audit từng lời gọi | 8 dòng `lark_user_call` đủ actor=AG-LEGAL, subject, path, http, lark_code | ✅ |
| 22.19 | metering | `tool_usage` connector=`lark_user`: 2 ok / 13 lỗi, có latency | ✅ |
| 22.20 | grant identity có tự cấp connector `lark_user` | có (trước đó phải cấp tay → 403 khó hiểu) | ✅ |
| 22.21 | `status` phản ánh cả connector grant | có (trước đó trả `connected:true` trong khi `/call` 403) | ✅ |
| 22.22 | token tạm bị xoá | lời gọi sau đó 401 | ✅ |

**Cả 8 tiêu chí nghiệm thu C8 đã đóng.**

### §22.4 — Panel danh tính trên trang agent

| # | Case | Kỳ vọng | KQ |
|---|---|---|---|
| 22.23 | `GET /v1/agents/AG-LEGAL/lark-identities` | trả subject/name/open_id/scope/path_prefixes/methods/refresh_days_left + `calls_7d` | ✅ |
| 22.24 | response có token không | **không** — không trường nào chứa token | ✅ |
| 22.25 | agent chưa có identity (AG-SOURCING) | `identities: []`, `calls_7d` toàn 0 | ✅ |
| 22.26 | qua Caddy, không token | 401 `cần đăng nhập console` (đã vào app, không phải 403 của guard) | ✅ |
| 22.27 | route cũ `golive-checklist` sau khi sửa regex | vẫn 401 như trước, không hỏng | ✅ |
| 22.28 | panel có trong bản build của web | có trong `.next/server/app/agent/[id]/page.js` | ✅ |

Lưu ý vận hành: Caddyfile nướng trong image nên đổi route **phải** `docker compose build
caddy` + `up -d --force-recreate caddy`. Lần này `up -d --build caddy` không dựng lại
container (giữ config cũ) nên endpoint mới trả 403 của guard — mất một vòng mới phát hiện.

## §23 — Chuyển console sang domain thật `agent.hapas-ai.tech`

`scripts/switch-console-domain.sh` kiểm 3 điều kiện rồi mới đổi `.env`; thiếu một mục là
dừng, không đổi gì. Lý do phải chặn: đổi `CONSOLE_BASE_URL` là đổi `redirect_uri` của Lark
OAuth, mà Lark chỉ nhận URI đã đăng ký — sai là **cả nhà mất đăng nhập** cùng luồng
authorize C8.

| # | Case | Kỳ vọng | KQ |
|---|---|---|---|
| 23.1 | DNS chưa trỏ | ✗ "không có record", exit 1, không đổi `.env` | ✅ |
| 23.2 | HTTPS chưa có cert | ✗ http 000 | ✅ |
| 23.3 | redirect_uri chưa đăng ký trong Lark | ✗ `error=invalid_request` + in đúng chỗ cần thêm | ✅ |
| 23.4 | Caddy nạp site mới khi DNS chưa có | site load được, ACME báo NXDOMAIN và tự thử lại | ✅ |
| 23.5 | domain cũ trong lúc chuyển | `platform.*` 200, `app.*` 200 — không ảnh hưởng | ✅ |
| 23.6 | `publicBase()` với host mới | redirect theo host thật, không ghim domain cũ | ✅ (đã có sẵn) |

### §23.1 — Đã chuyển xong (20/08)

| # | Case | Kỳ vọng | KQ |
|---|---|---|---|
| 23.7 | DNS + Lark redirect_uri đã xong → chạy script thật | đổi `.env`, dựng lại `platform_api`+`web` | ✅ |
| 23.8 | Caddy cấp cert cho domain mới | `certificate obtained successfully` (phải restart caddy để thoát backoff sau các lần NXDOMAIN) | ✅ |
| 23.9 | `redirect_uri` của luồng đăng nhập console | `https://agent.hapas-ai.tech/api/auth/lark/callback` | ✅ |
| 23.10 | URL đăng nhập đó có ra trang Lark thật | http 200, không `invalid_request` | ✅ |
| 23.11 | `redirect_uri` của luồng authorize C8 | cùng domain mới, ra trang Lark thật | ✅ |
| 23.12 | domain cũ sau khi đổi | `app.*` vẫn 200 (không cắt) | ✅ |
| 23.13 | identity của Ann sau khi đổi domain | còn nguyên, refresh còn 6 ngày | ✅ |
| 23.14 | xin 4 link authorize liên tiếp trong 1 giây | 4× http 200, state khác nhau | ✅ (trước: lần 3 → **500** trùng khoá) |
| 23.15 | dùng lại link đã bị thay | 400 "đã bị thay bằng link mới hơn" | ✅ |

## §24 — Báo đã nhận trên Lark (thả emoji trước khi trả lời)

Lark không có "typing indicator" cho bot, nên dấu hiệu duy nhất người dùng thấy được là
một reaction. Làm ở **event_gateway** (không phải trong từng agent) để mọi agent có ngay
và phản hồi tức thì thay vì chờ agent nghĩ xong.

| # | Case | Kỳ vọng | KQ |
|---|---|---|---|
| 24.1 | ingest trả `status=queued` | thả emoji `OK` lên tin của người hỏi | ⏳ chờ 1 tin thật |
| 24.2 | ingest trả `unrouted` / `rejected` | **không** thả — hứa suông rồi im là tệ hơn không hứa | ✅ (theo code path) |
| 24.3 | ingest trả `duplicate` | không thả lại | ✅ |
| 24.4 | token + scope + endpoint reactions | Lark chỉ báo sai `message_id` (99992354), không báo thiếu quyền | ✅ |
| 24.5 | Lark từ chối (thiếu scope / emoji lạ) | tự **tắt** báo-đã-nhận, log đúng 1 lần kèm cách sửa | ✅ (code) |
| 24.6 | lỗi mạng khi thả emoji | bỏ qua, KHÔNG chặn luồng trả lời | ✅ |
| 24.7 | dựng lại cả 8 gateway | 6 app có secret đều `connected to wss` lại; DATA/HARRY vẫn idle như trước | ✅ |

Tắt cho một app cụ thể: đặt `LARK_ACK_EMOJI=` (rỗng) cho đúng container gateway đó —
hữu ích với app nằm trong nhóm đông, mỗi tin một emoji sẽ thành ồn.

## §25 — A2A mở qua Caddy + tài liệu cho project vibe code (17/17)

Chạy **đúng đoạn code trong `docs/A2A.md`** bằng 2 agent nháp (`AG-A2A-CALLER-TEST`,
`AG-A2A-TARGET-TEST`), dọn sạch trước và sau. Mục đích: tài liệu sai thì phải fail ở đây,
không phải fail trên máy người đọc.

| # | Case | Kỳ vọng | KQ |
|---|---|---|---|
| 25.1 | `/v1/self/directory` | caller thấy chính mình `is_self=true` | ✅ |
| 25.2 | chưa grant | `can_call=false` | ✅ |
| 25.3 | gọi khi chưa grant | 403 + audit `a2a_denied` | ✅ |
| 25.4 | gọi sau khi có grant | trả `req_id` + `status=queued` ngay, không chờ | ✅ |
| 25.5 | poll khi chưa xong | `job_status=queued` | ✅ |
| 25.6 | target lease job | thấy job `channel=a2a` trong `/v1/self/jobs` | ✅ |
| 25.7 | `payload.text` | đúng `task` bên gọi gửi | ✅ |
| 25.8 | `payload.from_agent` + `hop` | có, để chuyển tiếp hop | ✅ |
| 25.9 | target `reply` + `complete` | caller đọc được `result.text` | ✅ |
| 25.10 | `X-A2A-Hop: 9` | 429 vượt `A2A_MAX_HOP=3` | ✅ |
| 25.11 | tự gọi chính mình | 400 | ✅ |
| 25.12 | target không tồn tại | 404 | ✅ |
| 25.13 | agent khác đọc `req_id` của mình | 404 (không rò kết quả sang agent khác) | ✅ |
| 25.14 | audit 2 chiều | `a2a_call` bên gọi + `a2a_serve` bên phục vụ, cùng `req_id` | ✅ |
| 25.15 | dọn sạch | không còn agent/grant/req/job test | ✅ |

### §25.1 — Định tuyến + rate limit

| # | Case | Kỳ vọng | KQ |
|---|---|---|---|
| 25.16 | `/v1/self/a2a/*`, `/v1/self/directory` qua Caddy, không gateway token | 401 của app (mở sẵn cho agent) | ✅ |
| 25.17 | `POST /v1/a2a/grant` không gateway token | 403 của guard (admin-only) | ✅ |
| 25.18 | 90 request liên tiếp vào zone A2A | **0** lần 429 (zone riêng 600/phút) | ✅ |
| 25.19 | 80 request vào zone chung | 20 lần 429 — vẫn giữ 60/phút, không bị nới theo | ✅ |

**Hai lỗi bộ test này bắt được, không phải lỗi platform mà là lỗi tài liệu/quy trình:**
`GET /v1/self/jobs` trả về **list**, tài liệu bản đầu viết `["jobs"]` → `TypeError` ngay
dòng đầu người đọc copy. Và lần chạy đầu crash giữa bài để lại `a2a_grants`, làm case
"chưa grant → bị chặn" pass sai ở lần sau — test phải tự dọn **trước** khi chạy.

## §26 — Grant `im` cho user account: đọc + trả lời (DM và group)

Grant AG-LEGAL → `ann_legal@hapas.vn`: `path_prefixes=[/open-apis/approval/v4/,
/open-apis/im/v1/]`, `methods=[GET,POST]`. Kiểm qua domain thật bằng token tạm của
AG-LEGAL (đã xoá sau khi test). **Không gửi tin thật cho ai**: các case gửi dùng
`receive_id` không tồn tại — Lark trả lỗi THAM SỐ chứng tỏ quyền đã qua.

| # | Case | Kỳ vọng | KQ |
|---|---|---|---|
| 26.1 | authorize lại với `domains=approval,im` | identity có đủ 4 scope `im`, refresh reset 7 ngày | ✅ |
| 26.2 | `GET im/v1/chats` | `code 0`, 3 chat | ✅ |
| 26.3 | `GET im/v1/messages` (nhóm Legal) | `code 0`, đọc được lịch sử | ✅ |
| 26.4 | `POST im/v1/messages` receive_id_type=chat_id | lỗi tham số (230001), **không** lỗi quyền → gửi group được phép | ✅ |
| 26.5 | `POST im/v1/messages` receive_id_type=open_id | lỗi tham số (99992351) → gửi DM được phép | ✅ |
| 26.6 | `POST im/v1/messages/{id}/reply` | lỗi tham số (99992354) → trả lời thread được phép | ✅ |
| 26.7 | `DELETE im/v1/messages/{id}` | chặn ở platform: "method DELETE không được cấp" | ✅ |
| 26.8 | `GET contact/v3/users` | chặn: ngoài allowlist | ✅ |
| 26.9 | `GET drive/v1/files` | chặn: ngoài allowlist | ✅ |
| 26.10 | trước khi nới grant | `im/v1/chats` bị chặn đúng (403 kèm danh sách path được cấp) | ✅ |

Chưa nghiệm thu được: **nhận** tin nhắn gửi thẳng cho user account. Long-connection hiện
mở bằng credential APP nên DM tới account không tới platform — xem mục "Được phép ≠ biết
có tin" trong `docs/LARK_USER_BROKER.md`.
