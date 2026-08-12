# PLOY — trợ lý thị trường Thái Lan, chạy trên LSR Agent Platform

> Bản map **kế hoạch Ploy (12/08/2026)** → **chuẩn platform**, sau khi khảo sát repo.
> Quyết định đã chốt với Vinh: **Ploy = AG-SQ-THAILAND mở rộng** — không tạo agent mới,
> không dựng hạ tầng riêng. Kế hoạch gốc: PLAN.md + FEATURES.md + PHAN-CONG-TEAM-TH.md
> (tài liệu Vinh giữ); file này là phần "đã điều chỉnh theo thực tế repo".

## 1. Trả lời các câu [CẦN XÁC NHẬN] của PLAN gốc

| # | Câu hỏi | Trả lời từ repo |
|---|---|---|
| a | Repo là codebase Jenny hay template rỗng? | **Không phải cả hai** — là LSR Agent Platform; Jenny chỉ là 1 agent-tenant. Scaffold AG-SQ-THAILAND đã có sẵn (commit b970e45) |
| b | Số TH lên BigQuery chưa? | Platform có connector BigQuery, nhưng USECASE ghi "chưa cần Phase 1" → Phase 1 vẫn đọc Lark doc. [Hỏi admin data] |
| c | Lark: tài khoản riêng hay chung? | Chuẩn platform: connector dùng chung, **agent không cầm secret Lark**. Manifest hỗ trợ `connect_mode: user` nhưng phải mở issue nhờ maintainer |
| d | Supabase riêng hay chung? | **Chung 1 project** — platform tự tạo schema riêng `agent_ag_sq_thailand` khi register. Bảng Jenny (conversations/messages/configs…) không tồn tại — platform đã lo state |
| e | Ai giữ vai People Ops TH? | Không có trong repo — **hỏi trực tiếp** (Ngọc nghỉ 27/07, phương án giữ vai từ VN chưa chốt) |
| f | 3 file .skill 05/08 đã lưu chưa? | **Chưa có trong repo** — Vinh gửi lại để commit vào `skills/` |

## 2. Kiến trúc sau điều chỉnh — cái gì của platform, cái gì của mình

| Ploy định tự dựng (plan gốc) | Dùng của platform (thực tế) |
|---|---|
| Gateway Lark OAuth polling + Telegram bot riêng | Mọi kênh → event gateway → job queue; agent poll `/v1/self/jobs`, trả lời `POST /v1/self/jobs/{id}/reply` |
| Bảng conversations/messages trên Supabase riêng | Context compiler `/v1/self/context` (instruction + summary + facts + tri thức) |
| Kho tri thức tự viết | Brain `/v1/self/brain/*` + pgvector RAG + console duyệt; index cục bộ = `configs/th_kb_files.json` |
| Whisper pipeline của Jenny | Whisper server platform — `transcribe.py` đã có client |
| Tự tạo Lark task | `POST /v1/self/actions/propose` + HITL duyệt trên console — khớp luật "Ploy không tự quyết" |
| Dashboard riêng / Vercel | Console sẵn: `https://app.34-126-154-135.sslip.io/agent/AG-SQ-THAILAND` |
| Config trên "dashboard Supabase" | Phase 0: `configs/*.json` trong repo · sau register: schema riêng của agent trên Supabase chung |

**Phần MỚI của Ploy (nằm gọn trong `agents/AG-SQ-THAILAND/`):**

```
agents/AG-SQ-THAILAND/
├── thailand_tools.py     # 6 nhóm tool TH (24 tool: 7 ready, 17 stub) — Data/Tech
├── configs/*.json        # 13 config key — mỗi key 1 chủ (xem skills/README.md)
├── skills/*.md           # skill từng người — 1 người 1 file
└── (consumer/knowledge/minutes/transcribe.py — khung sẵn có của Thi/Thái/Hương)
```

## 3. Quy trình git ĐÚNG cho team Thái (thay mục 3 của bảng phân công)

⚠️ Khác bản phát chiều nay: **không có branch `feature/th-agent-ploy`**, không có
`skills/` ở gốc repo — mọi thứ nằm trong `agents/AG-SQ-THAILAND/**` trên branch chung
`agent/thailand-AG-SQ-THAILAND`. Quy trình chuẩn (mô hình branch chung, team có quyền
write — cập nhật 12/08 19:59): xem **[TEAM.md](TEAM.md)**, tóm tắt:

```bash
git clone https://github.com/LamsonRetail/lsr-agent-platform.git && cd lsr-agent-platform
bash scripts/install-git-hooks.sh              # BẮT BUỘC — chặn commit chạm core
git checkout agent/thailand-AG-SQ-THAILAND && git pull
# ...sửa file CỦA MÌNH trong agents/AG-SQ-THAILAND/ ...
bash scripts/check-scope.sh --vs-main          # tự kiểm trước khi push
git commit -m "th: ..." && git push origin agent/thailand-AG-SQ-THAILAND
```

Luật: không sửa file người khác · `git pull` trước khi làm · commit message bắt đầu
`th:` · KHÔNG push main · tuyệt đối không commit secret/token.

## 4. Ba mức sửa hành vi (mục tiêu buổi học — vẫn đúng, đổi chỗ sửa)

1. **Đổi chi tiết (90%)** → sửa `configs/<key>.json` (2 phút). Phase 0: commit + PR;
   sau khi register: sửa trong schema agent, đổi ngay không cần deploy.
