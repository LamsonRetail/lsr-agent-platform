# Skill: th-internal-knowledge — Tri thức nội bộ thị trường Thái Lan

> Chủ sở hữu: **Vinh (CM)** — chỉ Vinh sửa file này.
> Phase 0 · F1. Nạp vào system prompt khi answer() chuyển sang Claude Agent SDK (Phase 2
> của AG-SQ-THAILAND); trước đó dùng làm luật cho `thailand_tools.th_kb_*`.

## Khi nào dùng

Người trong squad hỏi về: sản phẩm, JTBD, phân khúc giá, tổ chức/con người, chiến lược
thị trường Thái, nội dung ~27 file nghiên cứu.

## Trình tự bắt buộc (tra 2 bước — không đốt token)

1. `th_kb_index()` — xem mục lục: 3 master file + thư mục nghiên cứu.
2. Chọn đúng file/mục → `th_kb_read(file, section)` — chỉ đọc mục cần.
   **KHÔNG** nạp cả ~220KB master file vào context.

## Luật trả lời

- **Luôn trích tên file + mục.** Không nói chung chung "theo tài liệu".
- Không có trong kho → nói **"chưa có trong kho"**, không suy đoán, không lấy kiến thức
  ngoài thay thế.
- Số nào không tìm được nguồn → ghi `[CẦN BỔ SUNG SỐ LIỆU]`.
- **4 đính chính ở mục 0 của master file SP+JTBD phải ưu tiên nói ra** khi chạm chủ đề
  liên quan — ví dụ: tỷ trọng kênh LIVE 58–69% / video 16–24% (không dùng số bản cũ).
- Câu hỏi thuộc phần con người: dùng master file `04-Con-nguoi/…`; **không** trả lời
  lương/đánh giá cá nhân (theo `configs/role_permissions.json`).
- Người hỏi ngoài quyền xem (role_permissions) → từ chối thẳng, chỉ về hỏi Vinh.

## Nghiệm thu (definition of done)

Hương hỏi *"phân khúc giá HAPAS đang đứng là bao nhiêu, cạnh những ai"* → Ploy trả lời
**có số + tên file**, không cần hỏi Vinh.
