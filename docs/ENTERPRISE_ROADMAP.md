# Enterprise roadmap — tính năng platform cần có

Đối chiếu với chuẩn enterprise 2026 (Microsoft Cloud Adoption Framework cho AI agents;
Arthur "Agentic AI Observability Playbook"; các hướng dẫn evaluation/identity/audit).
Mô hình 4 lớp: **Control plane · Data governance · Security · Dev standards** + hai trục
xuyên suốt **Observability** và **Evaluation (ADLC)**.

Ký hiệu: ✅ đã có · ➕ đề xuất bổ sung · 🔷 ưu tiên cao

---

## 1. Control plane & Identity
- ✅ Agent registry (managed/external), owner + lifecycle, schema-per-agent
- ✅ Auth per-owner (subscription), cấm api key/auth chung
- ✅ Cost & quota theo agent + cảnh báo
- ✅ Audit log toàn platform
- 🔷➕ **Agent = first-class identity**: mỗi agent một service-identity riêng (client_id/secret
  hoặc token scope hẹp) thay vì dùng chung app Lark; mọi hành động gắn identity đó.
- ➕ **Discovery "shadow agent"**: quét định kỳ nguồn (Lark bot list, process báo trace lạ)
  để phát hiện agent chưa đăng ký → buộc đăng ký hoặc chặn.
- ➕ **Policy engine tập trung**: khai báo policy (data access, tool cho phép, giờ chạy)
  áp đồng nhất mọi agent, thay vì rải rác trong từng manifest.
- ➕ **Ownership & approval record**: mỗi agent có người phê duyệt golive + backup owner
  (đã có cột) → hiển thị "ai chịu trách nhiệm" trên dashboard.

## 2. Security & guardrails (runtime)
- ✅ Kill-switch (collector 403) + de/activate ⇄ bot Lark
- ✅ PII guard (redact ở collector)
- 🔷➕ **Prompt-injection / jailbreak filter** ở input: chặn mẫu tấn công trước khi tới model
  (rủi ro số 1 của agentic AI theo mọi source).
- 🔷➕ **Output guardrails**: chặn rò rỉ dữ liệu mật/PII trong câu trả lời (DLP), chặn
  hành động ngoài phạm vi (vd gửi tiền, xoá dữ liệu) — chặn ở tool layer.
- ➕ **Least-privilege tool scoping**: mỗi agent chỉ gọi được tool/skill đã cấp; log mọi
  tool call kèm tham số (một phần đã có qua telemetry).
- ➕ **Adversarial/red-team trước golive**: bộ test tấn công (prompt injection, data
  exfiltration) là mục bắt buộc trong golive checklist.
- ➕ **Incident response runbook**: quy trình tắt nhanh + giữ log forensic khi agent lỗi.
- ➕ **Secret hygiene tự động**: quét manifest/PR chặn secret (mở rộng validator hiện có).

## 3. Data governance & compliance
- ✅ Postgres schema-per-agent + BigQuery sink + traceability (source_url)
- 🔷➕ **Data retention & purge**: TTL cho trace/memory/log + job xoá/ẩn danh tự động
  (chuẩn CAF coi là bắt buộc; ta đang giữ vô thời hạn).
- ➕ **Data residency & phân tách corp/public**: tách rõ dữ liệu nội bộ vs public; agent
  public không chạm dữ liệu nội bộ.
- ➕ **Quyền kế thừa theo user**: khi agent truy xuất dữ liệu thay người dùng, kế thừa
  đúng quyền của người đó (không cấp quyền rộng).
- ➕ **Data lineage**: mỗi câu trả lời/tri thức truy ngược được nguồn dữ liệu đã dùng.

## 4. Observability
- ✅ Telemetry (6 chỉ số hành vi + token), collector, health monitor
- ✅ Dashboard chi phí + sức khoẻ
- 🔷➕ **Trace-level explorer**: xem chi tiết 1 lần chạy (chuỗi tool call, prompt, kết quả)
  để debug — hiện mới có tổng hợp.
- ➕ **Latency & error-rate metrics**: theo dõi độ trễ, tỉ lệ lỗi, vòng lặp retry
  (source cảnh báo "đúng nhưng chậm/đắt vẫn là fail").
- ➕ **Alert routing vào SOC/Lark theo severity** + ngưỡng bất thường (anomaly).
- ➕ **Drift detection**: cảnh báo khi hành vi/chi phí/độ dài output lệch bất thường.

