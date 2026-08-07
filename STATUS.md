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
| A9 | BigQuery sink → `AI_DB` | 🟡 | **cần**: scope BigQuery cho VM *hoặc* SA key |
| A10 | Domain công ty thay `sslip.io` | ⬜ | cần domain + DNS |

## B. Lõi platform

| # | Hạng mục | TT | Ghi chú |
|---|----------|----|---------|
| B1 | Registry agent (managed/external) + telemetry key + schema-per-agent | ✅ | Postgres VM, mỗi agent 1 schema |
| B2 | Collector: trace + resource index + **chặn agent deactivated (403)** | ✅ | kill switch cho agent external |
| B3 | Plugin telemetry Claude Code (hooks PostToolUse/Stop) | ✅ | control point khi dùng subscription |
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
| C8 | Notify qua Lark cho reviewer | 🟡 | **cần scope `contact:user.id:readonly`** (hoặc `LARK_NOTIFY_CHAT_ID`) |

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
| E1 | De/activate agent ⇄ bot/account Lark (không xoá dữ liệu) | ⬜ | **cần**: app admin + scope quản trị |

## F. Backlog tính năng (4 nhóm bạn đã chọn)

**Vận hành & tin cậy:** ⬜ cost/quota theo agent · ⬜ health monitor + cảnh báo Lark · ⬜ versioning/rollback prompt · ⬜ staging/canary
**Chất lượng & học hỏi:** ⬜ human feedback 👍/👎 có lý do · ⬜ golden set + regression test · ⬜ LLM judge (RIR/OFR/CTRL-Acc) · ⬜ marketplace prompt/skill
**Kiến thức & phối hợp:** ⬜ semantic search resource index · ⬜ second brain toàn công ty · ⬜ agent-to-agent handoff
**Quản trị & tuân thủ:** ⬜ audit log toàn platform · ⬜ RBAC theo phòng ban · ⬜ PII guard · ⬜ data retention

**Khác:** ⬜ SSO thay ô nhập email (reviewer/owner) · ⬜ parse PDF/Word server-side · ⬜ dọn agent demo trong registry · ⬜ nạp squad/KPI/thành viên thật

---

## Việc cần BẠN làm (đang chặn)

| Chặn | Việc | Mở khoá |
|------|------|---------|
| C8 | Cấp scope `contact:user.id:readonly` cho app `cli_aaf9aad57219deef` | Notify Lark cho reviewer |
| A9 | Thêm scope BigQuery cho VM (restart ngắn) **hoặc** SA key | Đẩy dữ liệu sang `AI_DB` |
| D4 | Add Minh Anh vào 1 nhóm họp | Chạy thật biên bản họp |
| E1 | Tạo Lark app admin + scope quản trị | Đồng bộ de/activate bot |
| F | Danh sách squad/KPI/thành viên thật | Nạp second brain, chấm điểm thật |
