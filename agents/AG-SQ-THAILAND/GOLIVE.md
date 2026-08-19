# Go-live checklist — AG-SQ-THAILAND (Ploy) · bản điền sẵn 12/08/2026

> Điền theo GOLIVE_CHECKLIST.md của platform (27 mục B — thiếu là bị chặn go-live).
> Nộp: trang **Golive** của agent trên console, hoặc `POST /v1/agents/AG-SQ-THAILAND/golive-checklist`.
> Mục `[CẦN ĐIỀN]` / `[CẦN CHỐT]` là chỗ Vinh/Thi phải quyết — còn lại đã điền từ tài liệu dự án.

## 1. Danh tính & tổ chức

| Mục | Giá trị |
|---|---|
| agent_id · tên · phiên bản | `AG-SQ-THAILAND` · Ploy — Trợ lý thị trường Thái Lan · 0.1.0 |
| Mô tả mục đích | Kho tri thức chung có nguồn cho squad TH; hỏi đáp qua Lark/Telegram/web; biên bản họp với gate chủ trì chốt |
| Owner | `[CẦN CHỐT: thint@hapas.vn (theo manifest) hay vinhnd@hapas.vn (CM, theo kế hoạch Ploy)]` |
| Backup owner | `[CẦN ĐIỀN email]` |
| Squad phục vụ | SQ-THAILAND (HAPAS Thailand — MATE MADE TH đã đóng 19/08/2026) — **là squad agent chính** |
| Thành viên team | Theo `configs/th_squads.json` — `[CẦN ĐIỀN lark_user_id từng người]` |
| Approver | Vinh (CM). Riêng biên bản họp: chủ trì cuộc họp đó. Giao việc: chỉ Vinh |
| Phối hợp người–máy | Agent tự làm: trả lời có nguồn, dựng nháp biên bản, index tài liệu. Phải hỏi người: chốt biên bản (chủ trì), duyệt tri thức (reviewer), duyệt task (console HITL) |
| Kênh làm việc chính | Nhóm Lark "Sawatdee HAPAS" (+ nhóm squad TH khi mở rộng) · web console `/agent/AG-SQ-THAILAND` |

## 2. KPI

| Mục | Giá trị |
|---|---|
| KPI squad (nguồn: PLAN.md M1–M3) | ≥20 mục tri thức duyệt sau 4 tuần · ≥80% câu trả lời có `source_url` · ≥80% thành viên hỏi ≥1 lượt/tuần · ≥90% cuộc họp có biên bản chốt trong 24h — đo bằng brain + traces + console, kỳ đo tuần |
| Target kỳ này + trọng số | `[CẦN ĐIỀN — đề xuất: M1 40% · M2 30% · M3 30%]` |
| KPI của agent ("có ích khi nào") | Tỉ lệ trả lời có nguồn ≥80% · thời gian có biên bản sau họp <30 phút · số câu hỏi không phải hỏi lại Vinh |
| Ngưỡng cảnh báo | `[CẦN ĐIỀN — đề xuất: usage 0 lượt/3 ngày · error rate >10%/ngày · cost >150% trung bình 7 ngày]` |

## 3. Dữ liệu & quyền

| Mục | Giá trị |
|---|---|
| Nguồn được truy cập | 19 nguồn Lark trong `configs/th_kb_files.json` + 8 nguồn báo cáo trong `configs/th_report_sources.json` + brain riêng của agent. BigQuery: **chưa dùng** Phase 1 |
| Dữ liệu KHÔNG đụng | Lương, đánh giá cá nhân, giá vốn, PII khách hàng (`configs/role_permissions.json` + chặn từ khoá trong `knowledge.py`) |
| Skill/MCP + lý do | `resource-index`, `brain` (kho có nguồn) · `transcribe` (biên bản) · `thailand_tools.py` local (bối cảnh TH từ config) |
| Ghi/sửa dữ liệu ở đâu | CHỈ: brain items `pending_review` + `actions/propose` (task qua HITL). Không ghi trực tiếp hệ thống nào khác, không tự gửi tin ngoài nhóm |

## 4. Kỹ thuật

| Mục | Giá trị |
|---|---|
| Auth model | Subscription của owner (`claude setup-token`) — manifest `auth: subscription`, không khoá chung. `LSR_MODEL_MODE=off` mặc định (thuần luật) |
| Kết nối Lark | **Bot** — app riêng "Sawadee HAPAS" (`cli_aaf6d2b3a5b8ded3`), long-connection. Đã add vào nhóm ✅ · scopes + publish `[ĐANG LÀM — Vinh]` · gateway + ingress `[CHỜ ADMIN]` |
| Telemetry | Bật trong manifest ✅ · trace thật về collector: `[CHỜ — cần register + 1 lượt chạy]` |
| Nơi chạy | `[CẦN CHỐT: container trên VM platform (khuyến nghị) hay máy khác — nếu external cần URL + người quản host]` |

## 5. Chất lượng & vận hành

| Mục | Giá trị |
|---|---|
| Bộ test | 32 case `tests.jsonl` + nhãn tool `tests/agent_tests.yaml` + regression đa lượt `tests/selfcheck_flows.py` (12 check gate HITL) — **pass 100% local 12/08**; chạy trên platform sau khi register |
| Trường hợp từ chối / escalation | Lương/PII/giá vốn → từ chối, chỉ bộ phận phụ trách · ngoài phạm vi TH → chỉ đúng kênh · giao việc bởi người ngoài Vinh → từ chối · Chapter Lead/BOD veto trong 24h |
| Rủi ro + giảm thiểu | Bịa số → chỉ trả lời có nguồn + luật cứng trong model.py · biên bản sai → gate chủ trì chốt (đã chống phủ định "chưa chốt" + chống chốt trùng) · Whisper chết → DLQ replay · cost → quota console |
| Review tuần đầu | `[CẦN ĐIỀN — đề xuất: Vinh đọc 100% output 3 ngày đầu, sau đó Hương mỗi ngày 1 lần]` |
| Lịch định kỳ | Phase 0: chưa có. Phase 1 sẽ thêm: draft báo cáo tuần (thứ 5) + nhắc mốc BST (thứ 2) — khai vào `schedule:` của manifest khi làm |
| Fail test định kỳ | `[CẦN ĐIỀN — đề xuất: owner sửa trong 48h, quá hạn thì tự deactivate theo luật platform]` |
| Kênh báo lỗi/góp ý | Reaction 👍👎 trên tin của bot + nhóm Lark squad |
| Nhịp review hiệu quả | `[CẦN ĐIỀN — đề xuất: 30' thứ 6 hằng tuần, Vinh + Thi + 1 người dùng thật]` |

## 6. Minh bạch

| Mục | Giá trị |
|---|---|
| Thành viên được thông báo bot đọc nhóm | Bản tin nháp đã soạn (Ploy tự viết 12/08) — đăng vào nhóm TRƯỚC khi tắt DRY_RUN. `[CHƯA ĐĂNG]` |
| Không đánh giá cá nhân ngoài phạm vi | Cam kết ✅ — không lưu lương/đánh giá cá nhân vào memory (`role_permissions.json`) |
