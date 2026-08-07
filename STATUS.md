# Trạng thái dự án — LSR Agent Platform

Cập nhật: 2026-08-07 · Repo: `LamsonRetail/lsr-agent-platform` (private)
Ký hiệu: ✅ xong & verify live · 🟡 code xong, chờ điều kiện bên ngoài · ⬜ chưa làm

---

## A. Hạ tầng & vận hành

| # | Hạng mục | TT | Ghi chú |
|---|----------|----|---------|
| A1 | VM GCP + SSH (deploy key, alias `lsr-gcp`) | ✅ | `digital-transformation-hosting`, Ubuntu 22.04 |
| A2 | Docker stack `/opt/lsr-platform` | ✅ | postgres · collector · platform_api · minh_anh_bot · caddy · web · bq_sink · lsr_brain |
| A3 | Caddy HTTPS công khai + gateway token + rate-limit | ✅ | `platform/collector/app.34-126-154-135.sslip.io`, 120 req/phút |
| A4 | UI backend tự host (basic-auth) | ✅ | `https://app.34-126-154-135.sslip.io` |
| A5 | GitHub repo + CI test (pytest + validator chuẩn agent) | ✅ | chặn merge nếu agent sai chuẩn |
| A6 | CI/CD auto-deploy VM (rsync + compose + **health gate**) | ✅ | fail nếu API không lên |
| A7 | Vercel app + git auto-deploy | ✅ | `hapas/lsr-platform-web`, Root Dir = `apps/platform-web` |
| A8 | LiteLLM gateway | ✅ | **tắt hẳn** (profile `optional`) do dùng subscription |
| A9 | BigQuery sink → `AI_DB` | ✅ | SA `lsr-bq-sink@surya-495408` ghi cross-project vào `ganesha:AI_DB`; verify có dữ liệu |
| A10 | Domain công ty thay `sslip.io` | ⬜ | cần domain + DNS |

## B. Lõi platform

| # | Hạng mục | TT | Ghi chú |
|---|----------|----|---------|
| B1 | Registry agent (managed/external) + telemetry key + schema-per-agent | ✅ | Postgres VM, mỗi agent 1 schema |
| B2 | Collector: trace + resource index + **chặn agent deactivated (403)** | ✅ | kill switch cho agent external |
| B3 | Plugin telemetry Claude Code (hooks Pre/PostToolUse, UserPromptSubmit, Stop) | ✅ | control point + điểm chặn runtime (Policy API); cài qua marketplace |
| B3b | **Self-service**: enroll (`/v1/agents/enroll`) + marketplace plugin + data-plane mở cho agent ngoài | ✅ | thành viên tự tạo agent (plugin/git), key per-agent, [ONBOARDING.md](ONBOARDING.md) |
| B4 | Chuẩn agent + validator CI + **auth per-owner** | ✅ | cấm api key/auth chung |
| B5 | Đăng ký agent có sẵn (`lsr_adopt.py`) | ✅ | giữ nguyên cấu hình, không sửa code |
| B6 | Backend riêng từng agent (`apps/agents/<id>`) + scaffolder | ✅ | conflicts của agent nằm ở đây |
| B7 | Đánh giá: squad scorer, agent scorer, auto-deactivate | ✅ | 2 nhánh tách biệt |
| B8 | 6 chỉ số hành vi tool (TSR/CTUR/RIR/OFR/UTR/CTRL-Acc) | ✅ | + thống kê token |
| B9 | Test & Learn (review→active, agent+người, fail→training, sinh test auto) | ✅ | API + UI thao tác thật |
| B10 | Resource index (chống long-memory) | ✅ | full-text search |
| B11 | Second brain team + checklist golive (27 mục) + **gate chặn golive** | ✅ | bảng chung, không rải rác |

## C. LSR Brain (tri thức)

