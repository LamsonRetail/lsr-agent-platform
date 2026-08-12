# Use case — MAI (AG-MAI-KDONLINE)

Nguồn gốc: `FEATURES.md` (mô tả tính năng cho cả team đọc) · `PLAN.md` (kế hoạch build).
Chủ sở hữu nghiệp vụ: Head of Online Business · Team: KD Online VN.

## Bài toán

Bốn nút thắt của Khối KD Online, mỗi cái có bằng chứng cụ thể:

| Nút thắt | Bằng chứng | MAI làm gì |
|---|---|---|
| Chuyên viên đốt thời gian vào phần lặp lại | Quy trình Ads 10 bước: thu thập idea, sản xuất, thao tác camp, gom số — làm tay | Gánh phần THỰC THI của 10 bước; người giữ 5 cổng WHY |
| Tri thức nằm trong đầu quản lý | JTBD, danh mục 3 ngành, RACI, phân tích đối thủ, khung năng lực — team không đọc nên hỏi lại | Hỏi–đáp trên chính các file đó, có trích nguồn |
| Báo cáo tuần gom tay, thiếu cấu trúc | Có template WBR nhưng phải gom số từ 3 kênh Ads + 2 sàn + Lark Base | Tự gom nguồn → dựng WBR theo template, chờ duyệt |
| 2 ngành mới (TS/NH) thiếu bối cảnh riêng | RACI đã tách PM ngành TS & NH; số ngành mới dễ bị gộp nhầm với Túi | Tách bối cảnh & số theo ngành, không gộp |

## Người dùng

Toàn bộ Khối KD Online (2 brand · 3 ngành), hỏi theo **vai trò RACI của mình**:
TP KD Online · TP Digital Performance · PM ngành TS/NH · TN Ads (FB/TikTok/Google) ·
CV Ads theo ngành · TN Affiliate · TN/CV Content · TP TMĐT / TN Vận hành / Host ·
Sale Online / TNKH.

**Kênh:** Telegram (Phase 0 — nhanh, ít quyền) → Lark nhóm KD Online (đường chính, gọi
khi được `@mention`) → chat riêng cho người trong whitelist `vn_p2p_partners`.

## Luồng chính (happy path)

1. Người dùng tag MAI trong nhóm: *"Ngành Trang sức đang đánh JTBD nào?"*
2. MAI đọc hồ sơ người hỏi (vai trò RACI → quyền xem số) từ `role_permissions` + `vn_squads`.
3. `vn_kb_index` → chọn đúng mục trong kho tri thức; `vn_kb_read` → đọc đúng mục đó.
4. Trả lời **kèm tên file + mục + thời điểm**; số nào ước tính thì ghi rõ *(ước tính)*.
5. Ngoài quyền của người hỏi → nói rõ *"phần này em không được chia sẻ"*.

## Ngoài phạm vi (không làm)

- Không tự quyết: không đổi target, giá, ngân sách lớn, ngày launching.
- Không tự scale/kill camp vượt hạn mức trong `vn_ads_rules`.
- Không lấy data từ Kalodata / TikTok Ads / POP trên server (cần session đăng nhập).
- Không trả lời khi không có nguồn — nói "chưa có trong kho".
- Không thay người review: draft báo cáo & creative luôn chờ duyệt.
- Không xử lý số lương / đánh giá cá nhân.
- Chưa làm (roadmap sau): trực số hằng ngày tự động · Zalo · dashboard riêng cho KD Online.

## Dữ liệu cần truy cập

| Nguồn | Trạng thái quyền |
|---|---|
| Kho tri thức nội bộ (`kb/*.md`: JTBD 3 ngành, RACI, chiến lược quý, phân tích đối thủ) | Team tự nạp file — **chưa nạp** |
| Export Ads Manager (FB / TikTok / Google) | ⬜ chưa chốt API hay CSV (PLAN §7 câu 5) |
| Shopee · TikTok Shop | ⬜ chưa chốt |
| Lark Base (số DT/LNĐG) | ⬜ chưa chốt đã lên data warehouse chưa (PLAN §7 câu 2) |
| Lark chat/doc/task | qua connector platform, cần admin cấp quyền |

## Rủi ro & giới hạn

- **Đừng tự động hoá B7/B10 quá sớm.** Bắt đầu "AI đề xuất — người duyệt"; chỉ mở "AI tự
  chạy" cho hành động nhỏ trong hạn mức sau khi đã tin cậy. Camp ops sai = đốt tiền thật.
- **Không gộp số 3 ngành** — ép chung KPI với Túi sẽ ra kết luận sai.
- **Không bịa nguồn.** Thà nói "chưa có" — mất niềm tin 1 lần là team bỏ agent.
- **Quyền theo RACI là bắt buộc** — LNĐG/P&L và lương là dữ liệu nhạy cảm.

## Gate nghiệm thu theo phase

| Phase | Nghiệm thu |
|---|---|
| **0** (tuần này) | Hỏi 1 câu về JTBD/ngành → trả lời có số + tên file |
| **1** | Có draft weekly; MAI đề xuất JTBD + idea + đọc số Ads |
| **2** | Từ idea → brief/nháp + dựng camp test; giao việc qua chat |
| **3** | Camp tự vận hành trong hạn mức; họp xong có biên bản; sáng có số |

**Sau mỗi phase:** đúng **1 người ngoài team CĐS** dùng thật 1 tuần. Không ai dùng thì
**dừng, sửa cái đang có** thay vì build thêm.
