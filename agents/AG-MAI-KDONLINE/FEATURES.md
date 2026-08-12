# MAI — Trợ lý AI Khối Kinh doanh Online Việt Nam · Mô tả tính năng

**Cập nhật:** 2026-08-12 · **Trạng thái:** thiết kế xong, chưa build (Phase 0 bắt đầu)
**Kế hoạch triển khai:** `PLAN.md` · **Nền tảng tái dùng:** Jenny (LSR BOD Assistant)
**Tài liệu này viết cho cả team KD Online đọc** — để biết MAI làm được gì và không làm gì.
Tên "MAI" là đề xuất, đổi được bằng 1 dòng config `persona`.

---

## 1. MAI là gì

Trợ lý AI dùng chung cho toàn **Khối Kinh doanh Online (LAMSON RETAIL)** — 2 brand **HAPAS + MATE MADE**, 3 ngành **Túi xách · Trang sức · Nước hoa**, trải các kênh Facebook/TikTok/Google Ads, Affiliate/KOC, Content, Shopee, TikTok Shop, Livestream, Sale & CSKH.

MAI hoạt động trong **Lark** (và **Telegram**), trả lời khi được tag hoặc nhắn riêng, và tự chủ một số luồng việc: **chạy quy trình 10 bước quảng cáo (Ads-ops)**, dựng báo cáo tuần/tháng (WBR), trả lời câu hỏi về sản phẩm–JTBD–tổ chức, nhắc mốc BST và dịp lễ VN, giao việc theo RACI, ghi biên bản họp, và hỗ trợ nghiên cứu thị trường/đối thủ.

**MAI không phải chatbot.** Cách nghĩ đúng: MAI là **một nhân sự của Khối KD Online** — có bối cảnh riêng của thị trường VN, biết ai làm gì (RACI), nhớ những gì đã quyết, và làm việc end-to-end thay vì trả lời từng câu rời rạc.

### Ba nguyên tắc cốt lõi
1. **Skill = năng lực chung** (file `.md`), **chi tiết hay thay đổi = configs** trên Supabase → sửa hành vi **không cần deploy lại**. Đây là lý do team tự điều chỉnh MAI được về sau.
2. **AI làm phần THỰC THI — con người giữ phần WHY.** AI trả lời "LÀM GÌ / LÀM THẾ NÀO", con người trả lời "TẠI SAO / CÓ NÊN KHÔNG". (Xem 5 cổng WHY ở §3.1.)
3. **Trung thực tuyệt đối** — không có dữ liệu thì nói rõ, không bịa số, không bịa nguồn. Mọi số kèm **nguồn + thời điểm + base target** đang dùng; số ước tính phải ghi *(ước tính)*. Tiếng Việt, xưng "em" – gọi "anh/chị". Ngắn gọn, đi thẳng số.

### MAI khác Jenny ở đâu
Jenny phục vụ **BOD tập đoàn** (query kho số, báo cáo group, giao việc BOD). MAI phục vụ **một khối vận hành** — bối cảnh hẹp hơn nhưng sâu hơn: biết camp nào đang chạy tệp nào, ngành nào đang ở vùng giá nào, BST nào launching ngày nào, dịp lễ VN nào đáng làm.

---

## 2. Tương tác & kênh chat

**Lark (đường chính)** — MAI chạy bằng **tài khoản người dùng riêng** (OAuth polling, không phải bot):
- **Group:** chỉ trả lời khi được `@mention` hoặc gọi tên trigger.
- **Chat riêng:** người trong config `vn_p2p_partners` được whitelist tự động.
- **Thread:** tag MAI trong 1 thread thì trả lời đúng trong thread đó.
- Gửi tin "⏳ Em đang xử lý…" rồi sửa thành câu trả lời khi xong.

**Telegram** — dự phòng và để demo nhanh (ít quyền, chạy trước ở Phase 0).

**Ngữ cảnh người hỏi:** mỗi tin nhắn MAI tự đính kèm hồ sơ người gửi (vai trò theo RACI, ngành phụ trách, quyền xem số) → điều chỉnh câu trả lời và **chặn phần ngoài quyền**.

---

## 3. Bảy nhóm tính năng

Bảy nhóm này trải **Phase 0 → Phase 3** (chiều nay đến T9), không phải xong hết trong tuần này. Xem lộ trình ở §7.

### 3.1 · Ads-ops — Quy trình 10 bước quảng cáo ⭐ (trục chính) — *Phase 1→3*