| # | Hạng mục | TT | Ghi chú |
|---|----------|----|---------|
| C1 | Agent AG-LSR-BRAIN + consolidate (lọc nhạy cảm, phát hiện mâu thuẫn) | ✅ | |
| C2 | Chạy định kỳ **hàng tuần (CN 20h)** | ✅ | service `lsr_brain` |
| C3 | Shared beliefs (chỉ admin) + import file → sửa → cập nhật | ✅ | tab riêng |
| C4 | Reviewer theo chuyên môn + tag/keywords + add/remove | ✅ | tab riêng, 403 nếu sai domain |
| C5 | Conflict → agent owner xác nhận (ở backend agent) | ✅ | |
| C6 | Auto-route chuyên môn theo keywords | ✅ | notify đúng người |
| C7 | **Link Lark đối chứng** (`source_url`) xuyên suốt | ✅ | UI cảnh báo "thiếu nguồn" |
| C8 | Notify qua Lark cho reviewer | ✅ | available range đã mở (78 user/2 phòng ban); tra open_id OK cho reviewer trong range (vd `huyennn@hapas.vn`). Tài khoản ngoài range (vd BOD `thint@hapas.vn`) rơi về fallback nhóm admin |

## D. Minh Anh (meeting agent)

| # | Hạng mục | TT | Ghi chú |
|---|----------|----|---------|
| D1 | Đăng ký + tự share từ điển meeting-notes cho agent mới | ✅ | live |
| D2 | Listener Lark long-connection (tenant permission) | ✅ | chỉ xử lý chat được add |
| D3 | Client transcript Whisper | ✅ | server large-v3/CUDA |
| D4 | Workflow biên bản (transcript→nháp→confirm→task) | 🟡 | **cần**: add bot vào nhóm họp + tắt `DRY_RUN` |

## E. Lark admin

| # | Hạng mục | TT | Ghi chú |
|---|----------|----|---------|
| E1 | De/activate agent ⇄ bot Lark (không xoá dữ liệu) + audit | ✅ | code + audit chạy; scope `im:chat` đã cấp. Kích hoạt thật khi agent có `lark_chat_ids` bị de/activate |

## F. Backlog tính năng (4 nhóm bạn đã chọn)

**Vận hành & tin cậy:** ✅ cost/quota theo agent (dashboard + hạn mức + cảnh báo Lark tự động) · ✅ health monitor + cảnh báo Lark (agent active im lặng) · ⬜ versioning/rollback prompt · ⬜ staging/canary
**Chất lượng & học hỏi:** ⬜ human feedback 👍/👎 có lý do · ✅ golden set + regression test · ✅ LLM judge (pluggable, JUDGE_URL) · ⬜ marketplace prompt/skill
**Kiến thức & phối hợp:** ⬜ semantic search resource index · ⬜ second brain toàn công ty · ⬜ agent-to-agent handoff
**Quản trị & tuân thủ:** ✅ audit log toàn platform · ⬜ RBAC theo phòng ban · ✅ PII guard (redact ở collector) · ⬜ data retention

**Khác:** ⬜ SSO thay ô nhập email (reviewer/owner) · ✅ parse PDF/Word server-side (endpoint /v1/extract + wire import beliefs) · ✅ dọn agent demo trong registry (endpoint /v1/agents/{id}/delete) · ⬜ nạp squad/KPI/thành viên thật

---

## Việc cần BẠN làm (đang chặn)

| Chặn | Việc | Mở khoá |
|------|------|---------|
| D4 | Add Minh Anh vào 1 nhóm họp + tắt `DRY_RUN` | Chạy thật biên bản họp |
| A10 | Domain thật (dùng khi golive mass) | Thay `sslip.io` |
| F-data | Danh sách squad/KPI/thành viên thật (cung cấp sau khi chạy thật) | Nạp second brain, chấm điểm thật |

> ✅ C8 (available range đã mở), E1 (scope `im:chat` đã cấp) — đã xong.
> Registry đã có 2 agent thật: **AG-MINH-ANH**, **AG-LSR-BRAIN**.
