# MAI — Trợ lý AI Khối KD Online VN · PLAN

**Bản kế hoạch để Claude Code build. Đọc hết mục 1–5 rồi mới code.**
Chủ sở hữu: Rooky (Head of Online Business) · Team: KD Online VN · Branch: `feature/vn-agent-mai`
Lập: 12/08/2026 · Nền tảng: **tái dùng kiến trúc Jenny (LSR BOD Assistant)**
Tên "MAI" là đề xuất, đổi được bằng 1 dòng config `persona`.

---

## 0. EXECUTIVE SUMMARY (5 dòng)

1. MAI là một **"nhân sự" của Khối KD Online VN**, không phải chatbot — cả khối dùng chung 1 agent, mỗi người hỏi theo vai trò RACI của mình, dữ liệu và bộ nhớ tập trung một chỗ.
2. **7 nhóm tính năng**, trải Phase 0 → Phase 3, xếp theo thứ tự build: Tri thức nội bộ → Ads-ops 10 bước (trục chính) → Báo cáo WBR → Lịch mùa vụ & mốc BST → Giao việc RACI → Nghiên cứu → Biên bản họp. **Không phải xong hết trong tuần này.**
3. **Tái dùng 100% xương sống Jenny** (Claude Agent SDK + Supabase + gateway Lark chạy bằng tài khoản người dùng + dashboard). Không viết lại hạ tầng — chỉ thêm 1 MCP server `vn` + skills + configs.
4. **Nguyên tắc bất di bất dịch:** skill = năng lực chung (`.md`), chi tiết hay thay đổi = configs trên Supabase. Đổi hành vi không cần deploy — đây chính là mục tiêu học "điều chỉnh tính năng nhanh".
5. **Chốt phạm vi Phase 0 (2–3h):** agent trả lời được trong Lark/Telegram bằng persona VN + tra được kho tri thức 3 ngành → **demo thật, không demo giả.**

---

## 1. BỐI CẢNH — vì sao cần agent này

Bốn nút thắt agent giải được, mỗi cái có bằng chứng cụ thể:

| Nút thắt | Bằng chứng | MAI làm gì |
|---|---|---|
| **Chuyên viên đốt thời gian vào phần lặp lại** | Quy trình Ads 10 bước: thu thập idea, sản xuất, thao tác camp, gom số — tất cả tốn công, làm bằng tay | Gánh phần THỰC THI của 10 bước; chuyên viên chỉ giữ 5 cổng WHY |
| **Tri thức nằm trong đầu quản lý** | JTBD, danh mục 3 ngành, RACI, phân tích đối thủ (edoris/bostanten/mossdoom/ELLY), khung năng lực — team không đọc nên hỏi lại | Hỏi–đáp trên chính các file đó, có trích nguồn |
| **Báo cáo tuần gom tay, thiếu cấu trúc** | Có template WBR (FACT→WHY→SO WHAT→ACTION) nhưng phải gom số từ 3 kênh Ads + 2 sàn + Lark Base | Tự gom nguồn → dựng WBR theo template, chờ duyệt |
| **2 ngành mới (TS/NH) thiếu bối cảnh riêng** | RACI đã tách PM ngành TS & NH; số ngành mới dễ bị gộp nhầm với Túi | Tách bối cảnh & số theo ngành, không gộp |

---

## 2. KIẾN TRÚC — tái dùng Jenny, chỉ thêm lớp VN

```
[ Lark (user OAuth polling) ] ─┐
[ Telegram (demo/backup)    ] ─┼─▶ Gateway (tái dùng Jenny)
                               │        │
                               │        ▼
                               │   Claude Agent SDK (main loop)
                               │        │  nạp: persona + skills(.md) + tool list
                               │        ▼
                               │   MCP server "vn"  ◀── mới, cần build
                               │        │  (vietnam_tools.py)
                               ▼        ▼
                        Supabase (configs + memory)   ◀── thêm rows, không đổi schema
                               │
             Data warehouse / Lark Base / export Ads Manager · Shopee · TikTok Shop
```

**Không đụng vào:** gateway, vòng lặp agent, cơ chế nạp skill, dashboard config, pipeline họp của Jenny.
**Thêm mới:** `vn/vietnam_tools.py` (MCP server), thư mục `skills/vn-*.md`, các config key prefix `vn_` trên Supabase.