Đây là DNA của Khối KD Online và là điểm khác biệt lớn nhất so với agent Thái. MAI gánh phần **THỰC THI** của cả 10 bước; con người giữ **5 cổng WHY**.

**5 cổng WHY con người luôn nắm:**
- **B1 — Chọn JTBD:** đánh vào nhu cầu nào.
- **B2 — Chọn sản phẩm:** đẩy SP nào theo mục tiêu KD (xả hàng / chủ lực / biên LN).
- **B4 — Duyệt concept:** nội dung nào xứng brand.
- **B7 — Phê duyệt ngân sách lớn:** scale tới đâu, rủi ro bao nhiêu.
- **B10 — Quyết nhân bản/bỏ:** chịu trách nhiệm P&L.

| Bước | AI TỰ ĐỘNG HOÁ (thực thi) | Con người giữ (WHY) | Tool |
|---|---|---|---|
| **1. Tìm JTBD** | Quét review/comment/tin nhắn/khảo sát + xu hướng search & social → gom cụm, xuất ≥5 JTBD chuẩn "Khi… tôi muốn… để…" kèm quy mô cầu ước tính | Chọn JTBD hợp chiến lược & danh mục; giữ tối đa ~5 cụm trọng tâm | `vn_jtbd_bank` |
| **2. Chọn SP** | Đọc catalog (tính năng, giá, tồn, lịch sử bán) → match & xếp hạng SP theo từng JTBD; cảnh báo hết hàng / biên thấp | Quyết SP nào đẩy theo mục tiêu KD & kế hoạch tồn kho | `vn_product_match` |
| **3. Tìm idea content** | Quét Ad Library / TikTok / nguồn TQ theo SP·JTBD → phân loại angle/hook/format, tóm tắt vì sao hiệu quả, đề xuất bản địa hoá | Chọn idea hợp brand, khả thi; sáng tạo lại, không sao chép lố | `vn_idea_scan` |
| **4. Sản xuất video/ảnh** | Sinh script + storyboard; tạo ảnh/video AI hoặc xuất brief cho ekip quay | Chốt concept cuối; quyết khi nào cần người thật quay | `vn_creative_brief` |
| **5. Cắt ghép/hậu kỳ** | Auto-cut theo script, phụ đề, lồng nhạc, xuất đa tỉ lệ (9:16/1:1/4:5), nhiều biến thể hook 3s | Duyệt bản đạt chuẩn cảm xúc/brand; chọn biến thể vào test | `vn_edit_variants` |
| **6. Lên camp test** | Tạo camp/adset theo naming convention & ngân sách test chuẩn; đề xuất targeting, nạp creative, gắn tracking, ghi giả thuyết + KPI | Duyệt giả thuyết test, tệp, mức ngân sách | `vn_camp_build` |
| **7. Vận hành camp** | Giám sát chỉ số theo ngưỡng 24/7; đề xuất (hoặc **tự chạy theo luật trong hạn mức**) tắt/bật, tăng/giảm, nhân bản; cảnh báo bất thường tức thì | Đặt "luật chơi" (ngưỡng, khẩu vị rủi ro, trần ngân sách); phê duyệt ngân sách lớn | `vn_camp_ops` |
| **8. Đo lường & báo cáo** | Kéo dữ liệu → báo cáo tự động (spend, CPM, CTR, CPC, CPA, ROAS, CIR); so target & kỳ trước; highlight top/bottom | Xác định chỉ số nào quan trọng với mục tiêu KD giai đoạn này | `vn_ads_report` |
| **9. Review & phân tích** | Đối chiếu creative × tệp × chỉ số → tìm pattern thắng/thua theo **FACT → WHY → SO WHAT → ACTION**; tách dữ kiện vs giả thuyết | Xác nhận nguyên nhân THẬT, đọc bối cảnh thị trường AI không biết | `vn_ads_review` |
| **10. Nhân bản/bỏ** | Chấm điểm từng camp-creative theo hiệu quả & tiềm năng scale; khuyến nghị nhân bản/giữ/bỏ + mức tự tin; mô phỏng tác động nếu scale | **RA QUYẾT ĐỊNH CUỐI** — chịu trách nhiệm P&L | `vn_scale_kill_reco` |

**Ba mức tự động hoá (triển khai an toàn):**
- **AI chạy — người giám sát:** B3 (idea) · B5 (cắt ghép) · B8 (báo cáo).
- **AI đề xuất — người duyệt:** B1 · B2 · B4 · B6 · B7 · B9.
- **Người quyết — AI hỗ trợ bằng chứng:** B10 và mọi cổng WHY.

