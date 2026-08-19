# Sổ quyết định — thị trường Thái Lan

> Mỗi dòng: **ngày** · quyết định · **ai chốt** · nguồn. Chỉ ghi việc ĐÃ chốt, không ghi đề xuất.

## Tháng 8/2026

- **19/08** — **MATE MADE Thái Lan ĐÓNG**. Phạm vi Ploy còn lại: **HAPAS Thailand**. Câu hỏi về MATE MADE Việt Nam là ngoài phạm vi (số do Jenny giữ). **Vinh (CM)** thông báo. Nhân sự squad MM TH — vai trò mới chờ Vinh xác nhận.

- **19/08** — BST **Tote launching 23/09/2026** là nguồn chuẩn (bản 07/09 là cũ). **Vinh (CM)** chốt trong nhóm Lark Sawatdee HAPAS.
- **18/08** — Quý 4 **cắt còn 3 BST** (mỗi tháng 1 bộ, launching trước ngày sale đôi), plan ban đầu 5 bộ. Nguồn: BC KQKD Weekly 18/8.
- **18/08** — **BST T11 KHÔNG launching BST**, chỉ làm campaign bổ sung traffic (lễ tốt nghiệp, bán SP win Camel/Roam). Nguồn: Weekly 18/8.
- **16/08** — **Travel bag dời launching sang 05/09** để dồn cho ngày sale 09/09 (lý do: hàng KOC chậm vì kho vào dịp sale). Nguồn: CM Weekly kỳ 16.8.
- **16/08** — **Build ROAM thành HERO** của BST Tote (bán test 27 đơn, 68% là ROAM; tắt ads vẫn thêm 11 đơn). Nguồn: CM Weekly 16.8.
- **16/08** — **Tạm dừng Lemon8**, tập trung TikTok + IG. Nguồn: CM Weekly 16.8.
- **16/08** — Tăng **target T9 từ 12 lên 14 tỷ** (thống nhất với team KD). Nguồn: CM Weekly 16.8.
- **11/08** — **Bỏ** mã Balo Solis và túi ô trám khỏi danh mục test. Nguồn: sheet Tiến độ Test (Weekly 11/8).
- **07/08** — Theo feedback CEO: **bỏ BST sinh nhật** · đào sâu **Tote Noel → tháng 11** · "boom thẳng vào T12" · giảm T10–T11, tăng T12; mục tiêu Noel 20–30 tỷ. Nguồn: CM Weekly kỳ 07.8.
- **05/08** — **Base target T8 = 13 triệu THB DT / 2,4 triệu THB LNĐG** (thay 11 triệu THB dùng ngày 4/8). Nguồn: BC KQKD Daily.

## Tháng 7/2026

- **19/07** — Kho Flash áp **bọc chống sốc 3 lớp theo tiêu chuẩn VN**; combo Mother's Day + Songkran **đóng tại bàn** (phụ phí 2–3 THB/đơn). Nguồn: nhóm THAILAND - VẬN HÀNH CUNG ỨNG.
- **19/07** — Dùng nhóm **THAILAND - VẬN HÀNH CUNG ỨNG** để báo nhanh sự cố kho/tồn kho, không đợi họp 1-1. **Vinh (CM)** chốt.
- **22/07** — **Rebase target T7**: từ 9,3 triệu THB DT / 2,2 LNĐG xuống 8,0 / 1,5 triệu THB ("Tuyên bố sự cố" trong BC Daily). Lưu ý: BC Weekly KHÔNG rebase theo, nên 2 báo cáo lệch nhau tới 27/7.

## 19/08/2026 — Ploy tự tra BigQuery (không chờ A2A grant)

**Quyết định (Vinh):** cấp service account riêng `agent-data@surya-495408` cho Ploy đọc
BigQuery, thay vì chờ admin cấp A2A grant sang Jenny.

**Vì sao:** đường A2A đứng bánh (issue #34 chưa xử; AG-DATA-SUPPORT không chạy). Có khoá
riêng thì Ploy tự trả lời số doanh số ngay, không phụ thuộc agent khác còn sống hay không.

**Đã dựng:** `bq.py` (REST + JWT ký bằng openssl, không cần cài thư viện), khoá đặt ở
`env/bq-service-account.json` (git bỏ qua), câu SQL rà soát trước trong `configs/th_bq.json`.
Ploy KHÔNG tự viết SQL từ câu chat.

**Số đối chiếu đầu tiên (MTD 01→19/08, brand HPTH):** GMV 7,29 tỷ VND · DT thuần 6,75 tỷ ·
4.700 đơn · cùng kỳ T7 3,71 tỷ → +96%. Kênh: TikTok Shop 4,78 tỷ / Shopee 2,50 tỷ, các sàn
khác chưa phát sinh.

**Hai lỗ hổng của DB (đã ghi vào config):**
1. LNĐG không tính được — `ads_cost_branding` và `operation_cost` của HPTH NULL 100%.
2. Target Thái Lan không có trong `10_lsr.fact_target_detail` (chỉ MMVN, HPVN) → target vẫn
   lấy từ `th_base_targets` (13M THB DT / 2,4M LNĐG, base 05/08).

**Đang chờ Vinh:** tỷ giá THB→VND để Ploy so số DB (VND) với target (THB). Chưa có thì Ploy
trả lời bằng VND và nói rõ là chưa quy đổi — không tự đoán tỷ giá.