**Quy ước:**
- 1 tính năng = 1 skill `.md` + 0..n config key + 0..n tool.
- Tool **thuần đọc/dựng**; **cấm** `Bash/Write/Edit` trên VPS.
- Mọi số MAI trả ra phải kèm **nguồn + thời điểm + base**; ước tính ghi rõ.

---

## 3. DANH SÁCH SKILLS (mỗi file 1 người sở hữu — xem PHÂN CÔNG)

| Skill file | Nội dung | Config phụ thuộc |
|---|---|---|
| `skills/vn-internal-knowledge.md` | Persona, cách tra kho 2 bước, luật trích nguồn, phân quyền | `persona`, `vn_context`, `role_permissions`, `vn_squads` |
| `skills/vn-ads-workflow.md` ⭐ | Quy trình 10 bước, 5 cổng WHY, 3 mức tự động hoá, naming convention, luật scale/kill | `vn_ads_rules`, `vn_naming_convention` |
| `skills/vn-creative-content.md` | Sinh angle/copy/hook/brief, chuẩn brand voice, rà chính sách FB | `vn_brand_voice` |
| `skills/vn-nganh-trangsuc.md` | Bối cảnh ngành Trang sức (tệp, vùng giá, đối thủ) | `vn_context_ts` |
| `skills/vn-nganh-nuochoa.md` | Bối cảnh ngành Nước hoa | `vn_context_nh` |
| `skills/vn-weekly-report.md` | Template WBR, khung FACT→WHY→SO WHAT→ACTION, 2 bẫy base/MTD | `vn_report_sources`, `vn_base_targets` |
| `skills/vn-season-calendar.md` | Dịp lễ & peak VN kèm kết luận làm/không làm | `vn_season_calendar` |
| `skills/vn-bst-milestones.md` | Mốc BST, đếm ngược, phát hiện lệch ngày | `vn_bst_milestones` |
| `skills/vn-assignments.md` | Luồng giao việc 4 yếu tố, escalation theo RACI | (dùng `vn_squads`) |
| `skills/vn-research.md` | SOP nghiên cứu + luật A/B/C, dựng report | `vn_research_sources` |
| `skills/vn-people-ops.md` | Tri thức tổ chức, tuyển dụng, khung năng lực | `vn_kb_files` |

---

## 4. DANH SÁCH TOOLS (`vietnam_tools.py` — Data/Tech scaffold, stub trước)

Nhóm và tool (chi tiết input/output ghi ở docstring khi build):

- **Ads-ops:** `vn_jtbd_bank`, `vn_product_match`, `vn_idea_scan`, `vn_creative_brief`, `vn_edit_variants`, `vn_camp_build`, `vn_camp_ops`, `vn_ads_report`, `vn_ads_review`, `vn_scale_kill_reco`
- **Tri thức:** `vn_kb_index`, `vn_kb_read`, `vn_review_report`
- **Báo cáo:** `vn_numbers_read`, `vn_report_draft`, `vn_report_charts`, `vn_report_publish`
- **Mùa vụ & mốc:** `vn_season_calendar`, `vn_milestone_list`, `vn_milestone_check`, `vn_milestone_conflict`
- **Giao việc:** `vn_assignment_create`, `vn_assignment_list`, `vn_assignment_update`, `vn_assignment_remind`, `vn_assignment_escalate`
- **Nghiên cứu:** `vn_research_index`, `vn_research_search`, `vn_research_sop`, `vn_research_report_build`
- **Họp (tái dùng Jenny):** `vn_meeting_to_assignment` (còn lại dùng tool họp của Jenny)

> Phase 0 chỉ cần **stub đủ 7 nhóm** + implement thật nhóm **Tri thức** (`vn_kb_index`, `vn_kb_read`). Các nhóm khác implement dần theo lộ trình §6.

---

## 5. SEED CONFIG KEYS (Supabase — Data/Tech seed, các owner điền nội dung)