> Nguyên tắc an toàn: bắt đầu ở chế độ **"AI đề xuất — người duyệt"**, chỉ chuyển sang **"AI tự chạy"** cho hành động nhỏ, trong hạn mức, sau khi đã tin cậy kết quả. Toàn bộ ngưỡng & hạn mức nằm ở config `vn_ads_rules` — sửa được không cần deploy.

### 3.2 · Tri thức nội bộ VN — *Phase 0*

Trả lời câu hỏi về **sản phẩm, JTBD, tổ chức, chiến lược 3 ngành** — dựa trên chính các file đã có, không suy đoán.

- **Kho tri thức:** JTBD & danh mục SP 3 ngành (Túi/TS/NH) · Con người–Tổ chức (RACI, khung năng lực Junior/Senior, JD) · Chiến lược & kế hoạch quý · các phân tích đối thủ đã có (edoris, bostanten, mossdoom, ELLY…) · bộ nhớ `.md`.
- `vn_kb_index` → mục lục · `vn_kb_read` → đọc 1 mục. **Tra 2 bước** (index trước, đọc sau) để không đốt token.
- `vn_review_report` ⭐ — soi báo cáo tuần của manager theo **6 trục**: reach vs revenue · nhìn sau vs nhìn trước · quyết định lớn bị ghi như ghi chú · "Done" giả · ngày tháng lệch giữa các tài liệu · mảng đang thắng lại viết ít nhất.
- **Brand voice** (HAPAS & MATE MADE) nạp sẵn để chuẩn hoá copy — dùng chung với B4/B5.

Trả lời luôn kèm **tên file + mục**. Không có trong kho thì nói *"chưa có"*, không đoán.

### 3.3 · Báo cáo tuần & báo cáo tháng (WBR) — *Phase 1*

Gom nguồn cố định (export Ads Manager 3 kênh + Shopee/TikTok Shop + Lark Base + chat group) → dựng draft theo template, **chờ duyệt** rồi phát hành.

- `vn_numbers_read` — đọc DT / LNĐG / %MTD từ nguồn số.
- `vn_report_draft` — dựng `.md` theo template WBR, khung **FACT → WHY → SO WHAT → ACTION**, ưu tiên theo tác động kinh doanh (doanh thu, hiệu quả, rủi ro). Báo cáo cho lãnh đạo ≤1 trang, 3–5 điểm quan trọng nhất.
- `vn_report_charts` — chart chuẩn: doanh thu luỹ kế vs target · so chỉ số MKT (CTR/CPA/ROAS/CIR) kỳ này vs kỳ trước · phễu DT theo kênh/ngành.
- `vn_report_publish` — tạo Lark Doc + gửi chat **sau khi được duyệt**.

**Hai cái bẫy MAI được dạy sẵn** (điều chỉnh trong `vn_base_targets`):
- Nếu có nhiều base target chạy song song → MAI luôn **in rõ đang dùng base nào**.
- **% MTD** so với target **lũy kế pro-rata theo ngày**, không phải actual ÷ target cả tháng.

*Deck tháng theo format đã chốt của Khối; toàn bộ số bằng VND; ảnh sản phẩm thật bắt buộc — MAI dựng khung, người chèn ảnh.*

### 3.4 · Lịch mùa vụ VN & nhắc mốc BST — *Phase 1*

`vn_season_calendar` — dịp lễ & peak VN **kèm kết luận làm / không làm**, không phải danh sách ngày suông. Ví dụ khung (chi tiết trong config):

| Dịp | Loại | MAI sẽ nhắc |
|---|---|---|
| Tết Nguyên đán | Peak lớn nhất | Deadline sản xuất trước nghỉ Tết; vùng "chết" cận Tết; combo quà biếu |
| Back-to-school (T7–T9) | LÀM | Tệp **người thân tặng tân sinh viên** (balo/tote) — nhắm người mua là phụ huynh/anh chị |
| Sàn double-day 9/9·10/10·11/11·12/12 | Peak sàn | Đăng ký flash deal/voucher; ngày khoá đăng ký campaign sàn |
| 20/10 · 8/3 · Valentine | Dịp quà nữ | Trục tặng quà — mạnh cho TS & NH |
| Black Friday · Noel/Năm mới | Peak cuối năm | Nhịp dồn cuối năm; xả tồn trước load hàng mới |

