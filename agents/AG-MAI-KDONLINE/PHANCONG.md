# PHÂN CÔNG — Team KD Online VN build agent MAI

Branch team: `feature/vn-agent-mai` · Agent: `AG-MAI-KDONLINE` · Cập nhật: 12/08/2026

> **Nguyên tắc số 1:** mỗi người 1 file skill + 1 (nhóm) config key → không ai đụng file của
> ai → không bao giờ conflict.

---

## 1. Ba loại "chỗ để sửa"

| Loại | Là gì | Sửa xong phải deploy? |
|---|---|---|
| **Skill** `.md` | Năng lực chung — "khi được hỏi X thì làm theo trình tự Y" | ❌ Không. Nạp lại ở phiên mới. |
| **Config** `.json` | Chi tiết hay thay đổi — target, luật scale/kill, lịch lễ, naming, danh sách người | ❌ Không deploy, nhưng **giai đoạn này vẫn cần commit + PR** (xem `configs/README.md`) |
| **Tool** `.py` | Việc phải chạy code — đọc số Ads, dựng chart, tạo task, quét idea | ✅ Có |

Chiều nay mỗi người làm **1 skill + 1 config**. **Không ai phải viết Python.**

**Bài học cần rút ra:** muốn MAI đổi hành vi, 90% trường hợp chỉ cần sửa 1 file `.md`
hoặc 1 dòng JSON — không cần lập trình viên.

---

## 2. Bảng phân công