## 5. Evaluation & quality (ADLC)
- ✅ Test & Learn (review→active, agent+người, fail→training)
- ✅ Golden set + regression + LLM-judge (pluggable)
- 🔷➕ **Vòng lặp "failure → regression test"**: mỗi lỗi production tự thành ca golden mới
  (source: golden set là "artifact tin cậy quan trọng nhất").
- 🔷➕ **Shadow / canary khi đổi prompt/model**: chạy song song bản mới vs cũ, so kết quả
  trước khi cắt traffic (chống lỗi âm thầm khi scale).
- ➕ **Tiered LLM-judge**: model rẻ chấm vòng 1, bất đồng mới escalate model mạnh
  (giảm 60–70% chi phí eval).
- ➕ **Human feedback 👍/👎 có lý do** gắn vào trace → nạp vào golden set.
- ➕ **Release gate bằng eval**: đổi prompt/model phải đạt ngưỡng regression mới được golive.

## 6. Reliability & operations
- ✅ CI/CD auto-deploy + health gate
- 🔷➕ **Versioning & rollback prompt/skill**: lưu version, rollback 1 click khi bản mới tệ.
- ➕ **Staging/canary environment** tách khỏi production.
- ➕ **Quota/rate-limit theo agent ở runtime** (chặn vòng lặp retry đốt token 50×).
- ➕ **Backup & DR** cho Postgres (định kỳ, khôi phục có kiểm thử).

## 7. Multi-agent & knowledge
- ✅ LSR Brain (consolidate hàng tuần, reviewer theo domain, conflict về agent owner)
- ✅ Resource index (chống long-memory) + full-text search
- ➕ **Semantic search** resource index (embeddings) thay full-text.
- ➕ **Agent-to-agent handoff (A2A)**: giao việc giữa agent theo chuẩn, có log.
- ➕ **Second brain toàn công ty** + marketplace prompt/skill dùng lại.

## 8. Access & tổ chức (RBAC)
- 🔷➕ **RBAC theo phòng ban/vai trò**: admin/owner/reviewer/viewer; hiện admin token đơn.
- ➕ **SSO Lark** thay ô nhập email (reviewer/owner) — bỏ nhập tay, gắn danh tính thật.
- ➕ **Approval workflow**: hành động nhạy cảm (golive, đổi belief) cần 2 người duyệt.

---

## ✅ Đã làm — nền forward-compat (chống rework)
Đã dựng sẵn để 5 sóng dưới đây *cắm vào* mà không sửa agent/không phá dữ liệu cũ:
- **Bề mặt enforcement DUY NHẤT**: collector `/v1/policy/check` + hook `PreToolUse`/
  `UserPromptSubmit` trong plugin bắt buộc + bảng `policies` (admin ghi). Hiện no-op
  (rỗng→allow) → **Sóng 1 chỉ cần thêm rule**, không đụng agent. Verify: deny theo
  tool/pattern hoạt động.
- **Trace** đã có `duration_ms/status/error` (tích luỹ sẵn cho Sóng 4).
- **Audit `actor`** lấy từ header `X-Actor` (server web đóng dấu) → sẵn sàng cho RBAC.
- **Con trỏ version prompt** trong manifest + registry → rollback = đổi con trỏ.
- **`retention_config`** khai báo TTL + index thời gian (chưa bật purge).

## Đề xuất thứ tự (sóng tiếp theo)
1. **Guardrails runtime** (prompt-injection + output DLP) — rủi ro bảo mật lớn nhất còn hở.
2. **Data retention & purge** — chuẩn CAF bắt buộc, ta đang giữ vô hạn.
3. **RBAC + SSO Lark** — nền cho mọi tính năng quản trị sau.
4. **Trace explorer + latency/error metrics** — hoàn thiện observability để debug thật.
5. **Versioning/rollback + canary + release-gate-bằng-eval** — an toàn khi đổi prompt/model.

## Nguồn
- Microsoft Cloud Adoption Framework — Govern & secure AI agents
- Arthur — Agentic AI Observability Playbook 2026; Best AI Governance Platforms 2026
- Confident AI / digitalapplied — AI Agent Evaluation 2026 (golden set, LLM-judge, canary)
- Teiva — Securing Enterprise AI Agents: Identity, Permissions, Auditability