| Config key | Kiểu | Ai điền | Ghi chú |
|---|---|---|---|
| `persona` | text | TP Digital | Tên MAI, giọng, xưng hô, độ dài trả lời |
| `vn_context` | json | TP Digital | Target tháng/quý, 2 brand, 3 ngành, mục tiêu KD hiện tại |
| `role_permissions` | json | TP Digital | Map vai trò RACI → quyền xem/làm (theo §5 FEATURES) |
| `vn_squads` | json | TP Digital | Cây tổ chức: ai thuộc nhóm nào, báo cáo lên ai (từ RACI) |
| `vn_p2p_partners` | list | TP Digital | Whitelist chat riêng |
| `vn_ads_rules` | json | TN FB Ads | Ngưỡng scale/kill, trần ngân sách, khẩu vị rủi ro |
| `vn_naming_convention` | text | TN FB Ads | Quy ước tên camp/adset/ad: `[Angle]_[Tep]_[Format]_[v]` |
| `vn_brand_voice` | text | TN Content | Tone, từ nên/không nên, checklist chính sách FB |
| `vn_context_ts` | json | PM Trang sức | Số, tệp, vùng giá, đối thủ ngành TS |
| `vn_context_nh` | json | PM Nước hoa | Số, tệp, vùng giá, đối thủ ngành NH |
| `vn_report_sources` | json | PM/TP KD | Danh sách nguồn số (export Ads, Shopee, TT Shop, Lark Base, chat) |
| `vn_base_targets` | json | PM/TP KD | Base target đang dùng + ngày rebase (để in rõ base) |
| `vn_season_calendar` | json | MKT/CĐS | Dịp lễ & peak VN + kết luận làm/không làm |
| `vn_bst_milestones` | json | MKT/CĐS | Mốc BST tuyệt đối + luật D-x |
| `vn_research_sources` | json | (việc trống) | Index file nghiên cứu đối thủ đã có |
| `vn_kb_files` | json | HR/People Ops | Đường dẫn file tri thức tổ chức |

---

## 6. LỘ TRÌNH BUILD

- **Phase 0 (tuần này, 2–3h):** gateway nạp persona VN; `vn_kb_index`/`vn_kb_read` chạy thật; stub 7 nhóm tool; chạy Telegram trước. **Nghiệm thu:** hỏi JTBD/ngành → trả lời có số + tên file.
- **Phase 1:** Ads-ops GĐ1 (`vn_jtbd_bank`, `vn_idea_scan`, `vn_ads_report`, `vn_ads_review`) + WBR (`vn_numbers_read`, `vn_report_draft`, `vn_report_charts`, `vn_report_publish`) + mùa vụ/mốc.
- **Phase 2:** Ads-ops GĐ2 (`vn_creative_brief`, `vn_edit_variants`, `vn_camp_build`) + giao việc RACI + nghiên cứu (SOP + report builder).
- **Phase 3:** Ads-ops GĐ3 (`vn_camp_ops` theo luật, `vn_product_match`, `vn_scale_kill_reco`) + biên bản họp + trực số hằng ngày + runner local (Kalodata/Ads Manager cần session).

**Gate sau mỗi phase:** đúng 1 người ngoài team CĐS dùng thật 1 tuần. Không ai dùng → dừng, sửa cái đang có.

---

## 7. CÂU HỎI CHỐT TRƯỚC KHI CODE (chặn/đẩy nhanh build)

1. Repo là chính codebase **Jenny** hay template rỗng? → quyết định tái dùng được bao nhiêu.
2. Số KD Online VN đã lên **data warehouse** chưa, hay còn Lark Base + export? → bỏ được bước đọc doc thủ công không.
3. MAI dùng **tài khoản Lark riêng** hay chung Jenny? → ảnh hưởng quyền đọc lịch/doc/task.
4. Supabase: 1 project riêng cho VN hay chung với prefix `vn_`?
5. Kết nối **Facebook/TikTok/Google Ads + Shopee + TikTok Shop**: API chính thức hay export CSV giai đoạn đầu? → quyết độ tự động B7/B8.
6. Ai giữ vai **People Ops** Khối KD Online? (điền dòng 9 bảng phân công)
7. Skill nền dùng chung (brand voice, format WBR, SOP nghiên cứu) đã đóng gói chưa? → nạp lại, tránh 2 bản recipe lệch nhau.

---

## 8. RỦI RO & CÁCH GIỮ AN TOÀN

- **Đừng tự động hoá B7/B10 quá sớm.** Bắt đầu "AI đề xuất — người duyệt"; chỉ mở "AI tự chạy" cho hành động nhỏ trong `vn_ads_rules` sau khi tin cậy. Camp ops sai = đốt tiền thật.
- **Không gộp số 3 ngành.** TS/NH đang "học thị trường"; ép chung KPI với Túi sẽ ra kết luận sai.
- **Không bịa nguồn.** Thà nói "chưa có" — mất niềm tin 1 lần là team bỏ agent.
- **Quyền theo RACI là bắt buộc**, không phải tuỳ chọn — LNĐG/P&L và lương là dữ liệu nhạy cảm.