`vn_milestone_check` — đếm ngược tới mốc tuyệt đối (ngày cụ thể), cảnh báo khi trượt (chốt mẫu · xuống PO · lên kệ · chốt KOC).
`vn_milestone_conflict` ⭐ — phát hiện một mốc BST có nhiều phiên bản ngày giữa các nguồn, liệt kê thành bảng, bắt chốt 1 nguồn chuẩn.

### 3.5 · Giao việc & đôn đốc theo RACI — *Phase 2*

Luồng giao việc chuẩn hoá — bắt buộc đủ **4 yếu tố**: *việc gì · bối cảnh · đầu ra cụ thể để chấm được · PIC*. Thiếu 1 yếu tố thì MAI từ chối tạo.

- `vn_assignment_create` — tạo record + Lark task + tự nhắn PIC đầy đủ thông tin.
- `vn_assignment_list / _update / _remind`.
- `vn_assignment_escalate` — luật 24h: PIC im 24h → escalate theo cây RACI (CV → TN → TP/PM).

**Ai giao được việc** bám theo cột **A (Accountable)** trong RACI: TP KD Online, TP Digital Perf., PM ngành TS/NH, TP TMĐT, và các Trưởng nhóm trong phạm vi nhóm mình. Người khác gọi → MAI nói rõ ai được giao.

### 3.6 · Nghiên cứu thị trường & đối thủ — *Phase 2*

- `vn_research_index` / `vn_research_search` — tra các file nghiên cứu đã có. **Luật: luôn tra trước khi làm bài mới** — để không làm lại việc đã làm.
- `vn_research_sop` — SOP chuẩn: Kalodata · Ad Library · POP · Taobao/nguồn TQ · TikTok Ads Audience Insights.
- `vn_research_report_build` — dựng HTML báo cáo theo format: card ảnh thật → brand + năm → trường ngắn → lớp "→ HAPAS làm được gì" → nguồn + cấp A/B/C.

**Luật nghiên cứu MAI phải giữ:** Size/Màu/Kiểu dáng/Kênh tính theo **SỐ MẪU** (không theo số lượng bán); thương hiệu tính theo số lượng bán · TikTok Audience Insights: **Affinity = Selected ÷ All** (đọc thô cột Selected là sai) · Comment: chỉ đọc comment ≥3 like · xếp KOC bằng median views ÷ followers và giá/1.000 view, không bằng follower · cấp **A/B/C** cho mọi dữ kiện · ghi **NĂM** · "KHÔNG TÌM ĐƯỢC" thay vì suy đoán.

> **Giới hạn thật, nói trước:** Kalodata / TikTok Ads / POP đều cần session đã đăng nhập; chạy trên server sẽ đá người thật ra. Phase 2 MAI làm phần **SOP + dựng báo cáo**; phần lấy data vẫn chạy trên máy cá nhân. Phase 3 mới có **runner local** nhận việc từ MAI.

### 3.7 · Biên bản họp + action item — *Phase 3 (tái dùng Jenny)*

Tái dùng pipeline Jenny: theo dõi lịch → nhận bản ghi → gỡ băng → draft notes `.md` → người tạo họp duyệt → phát hành.
Lớp riêng của VN: `vn_meeting_to_assignment` — biến action item thành assignment 4 yếu tố theo đúng cây RACI. Biên bản luôn viết tiếng Việt.

---

## 4. Bảng tra công cụ

| Nhóm | Tools |
|---|---|
| **Ads-ops** | `vn_jtbd_bank`, `vn_product_match`, `vn_idea_scan`, `vn_creative_brief`, `vn_edit_variants`, `vn_camp_build`, `vn_camp_ops`, `vn_ads_report`, `vn_ads_review`, `vn_scale_kill_reco` |
| **Tri thức** | `vn_kb_index`, `vn_kb_read`, `vn_review_report` |
| **Báo cáo** | `vn_numbers_read`, `vn_report_draft`, `vn_report_charts`, `vn_report_publish` |
| **Mùa vụ & mốc** | `vn_season_calendar`, `vn_milestone_list`, `vn_milestone_check`, `vn_milestone_conflict` |
| **Giao việc** | `vn_assignment_create`, `vn_assignment_list`, `vn_assignment_update`, `vn_assignment_remind`, `vn_assignment_escalate` |
| **Nghiên cứu** | `vn_research_index`, `vn_research_search`, `vn_research_sop`, `vn_research_report_build` |
| **Họp** | `meeting_list_pending`, `meeting_save_draft`, `meeting_finalize`, `vn_meeting_to_assignment` |
| **Lark (tái dùng Jenny)** | `read_lark_document`, `send_lark_message`, `calendar_*`, `task_*`, `org_lookup`, `memory_*` |
| **Web** | `WebSearch`, `WebFetch` |

