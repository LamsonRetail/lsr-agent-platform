# Test & Learn

Tính năng test năng lực (agent lẫn người) + training khi trượt.

## Nguyên tắc
- **Test** gồm nhiều **Question** (test case). Có thể **sinh tự động** (`source=auto`)
  nhưng **phải người review** mới `active` — chưa active thì **không ai làm được**.
- **Chọn agent đã đăng ký** để làm bài (hoặc **người** — cùng cơ chế chấm).
- **Trượt → cần training**: hệ thống gợi ý tài liệu theo skill/tag của bài test.
- **Training do HR cung cấp**: import file công ty → **markdown** → lưu lại.

## Vòng đời bài test
```
draft ──submit──► in_review ──approve(reviewer)──► active ──(làm bài)──► [pass | fail→training]
   (auto/manual)                (bắt buộc người duyệt)
```

## Module (đã code + test): `rating_agent.testlearn`
- `Test`/`Question`/`Attempt`/`TrainingMaterial` (models).
- `grade`, `make_attempt` — chấm điểm (reuse assertion của agent_testing);
  `NotTakeableError` nếu test chưa active.
- `submit_for_review`, `approve`, `new_auto_draft` — vòng đời review.
- `recommend_training` — gợi ý tài liệu khi trượt (khớp skill/tag).
- `import_training_file` / `to_markdown` — HR import file (.md/.txt) → markdown.

## API (Platform API, deployed :8090)
| Endpoint | Việc |
|----------|------|
| `POST /v1/tests` [admin] | tạo bài test (draft; source manual/auto) |
| `POST /v1/tests/{id}/review` [admin] | duyệt → active (bắt buộc `reviewed_by`) |
| `GET /v1/tests` · `/{id}` | liệt kê/xem |
| `POST /v1/attempts` | làm bài (`taker_type` = agent \| human); 409 nếu test chưa active; fail → `training` gợi ý |
| `GET /v1/attempts` | lịch sử làm bài (theo taker/test) |
| `POST /v1/training` [admin] · `GET /v1/training` | lưu/liệt kê tài liệu training (md) |

## Đã verify live
draft → 409 khi chưa active → review→active → agent fail (0.5) + gợi ý training
`order` → người pass (1.0). Xem [infra/DEPLOY.md](infra/DEPLOY.md).

## Còn lại
- **Sinh test tự động** bằng LLM (hiện `new_auto_draft` nhận sẵn câu hỏi).
- Chuyển đổi **.docx/.pdf** → md (dùng skill docx/pdf ở runtime).
- Màn hình Test & Learn trên dashboard (tạo/review/giao bài/kết quả).
- Cổng cho **nhân sự** làm bài (UI người dùng).