| # | Vai trò (điền tên) | Tính năng | File skill — chỉ mình sửa | Config — chỉ mình sửa | Xong là chứng minh bằng |
|---|---|---|---|---|---|
| 1 | **TP Digital Perf.** (điều phối) | Persona + phân quyền + tri thức nền | `skills/vn-internal-knowledge.md` | `persona` · `vn_context` · `role_permissions` · `vn_squads` · `vn_p2p_partners` | Hỏi MAI 1 câu về JTBD → trả lời có số + tên file |
| 2 | **TN Facebook Ads** | ⭐ Ads-ops 10 bước + 5 cổng WHY | `skills/vn-ads-workflow.md` | `vn_ads_rules` · `vn_naming_convention` | Đưa 1 creative đã duyệt → MAI dựng khung camp test đúng naming + KPI |
| 3 | **TN Content Perf.** | Creative & nội dung + brand voice | `skills/vn-creative-content.md` | `vn_brand_voice` | Dán 1 copy thô → MAI trả bản đúng giọng brand + ≥3 angle |
| 4 | **PM Ngành Trang sức** | Bối cảnh ngành TS | `skills/vn-nganh-trangsuc.md` | `vn_context_ts` | MAI trả số ngành TS không gộp với Túi |
| 5 | **PM Ngành Nước hoa** | Bối cảnh ngành NH | `skills/vn-nganh-nuochoa.md` | `vn_context_nh` | MAI trả số ngành NH riêng; biết vùng giá & đối thủ |
| 6 | **PM / TP KD Online** | Báo cáo tuần/tháng (WBR) | `skills/vn-weekly-report.md` | `vn_report_sources` · `vn_base_targets` | MAI đọc đúng DT/LNĐG và **nói rõ đang dùng base nào** |
| 7 | **MKT / CĐS** | Lịch mùa vụ VN & mốc BST | `skills/vn-season-calendar.md` · `skills/vn-bst-milestones.md` | `vn_season_calendar` · `vn_bst_milestones` | Hỏi "T10 làm gì" → nhắc 10/10 · 20/10 + countdown BST |
| 8 | **TN Affiliate / TP TMĐT** | Giao việc & đôn đốc theo RACI | `skills/vn-assignments.md` | (dùng `vn_squads` của #1) | Giao 1 việc test → MAI nhắn đủ 4 yếu tố cho PIC |
| 9 | **HR / People Ops** — ⚠ **cần xác nhận PIC** | Tri thức con người, tổ chức, tuyển dụng | `skills/vn-people-ops.md` | `vn_kb_files` | Hỏi "ai là PM ngành TS, báo cáo lên ai" → trả đúng RACI |
| 10 | **Data/Tech** (hỗ trợ) | MCP server + seed config | `vn/vietnam_tools.py` | — | Agent nạp được tool list đầy đủ (dù còn stub) — ✅ **đã xong** |

> ⚠ **Dòng 9 phải chốt trước khi phát bảng này:** ai đang giữ vai People Ops cho Khối KD
> Online (đang tuyển CV Ads/AFF/Content ngành mới)? Hỏi rồi mới điền tên.

**Việc còn trống** (ai rảnh thì nhận):

| Việc | Vì sao cần |
|---|---|
| `skills/vn-research.md` + `vn_research_sources` — index nghiên cứu đối thủ đã có | Đang làm lại nghiên cứu vì không tra được bài cũ |
| `vn_milestone_conflict` — soi 1 mốc BST có nhiều phiên bản ngày | Tránh lệch ngày launching giữa các nguồn |
| `vn_review_report` — soi báo cáo tuần theo 6 trục | Chuẩn hoá chất lượng WBR |
| Skill trả lời cho ngành mới bằng tệp khách mới | TS & NH cần tệp khác Túi |

---

## 3. Quy trình git — 5 bước

```bash
# 1. Lấy repo (đã xong nếu bạn đang đọc file này trong repo)
git clone git@github.com:LamsonRetail/lsr-agent-platform.git && cd lsr-agent-platform

# 2. Branch team — CHỈ 1 NGƯỜI LÀM, rồi push
git checkout -b feature/vn-agent-mai
git push -u origin feature/vn-agent-mai

# 3. Mỗi người tạo branch con TỪ branch team
git checkout feature/vn-agent-mai && git pull
git checkout -b vn/<ten>-<tinh-nang>          # vd: vn/fbads-ads-workflow

# 4. Làm việc → commit → push
git add agents/AG-MAI-KDONLINE/skills/vn-ads-workflow.md \
        agents/AG-MAI-KDONLINE/configs/vn_ads_rules.json
git commit -m "vn: skill Ads-ops 10 bước — 5 cổng WHY + naming convention"
git push -u origin vn/<ten>-<tinh-nang>

# 5. Mở PR vào feature/vn-agent-mai (KHÔNG vào main)
```

**Luật để không vỡ:**

- Không ai push thẳng vào `feature/vn-agent-mai` (trừ bước 2).
- **Chỉ sửa file trong `agents/AG-MAI-KDONLINE/`.** CI `scope-guard` **chặn PR** đụng vào
  `infra/`, `src/`, `scripts/`, `tests/`, `docs/`, `.github/`, `apps/platform-web/` nếu bạn
  không phải maintainer.
- Không sửa file của người khác. Cần đổi → nhắn người đó.
- Trước khi làm: `git checkout feature/vn-agent-mai && git pull`.
- Commit message bắt đầu bằng `vn:` để lọc được.

---

## 4. Thêm tính năng cho MAI VỀ SAU

| Trường hợp | Công sức | Làm gì |
|---|---|---|
| **1 — Đổi một chi tiết** (90% trường hợp)<br>*VD: target T10 đổi 12 tỷ → 13 tỷ* | ~2 phút, không cần code | Sửa `configs/vn_context.json` → commit → PR |
| **2 — Đổi cách MAI làm việc**<br>*VD: báo cáo tuần luôn có thêm mục "3 việc tuần tới"* | ~15 phút, không cần code | Sửa `skills/vn-weekly-report.md` → commit → PR. MAI nạp ở phiên mới |
| **3 — Cần MAI làm việc mới hẳn**<br>*VD: tự đọc bảng giá đối thủ trên Shopee* | Thêm tool, cần Claude Code | Mở Claude Code trong repo: *"Đọc `agents/AG-MAI-KDONLINE/PLAN.md`. Thêm tool `vn_competitor_price` vào `vn/vietnam_tools.py`… **Lập kế hoạch trước, đừng code ngay.**"* |

**Ba luật khi làm việc với Claude Code:**

1. **Luôn bắt lập plan trước khi code.** Đọc plan là việc của người, không phải của Claude.
2. Dùng model mạnh cho lập kế hoạch & phân tích, model thấp hơn cho code cơ bản — tiết kiệm token.
3. Gặp lỗi thì **paste nguyên văn lỗi**, đừng diễn giải lại. Context dài quá thì `/compact`.

---

## 5. Checklist chiều nay

- [x] Pull repo, tạo branch team `feature/vn-agent-mai`
- [x] Data/Tech: scaffold `vn/vietnam_tools.py` (32 tool: 3 thật + 29 stub) + seed 16 config
- [x] Khung 11 skill file — mỗi file ghi rõ owner + TODO
- [ ] Mỗi người tạo branch con + điền skill & config của mình
- [ ] #1 TP Digital: chốt `persona` + `role_permissions` theo RACI
- [ ] Nạp file tri thức vào `kb/` (xem `kb/_README.md`) — **thiếu cái này thì không demo được**
- [ ] Đăng ký agent + chạy thử trên **Telegram** trước (nhanh, ít quyền), Lark làm sau
- [ ] Demo 1 câu hỏi thật về JTBD/ngành → MAI trả lời có số + tên file
- [ ] Mỗi người mở 1 PR vào branch team

> **Không** đặt mục tiêu xong hết tính năng chiều nay. Mục tiêu là: **agent chạy thật +
> mỗi người biết chỗ để sửa phần của mình.**

---

## 6. Câu hỏi cần chốt với anh (trước khi build tiếp)

| # | Câu hỏi | Trạng thái |
|---|---|---|
| 1 | Repo công ty là codebase Jenny hay template rỗng? | ✅ **Đã rõ** — repo là **LSR Agent Platform** (registry + telemetry + RBAC + runtime), **không phải Jenny**. Xem mục "Khác biệt so với PLAN" trong `README.md` |
| 2 | Số KD Online VN đã lên data warehouse chưa, hay còn Lark Base + export? | ⬜ chưa chốt |
| 3 | MAI dùng tài khoản Lark riêng hay chung? | ⬜ chưa chốt — hiện khai `connect_mode: bot`, dùng bot chung của platform |
| 4 | Supabase: project riêng hay chung với prefix `vn_`? | ✅ **Không dùng Supabase** — platform dùng Postgres, mỗi agent 1 schema riêng |
| 5 | Facebook/TikTok/Google Ads + Shopee + TikTok Shop: API chính thức hay export CSV? | ⬜ chưa chốt — chặn Phase 1 (B8) |
| 6 | Ai giữ vai People Ops Khối KD Online? | ⬜ chưa chốt — chặn dòng 9 |
| 7 | Skill nền dùng chung (brand voice, format WBR, SOP nghiên cứu) đã đóng gói chưa? | ⬜ chưa chốt |
