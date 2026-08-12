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
| P2.8 | Đổi account giữa hội thoại | Người dùng không nhận ra (job giữ trong queue; NGỮ CẢNH đầy đủ cần P4) | ✅ một nửa — phần context ⏳ P4 |
| P2.9 | Runner lease end-to-end trên VM | Container lease→đọc /secrets/<ref>→chạy; limit→re-lease | ⏳ chờ agent managed đầu tiên deploy thật |

## 6. Stable release — workflow team (✅ 08-12, gate local 4/4)

| ID | Kịch bản | Kỳ vọng | Trạng thái |
|----|----------|---------|-----------|
| ST.1 | Code agent khi THIẾU USECASE.md/TESTCASES.md | Plugin chặn Write/Edit file code + hướng dẫn tạo 2 file | ✅ 08-12 (unit 4/4) |
| ST.2 | Viết chính USECASE.md/TESTCASES.md | Luôn cho phép (không gate file .md/.jsonl) | ✅ 08-12 |
| ST.3 | Đủ 2 file → code | Cho phép bình thường | ✅ 08-12 |
| ST.4 | PR có code agent mà thiếu 2 file | CI `agent-gate` fail kèm hướng dẫn | ⏳ nghiệm thu ở PR đầu tiên của team |
| ST.5 | `new-agent.sh` scaffold | Sinh đủ USECASE/TESTCASES/tests.jsonl/consumer.py/README; consumer compile được | ✅ 08-12 |
| ST.6 | Team branch không đụng core | scope-guard fail nếu PR chạm `infra/ src/ scripts/ plugins/ ...` | ✅ 08-09 (đã có) |
| ST.7 | `agent-test.sh` chạy tests.jsonl qua Chat API | Pass/fail theo từ khoá kỳ vọng; exit code đúng cho CI | ⏳ nghiệm thu cùng agent đầu tiên của team |
| ST.8 | 2–3 người cùng branch | Push chung branch `agent/<team>-<ID>`, PR duy nhất, không conflict core | ⏳ nghiệm thu với team đầu tiên |

## 7. P3 — Agent Versions + Builder + eval gate (⏳ kế hoạch)

| ID | Kịch bản | Kỳ vọng |
|----|----------|---------|
| P3.1 | Sửa instruction qua Builder | Tạo draft; agent đang chạy KHÔNG đổi hành vi |
| P3.2 | Publish lên dev | Chỉ job môi trường dev dùng bản mới; prod giữ nguyên |
| P3.3 | Publish prod khi golden fail | Bị chặn + hiển thị case fail; audit ghi lần thử |
| P3.4 | Publish prod khi golden pass | Áp dụng ở job kế tiếp, không rebuild; audit ai-publish-gì |
| P3.5 | Rollback 1 click | Version trước hoạt động lại ở job kế tiếp |
| P3.6 | Version khai skill mới | Skill xuất hiện ở brain_skills + Directory |

## 8. P4 — Context Compiler + Session Memory + RAG (⏳ kế hoạch)

| ID | Kịch bản | Kỳ vọng |
|----|----------|---------|
| P4.1 | 2 câu nối nhau trong 1 session | Câu 2 hiểu ngữ cảnh câu 1 dù là 2 call LLM độc lập |
| P4.2 | Restart runner giữa hội thoại | Session tiếp tục đúng — state ở Postgres |
| P4.3 | Câu hỏi khớp tri thức brain | Trả lời kèm trích dẫn source_url Lark |
| P4.4 | Hội thoại 50 lượt | Prompt không phình (rolling summary); token/call ổn định |
| P4.5 | Fact ở session cũ, mở session mới | Agent vẫn biết (user_facts per user) |
| P4.6 | Đặt TTL rồi chờ purge | Session cũ xoá đúng hạn + audit |
| P4.7 | (nốt P2.8) Đổi credential giữa hội thoại | Ngữ cảnh giữ nguyên 100% |

## 9. P5 — Connector Registry + metering (⏳ kế hoạch)

| ID | Kịch bản | Kỳ vọng |
|----|----------|---------|
| P5.1 | Gọi connector chưa được grant | 403 + audit + error-map rõ |
| P5.2 | Cấp grant qua console → gọi lại | Chạy ngay, không restart |
| P5.3 | Thu grant giữa chừng | Call kế tiếp bị chặn ngay |
| P5.4 | Skill/tool hoàn toàn mới | Mỗi call có dòng tool_usage — tần suất/lỗi/chi phí theo skill |
| P5.5 | Thêm connector mock | Chỉ đăng ký adapter — không sửa core/agent |
| P5.6 | Connector bị rate-limit ngoài | Retry backoff; agent không sập; usage ghi lỗi |

## 10. P6 — Directory + A2A (⏳ kế hoạch)

| ID | Kịch bản | Kỳ vọng |
|----|----------|---------|
| P6.1 | AG-A đọc directory | Thấy AG-B + skill/domain/status; không thấy agent deactive |
| P6.2 | A gọi B (có grant) | Nhận kết quả; trace/audit 2 phía khớp req_id |
| P6.3 | A gọi C (không grant) | 403 + audit denied |
| P6.4 | Vòng lặp A→B→A | Hop 3 bị chặn, không treo queue |
| P6.5 | Target đang deactive | Lỗi "target inactive" ngay, không enqueue |
| P6.6 | Chi phí lượt A2A | Tính cho agent GỌI (caller-pays) trong mart |

## 11. P7 — Platform agents + HITL + Mart (⏳ kế hoạch)

| ID | Kịch bản | Kỳ vọng |
|----|----------|---------|
| P7.1 | DLQ vượt ngưỡng | AG-OPS alert Lark ≤5 phút kèm chẩn đoán |
| P7.2 | Đề xuất deactive agent lỗi (risk=high) | Card Lark → Duyệt thì thực thi; Từ chối thì thôi; audit đủ |
| P7.3 | Action quá expires_at | Tự expire + nhắc lại 1 lần |
| P7.4 | Điểm prod giảm sau publish | AG-EVAL cảnh báo + đề xuất rollback qua HITL |
| P7.5 | Đối chiếu mart 1 tuần với dữ liệu thô | Lệch ≤1% |
| P7.6 | Platform agent tự duyệt việc của mình | Bị chặn (separation of duty) + audit attempt |
| P7.7 | Pool credential còn 1 account | Cảnh báo sớm trước khi rơi xuống API |

---

**Tổng:** 14 CORE + 6 Brain + 6 Lark + 8 P1 + 9 P2 + 8 Stable = **51 case đã có** (46 ✅, 5 ⏳ chờ điều kiện ngoài/nghiệm thu với team đầu tiên) · P3–P7 = **32 case kế hoạch**. Cách chạy lại bộ smoke: script trong lịch sử deploy (P1/P2 smoke chạy trên VM), hoặc yêu cầu chạy lại bất kỳ nhóm nào.