**Bị cấm trên VPS:** `Bash`, `Write`, `Edit` — MAI không sửa file hay chạy shell trên server.

---

## 5. Phân quyền — vì đây là agent dùng chung

Bám theo RACI Khối KD Online. Ai hỏi ngoài quyền → MAI nói rõ *"phần này em không được chia sẻ"*, không lách, không trả lời một nửa. **Số lương & đánh giá cá nhân không lưu vào bộ nhớ.**

| Vai trò | Xem được | Làm được |
|---|---|---|
| **TP KD Online** (Head) | Tất cả, cả P&L 2 brand | Tất cả, kể cả giao việc toàn khối |
| **TP Digital Perf.** | Toàn bộ số Digital (Ads/AFF/Content) | Giao việc trong khối Digital; duyệt ngân sách |
| **PM Ngành TS / NH** | Số ngành mình (toàn kênh) | Quyết đẩy SP, giao việc trong ngành |
| **TN Ads (FB/TT/Google)** | Số kênh mình, 3 ngành | Đặt luật camp, duyệt scale trong hạn mức, giao việc CV |
| **CV Ads theo ngành** | Số camp/ngành mình | Vận hành camp, cập nhật assignment |
| **TN Affiliate** | DT AFF, KOC pool | Booking KOC, giao việc CV AFF |
| **TN/CV Content** | Chỉ số creative | Sản xuất, cập nhật assignment |
| **TP TMĐT / TN VH / Host** | Số gian hàng & phiên live | Vận hành sàn/live, cập nhật assignment |
| **Sale Online / TNKH** | Feedback, chỉ số chốt đơn | Cập nhật assignment, báo feedback |

*LNĐG / P&L chỉ mở cho cấp quản lý (TP, PM). CV chỉ xem DT & traffic phần mình.*

---

## 6. MAI KHÔNG làm gì

- **Không tự quyết** — không tự đổi target, đổi giá, đổi ngân sách lớn, đổi ngày launching. MAI chỉ ra số, đề xuất và cảnh báo.
- **Không tự scale/kill vượt hạn mức** — chỉ tự chạy trong `vn_ads_rules` đã đặt; ngoài đó phải người duyệt (cổng WHY B7, B10).
- **Không lấy data từ Kalodata / TikTok Ads / POP trên server** (cần session đăng nhập) — Phase 2 chỉ hỗ trợ SOP + dựng báo cáo.
- **Không trả lời khi không có nguồn.** Sẽ nói *"chưa có trong kho"* chứ không đoán.
- **Không thay người review.** Draft báo cáo & creative luôn chờ người duyệt mới phát hành.
- **Không xử lý số lương / đánh giá cá nhân.**
- **Chưa có** (roadmap sau): trực số hằng ngày tự động · Zalo · dashboard riêng cho KD Online.

---

## 7. Lộ trình

| Phase | Khi nào | Có gì | Nghiệm thu |
|---|---|---|---|
| **0** | Tuần này | Agent chạy Lark/Telegram + tri thức nội bộ 3 ngành (§3.2) | Hỏi 1 câu về JTBD/ngành → trả lời có số + tên file |
| **1** | Tuần kế | Ads-ops GĐ1 (B1 JTBD · B3 idea · B8 báo cáo · B9 phân tích) + WBR + lịch mùa vụ & mốc BST | Có draft weekly; MAI đề xuất JTBD + idea + đọc số Ads |
| **2** | Nửa cuối T8 | Ads-ops GĐ2 (B4 sản xuất · B5 hậu kỳ · B6 lên camp) + giao việc RACI + nghiên cứu | Từ idea → brief/nháp + dựng camp test; giao việc qua chat |
| **3** | T9/2026 | Ads-ops GĐ3 (B7 vận hành theo luật · B2 · B10) + biên bản họp + trực số hằng ngày + runner local | Camp tự vận hành trong hạn mức; họp xong có biên bản; sáng có số |

**Gate sau mỗi phase:** có đúng **1 người ngoài team CĐS** dùng thật 1 tuần. Không ai dùng thì **dừng, sửa cái đang có** thay vì build thêm.