2. **Đổi cách làm việc** → sửa `skills/th-*.md` của mình (15 phút) → PR. Nạp ở phiên mới.
3. **Việc mới hẳn** → thêm tool vào `thailand_tools.py` bằng Claude Code trong repo:
   *"Đọc agents/AG-SQ-THAILAND/PLOY.md. Thêm tool `th_x` làm Y, trả về Z. Thêm test case
   vào TESTCASES.md + tests.jsonl trước. Lập kế hoạch trước, đừng code ngay."*

## 5. Trạng thái tool (chiều 12/08) & lộ trình

- ✅ **Ready (7)**: `th_kb_index` · `th_base_targets` · `th_season_calendar` ·
  `th_milestone_list` · `th_milestone_check` · `th_milestone_conflict` · `th_context`
  — chạy từ config, đã có test (tests.jsonl case 10–15).
- ⬜ **Stub (17)**: nhóm báo cáo + kb_read (Phase 1) · giao việc + nghiên cứu (Phase 2)
  · họp→assignment (Phase 3). Agent nạp được tool list đầy đủ: `python3 thailand_tools.py --list`.
- Luồng **biên bản họp** (recording → nháp → chủ trì "chốt" → lưu kho + đề xuất task)
  đã chạy sẵn từ scaffold của Thi (`minutes.py`), không phải chờ Phase 3.

Lộ trình 4 phase + gate "1 người ngoài Vinh dùng thật 1 tuần" giữ nguyên như PLAN gốc.

## 6. Cần core / admin làm (mở issue, nhãn `agent:AG-SQ-THAILAND`)

Kênh Lark của Ploy dùng **app riêng "Sawadee HAPAS"** (`app_id: cli_aaf6d2b3a5b8ded3`,
Vinh sở hữu trên Lark Developer Console, đã Enabled + published).

| # | Việc | Chi tiết | Chặn tính năng |
|---|---|---|---|
| 1 | Nối app Sawadee HAPAS vào event gateway | Gateway hiện long-connection 1 app qua env `MINH_ANH_LARK_APP_ID/SECRET` (`infra/lsr-platform/event_gateway/gateway.py:26`) → chạy thêm 1 container gateway với credential app này (không cần sửa code), hoặc core đổi env đa app. Vinh gửi App Secret cho admin **qua kênh an toàn** — không repo, không chat nhóm | Agent chưa nhận tin Lark thật |
| 2 | Gán ingress trên Console | `routing_binding`: channel=`lark`, app_id=`cli_aaf6d2b3a5b8ded3` → `AG-SQ-THAILAND` (+ chat_id nhóm khi add bot) | nt |
| 3 | Cấp enroll-token + register agent | `scripts/lsr_adopt.py` — xem README | Agent chưa poll được job |
| 4 | Mở đường tải file recording qua gateway (C1 của Thi) | gateway chỉ đẩy text/message_type, chưa có file_key | Luồng biên bản từ recording |
| 5 | Đọc Lark doc/base qua `/v1/lark/*` cho agent | hoặc cấp scope docs/base cho app Sawadee HAPAS rồi share doc với bot | `th_kb_read`, cả nhóm báo cáo F2 |
| 6 | (Nếu sau này đổi webhook mode) | Caddy chưa route công khai cho gateway; handler webhook chưa verify chữ ký + chưa lấy `sender_open_id` | — |

## 6b. Việc Vinh tự làm trên Lark Developer Console (không cần admin)

1. **Permissions & Scopes** — thêm cho bot: nhận/gửi tin (`im:message`,
   `im:message.group_at_msg`, `im:message.p2p_msg`), thông tin chat (`im:chat:readonly`),
   tải file trong tin nhắn (`im:resource` — cần cho recording); (chuẩn bị F2:
   `docx:document:readonly` · `drive:drive:readonly` · `bitable:app:readonly`).
2. **Events & Callbacks** — subscribe `im.message.receive_v1`; chọn chế độ nhận
   **Long Connection** (không cần mở URL công khai).
3. **Create version & publish** lại sau khi đổi scope (scope mới chỉ có hiệu lực sau khi
   duyệt phiên bản).
4. **Add bot vào nhóm Lark của squad TH** → báo admin lấy `chat_id` điền vào ingress
   (hiện ra trong log gateway ở tin nhắn đầu tiên).
5. **Thông báo minh bạch** cho squad việc bot đọc nhóm (yêu cầu tuân thủ platform).
6. Gửi **App Secret** cho admin qua kênh an toàn. Nếu lỡ lộ secret ở đâu công khai →
   bấm nút xoay (↻) cạnh App Secret để đổi ngay.

## 7. Bẫy đã biết (đọc trước khi test)

- Câu chứa **"chốt"/"duyệt"** bị gate xác nhận biên bản bắt trước khi tới tool TH
  (`minutes.is_confirm` khớp chuỗi con) — hỏi mốc thì dùng "hạn", "deadline".
- Hai base target song song: **9,3M THB (tháng) · 8,0M THB (ngày, rebase 22/07)** —
  mọi số phải nói rõ base nào.
- %MTD = target lũy kế pro-rata theo ngày, không phải actual ÷ target cả tháng.
- Ngày launching Travel bag đang lệch 3 nguồn — Ploy từ chối chọn hộ cho tới khi chốt
  nguồn chuẩn trong `configs/th_bst_milestones.json`.
