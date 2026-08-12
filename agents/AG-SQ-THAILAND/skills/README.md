# Skills của Ploy — mỗi người 1 file, không ai đụng file của ai

> Skill = **năng lực chung** (file .md, mô tả "khi được hỏi X thì làm theo trình tự Y").
> Chi tiết hay thay đổi (token doc, target, lịch lễ, danh sách người) = **config JSON**
> ở [../configs/](../configs/) — sửa config KHÔNG cần deploy.
> Quy trình git (branch chung — xem [../TEAM.md](../TEAM.md)) và mapping kế hoạch
> Ploy → platform: [../PLOY.md](../PLOY.md).

## Bảng phân công (đường dẫn đã chỉnh theo chuẩn platform)

| Người | Tính năng | File skill (chỉ mình sửa) | Config key (chỉ mình sửa) |
|---|---|---|---|
| **Vinh (CM)** | Persona + phân quyền + F1 tri thức | `th-internal-knowledge.md` ✅ | `persona` · `th_context` · `role_permissions` · `th_squads` |
| **Hương (KD HAPAS)** | F2 báo cáo — 8 nguồn & base target | `th-weekly-report.md` ⬜ | `th_report_sources` · `th_base_targets` |
| **Trang (KD MATE MADE)** | Bối cảnh brand MM | `th-brand-matemade.md` ⬜ | `th_context_mm` |
| **Tùng (MKT Manager)** | F3 lịch mùa vụ & dịp lễ | `th-season-calendar.md` ⬜ | `th_season_calendar` |
| **Khôi (Sản phẩm)** | F3 mốc BST | `th-bst-milestones.md` ⬜ | `th_bst_milestones` |
| **Hạnh (Booking)** | F4 giao việc & đôn đốc | `th-assignments.md` ⬜ | (dùng `th_squads` của Vinh) |
| **People Ops [CẦN XÁC NHẬN AI]** | Tri thức phần con người | `th-people-ops.md` ⬜ | `th_kb_files` |
| **Data/Tech** | Scaffold tool + seed config | `../thailand_tools.py` ✅ | (seed 13 key ✅) |

Toàn bộ 13 config key đã được seed sẵn giá trị từ PLAN — mỗi người mở file JSON của
mình, kiểm tra và sửa cho đúng thực tế (chỗ nào ghi `[CẦN XÁC NHẬN]` / `[CẦN BỔ SUNG]`
là chỗ đang chờ chính bạn điền).

## Skill viết thế nào

Mỗi skill .md gồm 4 phần: **Khi nào dùng** · **Trình tự** · **Luật** (điều bắt buộc /
điều cấm) · **Nghiệm thu** (1 câu hỏi thật + câu trả lời đạt). Xem mẫu:
[th-internal-knowledge.md](th-internal-knowledge.md).

Cách nạp: Phase 2 khi `answer()` chuyển sang Claude Agent SDK, skills được ghép vào
system prompt theo `lsr-agent.yaml` → sửa skill là đổi hành vi ở **phiên mới**, không
cần deploy lại container.

## Skill tái dùng, KHÔNG viết mới

`lsr-doc-style` · `lsr-report-formats` · `th-market-research` (đã đóng gói 05/08, gửi
Vinh) — **chưa có trong repo**. Vinh gửi lại để commit vào thư mục này; ai cần recipe
nghiên cứu thì chờ bản đó, đừng tự viết bản thứ hai lệch nhau.
