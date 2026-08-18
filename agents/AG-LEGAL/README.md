# Legal Agent (AG-LEGAL)

Trợ lý pháp chế: hỏi đáp có trích dẫn từ Wiki/Drive pháp chế (engine NotebookLM), tạo hợp
đồng từ template, review hợp đồng đối tác, hỗ trợ hồ sơ trình ký, tổng hợp văn bản luật.
**Mọi output đi qua chốt Pháp chế** (xem "Pháp chế in the loop" bên dưới).

Đọc trước khi sửa code: **[CLAUDE.md](CLAUDE.md)** (3 nguyên tắc + ràng buộc kỹ thuật) ·
**[USECASE.md](USECASE.md)** (phạm vi) · **[TESTCASES.md](TESTCASES.md)** ·
**[INSTRUCTION.md](INSTRUCTION.md)** (hành vi — nguồn của `instruction_block`) ·
**[SETUP.md](SETUP.md)** (việc admin cần làm trước).

Thứ tự làm việc (gate CI `agent-gate` tự chặn nếu bỏ qua):
**USECASE.md → TESTCASES.md → code**.

## Chạy & test

```bash
python3 -m pytest tests/ -q          # 88 case offline, không cần secret (~1s)
```

CI của repo không chạy bộ này (`testpaths` ở gốc chỉ trỏ `tests/` của core) → tự chạy
trước khi commit.

```bash
cp .env.example .env && vi .env && docker compose up
```

```bash
python3 seed_roles.py                # nạp 2 người duyệt + resolve open_id
```

Đăng ký & golive (chuẩn mới của platform — **không đi xin enroll token của ai**):

```bash
bash ../../scripts/lsr-login.sh      # device login → token cá nhân ~/.lsr/token
```

Sau đó enroll bằng chính token đó, rồi `claude setup-token` → `POST /v1/self/deploy`.
Chi tiết: `PLAN-AG-LEGAL.md §2.2`. **Kiểm golive bằng `GET /v1/self/context` →
`instruction_block` ≠ null** — đừng tin `status`/`golive_at` trên dashboard.

## Console của agent
**https://app.34-126-154-135.sslip.io/agent/AG-LEGAL** — chat thử, jobs, traces, chi phí,
brain riêng, version.

## Kênh vào

| Kênh | Cần gì |
|---|---|
| Web chat (console) | có sẵn, không cần gán |
| Lark | `channel=lark`, chat_id nhóm — admin gán một dòng ở Console → Ingress |
| ~~Telegram~~ | **bỏ khỏi scope** (chốt 17/08/2026) |

## Pháp chế in the loop

Group **`oc_2c44821d37e5e12a2c1651251cfd4efb`** vừa nhận thông báo vừa nhận lệnh phê duyệt.
Người duyệt (Nguyễn Trần Thi — BOD, Nguyễn Thị Anh — Legal) gõ trong group:

| Lệnh | Việc |
|---|---|
| `#12 duyệt` | thông qua |
| `#12 sửa: <góp ý>` | yêu cầu sửa, quay lại agent |
| `#12 huỷ: <lý do>` | từ chối |
| `#12 tham gia` / `#12 trả lại` | người thay Agent trong hội thoại đó / trả lại Agent |
| `#12 nhắn: <nội dung>` | chuyển lời tới người hỏi |
| `#ds` | danh sách việc đang chờ |

Tin nhắn thường trong group → agent **im lặng**. Gate quá hạn → **nhắc**, không bao giờ
tự động thông qua.
