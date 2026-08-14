# PLAN — HR Agent (AG-HR)

> Trạng thái: DRAFT chờ owner confirm. Quy tắc: plan → confirm → prototype → thực thi.
> Thay đổi plan/tính năng lớn phải cập nhật file này trước khi commit.

## 1. Nguyên tắc thiết kế

1. **Số liệu = code, chữ nghĩa = model.** KPI, thu nhập, chấm công, headcount truy vấn
   trực tiếp Lark Base/Sheet bằng code (deterministic) — model chỉ diễn giải kết quả,
   không bao giờ tự sinh số. Chính sách/tài liệu dùng RAG có trích dẫn nguồn.
2. **Không có nguồn → không trả lời.** Mọi câu trả lời tài liệu phải dẫn được về
   nguồn trong brain; thiếu thì nói thẳng là chưa có.
3. **Privacy theo `user_ref`.** Nhân viên thường chỉ hỏi được dữ liệu của mình;
   số liệu tổng hợp/nhạy cảm chỉ trả cho nhóm HR (whitelist open_id).
4. **Con người duyệt.** Đề xuất điều chỉnh chính sách, form đánh giá, JD… đều là
   bản nháp chờ duyệt — agent không quyết định nhân sự.

## 2. Đề xuất phương án truy vấn chính xác (chờ owner chốt)

| Phương án | Dùng cho | Nhận xét |
|---|---|---|
| **Brain platform** (`/v1/self/brain/search`, scope=agent + shared) — **chọn làm chính** | Chính sách, quy trình, tài liệu đào tạo | Nằm sẵn trong platform, có nguồn, agent khác đọc được phần publish; console chỉnh được nội dung |
| **Truy vấn code Lark Base/Sheet** — **bắt buộc cho số liệu** | KPI, thu nhập, chấm công, headcount | Chính xác 100%, kiểm thử được; model không đụng vào phép tính |
| NotebookLM (notebooklm-py — pattern AG-LEGAL) | Nghiên cứu sâu chính sách nhà nước, đối chiếu văn bản luật dài | Bổ sung ở P3, không làm kho chính (nằm ngoài platform, khó cho A2A) |

Lý do không dùng NotebookLM làm kho chính: tri thức phải nằm trong brain platform thì
console mới chỉnh được, agent khác mới đọc được qua shared brain, và trích dẫn mới
đồng nhất. NotebookLM giữ vai trò "bàn nghiên cứu" cho use case chính sách nhà nước.

## 3. Kiến trúc tri thức

```
Lark Wiki/Drive (thư mục cố định do owner quy ước)
        │  sync định kỳ (cron, script trong agents/AG-HR/)
        ▼
Brain scope=agent (AG-HR riêng)  ←— console: cập nhật/điều chỉnh
        │  publish có chọn lọc, định kỳ
        ▼
Shared brain platform  ←— agent khác đọc qua A2A/search
```

- Thư mục cố định (đề xuất, owner đặt tên thật): `HR/ChinhSach`, `HR/Onboarding`,
  `HR/DaoTao`, `HR/TuyenDung`. File mới/sửa trong các folder này được index ở chu kỳ kế.
- Bộ nhớ riêng của agent = brain scope=agent + user_facts/session do platform giữ.

## 4. Lộ trình (phase — mỗi phase chạy được, test được rồi mới sang phase sau)

### P0 — Prototype (làm ngay sau confirm)
- `consumer.py`: `answer()` gọi Claude qua **Claude Agent SDK** (model auth = subscription
  owner, `claude setup-token`; cấu hình strict để không tốn context thừa).
- RAG từ brain + trích dẫn nguồn; gửi `usage` khi complete job để dashboard đo chi phí.
- Nạp tay ~5–10 tài liệu chính sách mẫu vào brain để test.
- Test: `docker compose up` → `bash scripts/agent-test.sh AG-HR` → web chat `/agent/AG-HR`.
- Phủ test case #1–5 (tests.jsonl).

### P1 — Kho tri thức sống
- Script sync Lark Wiki/Drive (thư mục cố định) → brain scope=agent, chạy cron định kỳ.
- Quy trình publish chọn lọc lên shared brain.
- `POST /v1/agents/AG-HR/profile` (capabilities + usage_guide) — master data trước golive.
- Phủ test case #12. Nhờ admin ACTIVATE → lên Lark nhóm HR.

### P2 — Số liệu nhân sự (nhạy cảm — cần cấp quyền trước)
- Kết nối đọc Lark Base/Sheet nhân sự; module truy vấn bằng code cho headcount,
  chấm công, phép, KPI, thu nhập.
- Privacy gate theo `user_ref`: nhân viên chỉ hỏi được của mình; whitelist HR.
- Phủ test case #6–8. Sau đó mới mở kênh cho toàn bộ nhân viên qua Lark.

### P3 — Nghiệp vụ nâng cao
- Cron tổng hợp chính sách nhà nước (VBPL, thuvienphapluat…) → bản tin + đề xuất
  điều chỉnh (đánh dấu chờ duyệt). NotebookLM hỗ trợ đối chiếu văn bản dài.
- Train & re-train: soạn giáo trình/quiz từ tài liệu trong brain, theo dõi lộ trình.
- Đánh giá xếp loại: form + calibration theo framework owner chốt.
- Phủ test case #9–10.

### P4 — Đồng bộ hệ sinh thái agent
- A2A: nhận câu hỏi từ agent khác (vd AG-LEGAL hỏi chính sách nội bộ), chuyển câu
  pháp lý sâu sang AG-LEGAL.
- Lịch cập nhật định kỳ tri thức HR về shared brain.
- Phủ test case #11.

## 5. Việc owner cần làm (ngoài code)

1. Lấy token: `ssh lsr-gcp "sudo cat /opt/lsr-platform/secrets/agents/AG-HR.env"` → dán vào `agents/AG-HR/.env`.
2. Chốt tên thư mục Lark cố định + cấp quyền app Lark đọc các folder đó (P1).
3. Cấp quyền đọc Base/Sheet nhân sự + chốt whitelist HR được xem số liệu nhạy cảm (P2).
4. Nhờ admin ACTIVATE khi P0 test xong (admin đã nhận thông báo lúc agent đăng ký).
5. Duyệt nội dung publish lên shared brain (P1) và mọi đề xuất điều chỉnh chính sách (P3).
